import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Conversation, Message, MessageRead, BroadcastLog, PushSubscription

User = get_user_model()


# ============================================================
# Web Push — استيرادات اختيارية آمنة:
# إن لم تكن الحزمة أو المفاتيح مثبتة بعد يعمل الموقع كالمعتاد
# وتتعطل وظيفة الدفع بصمت دون أي كسر
# ============================================================
try:
    from pywebpush import webpush, WebPushException
except Exception:
    webpush = None
    WebPushException = Exception

try:
    from .vapid_keys import VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY
except Exception:
    VAPID_PUBLIC_KEY = ''
    VAPID_PRIVATE_KEY = ''

try:
    from .icons_data import ICON_PNG_B64
except Exception:
    ICON_PNG_B64 = {}

PUSH_CLAIMS_SUB = 'mailto:admin@balanceiqsoft.com'


# ============================================================
# مساعد السياق: يضمن وصول csp_nonce لكل قالب دون إخلال
# + مفتاح VAPID العام لكل قالب يحتاجه زر تفعيل التنبيهات
# ============================================================
def _ctx(request, **data):
    nonce = getattr(request, 'csp_nonce', None)
    if nonce:
        data['csp_nonce'] = nonce
    data.setdefault('vapid_public_key', VAPID_PUBLIC_KEY)
    return data


# ==================== أدوات مساعدة ====================


def _validate_attachment(file):
    """يتحقق من حجم ونوع الملف. يرجع (type, error)."""
    ext = os.path.splitext(file.name)[1].lower()
    size = file.size

    if size > settings.CHAT_MAX_FILE_SIZE:
        max_mb = settings.CHAT_MAX_FILE_SIZE // (1024 * 1024)
        return '', f'حجم الملف يتجاوز {max_mb} MB'

    if ext in settings.CHAT_ALLOWED_IMAGE_EXTS:
        try:
            Image.open(file).verify()
        except Exception:
            return '', 'ملف الصورة غير صالح'
        file.seek(0)
        return 'image', ''

    if ext in settings.CHAT_ALLOWED_AUDIO_EXTS:
        if not (getattr(file, 'content_type', '') or '').startswith('audio/'):
            return '', 'نوع الملف الصوتي غير مدعوم'
        return 'audio', ''

    return '', 'نوع الملف غير مسموح'


def _can_access(conversation, user):
    """
    صلاحيات الوصول — نموذج مالك القناة (Model B):
    - السوبر يوزر: يصل إلى كل المحادثات (إشراف).
    - العميل: يصل لمحادثته فقط (قناة customer التي هو طرفها).
    - الموظف: يصل لقنوات العملاء التي يملكها فقط،
      وللمحادثات الداخلية التي يكون طرفاً فيها.
    """
    if user.is_superuser:
        return True

    if conversation.kind == 'customer':
        if conversation.customer_id == user.id:
            return True
        if user.is_staff and conversation.initiator_id == user.id:
            return True
        return False

    # محادثة داخلية: للطرفين فقط
    return (conversation.initiator_id == user.id
            or conversation.customer_id == user.id)


def _serialize_message(msg):
    url = msg.attachment.url if msg.attachment else ''
    return {
        'id': msg.id,
        'content': msg.content,
        'created_at': msg.created_at.isoformat(),
        'sender__username': msg.sender.username,
        'sender_id': msg.sender.id,
        'attachment_url': url,
        'attachment_type': msg.attachment_type,
        'attachment_size': msg.attachment_size,
    }


# ============================================================
# أدوات Web Push — إشعارات تعمل حتى والمتصفح/التطبيق مغلق
# ============================================================

def _push_preview(message):
    """نص مختصر للإشعار: المحتوى أو وصف المرفق."""
    if message.content:
        return message.content[:180]
    if message.attachment_type == 'image':
        return 'صورة مرفقة'
    if message.attachment_type == 'audio':
        return 'مقطع صوتي'
    return 'مرفق'


def _push_target_url(conversation, recipient_id):
    """الرابط الذي يفتحه الإشعار عند النقر حسب هوية المستلم."""
    if conversation.kind == 'internal':
        return reverse('staff_chat', args=[conversation.id])
    if recipient_id == conversation.customer_id:
        return reverse('chat_room')
    return reverse('staff_chat', args=[conversation.id])


def _push_payload(conversation, message, recipient_id):
    sender_name = message.sender.get_full_name() or message.sender.username
    return json.dumps({
        'title': 'رسالة جديدة من ' + sender_name,
        'body': _push_preview(message),
        'url': _push_target_url(conversation, recipient_id),
        'icon': '/chat/icon-192.png',
        'tag': 'bq-conv-' + str(conversation.id),
    }, ensure_ascii=False)


def _push_recipient_ids(conversation, sender_id):
    """معرفات المستلمين المستحقين للإشعار (الطرف الآخر فقط)."""
    if conversation.kind == 'internal':
        ids = {conversation.initiator_id, conversation.customer_id}
        return [i for i in ids if i and i != sender_id]
    ids = []
    if conversation.customer_id and conversation.customer_id != sender_id:
        ids.append(conversation.customer_id)
    if conversation.initiator_id and conversation.initiator_id != sender_id:
        ids.append(conversation.initiator_id)
    return ids


def _send_push_to_user(user_id, payload):
    """يرسل إلى كل أجهزة المستخدم ويحذف الاشتراكات الميتة (404/410).
    لا يرفع استثناءات أبداً حتى لا يؤثر على إرسال الرسالة نفسها."""
    for sub in PushSubscription.objects.filter(user_id=user_id):
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={'sub': PUSH_CLAIMS_SUB},
                timeout=5,
            )
        except WebPushException as exc:
            code = getattr(getattr(exc, 'response', None), 'status_code', None)
            if code in (404, 410):
                sub.delete()
        except Exception:
            pass


def _push_notify(conversation, message):
    """يحاول إرسال Web Push للطرف الآخر — آمن للاستدعاء من أي مكان."""
    try:
        if webpush is None or not VAPID_PRIVATE_KEY:
            return
        for uid in _push_recipient_ids(conversation, message.sender_id):
            _send_push_to_user(uid, _push_payload(conversation, message, uid))
    except Exception:
        pass


# ============================================================
# Service Worker — يُخدم من /chat/sw.js مع ترويسة
# Service-Worker-Allowed: / ليصح نطاقه على كامل الموقع
# لا يحتوي معالج fetch إطلاقاً حتى لا يتدخل في أي طلب
# ============================================================
SW_JS = """/* BalanceIQ Chat — Service Worker: Web Push فقط، لا يتدخل في الطلبات */
self.addEventListener('install', function (event) {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', function (event) {
  var data = {};
  try {
    if (event.data) { data = event.data.json(); }
  } catch (err) {
    try { data = { body: event.data.text() }; } catch (err2) { data = {}; }
  }

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      var hasFocused = clientList.some(function (c) { return c.focused; });
      // إن كانت نافذة التطبيق مركّزة الآن فالصفحة تعرض الرسالة بنفسها — لا إشعار مزدوج
      if (hasFocused) { return null; }
      return self.registration.showNotification(data.title || 'رسالة جديدة', {
        body: data.body || 'لديك رسالة جديدة',
        icon: data.icon || '/chat/icon-192.png',
        badge: '/chat/icon-192.png',
        tag: data.tag || 'bq-chat',
        data: { url: data.url || '/chat/' },
        dir: 'rtl',
        lang: 'ar'
      });
    })
  );
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var url = (event.notification.data && event.notification.data.url) || '/chat/';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      // 1) نافذة مفتوحة على نفس الرابط؟ ركّزها
      for (var i = 0; i < clientList.length; i++) {
        var c = clientList[i];
        if (c.url && c.url.indexOf(url) !== -1 && c.focus) { return c.focus(); }
      }
      // 2) نافذة مفتوحة للتطبيق؟ وجّهها للرابط المطلوب وركّزها
      for (var j = 0; j < clientList.length; j++) {
        var c2 = clientList[j];
        if (c2.url && c2.url.indexOf(self.location.origin) === 0) {
          if (c2.navigate) {
            return c2.navigate(url)
              .then(function (nc) { return (nc || c2).focus(); })
              .catch(function () { return self.clients.openWindow(url); });
          }
          if (c2.focus) { return c2.focus(); }
        }
      }
      // 3) لا توجد نوافذ مفتوحة — افتح الرابط في نافذة جديدة
      return self.clients.openWindow(url);
    })
  );
});
"""


# أيقونة SVG مطابقة لأيقونة PNG — تُخدم من /chat/icon.svg
ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#00bcd4"/>
      <stop offset="1" stop-color="#006064"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" fill="url(#g)"/>
  <ellipse cx="256" cy="220" rx="140" ry="110" fill="#ffffff"/>
  <path d="M180 316 L268 316 L168 392 Z" fill="#ffffff"/>
  <circle cx="200" cy="205" r="17" fill="#006064"/>
  <circle cx="256" cy="205" r="17" fill="#006064"/>
  <circle cx="312" cy="205" r="17" fill="#006064"/>
</svg>
"""


# ==================== صفحات العميل ====================


def chat_room(request, conv_id=None):
    user = request.user

    # ─── 1) غير المسجل أو الموظف ليس له عمل في قناة العميل ───
    if not user.is_authenticated or user.is_staff:
        return render(request, 'chat/room_empty.html', _ctx(request))

    # ─── 2) العميل يصل إلى محادثته هو حصراً ───
    if conv_id is not None:
        conversation = Conversation.objects.filter(
            kind='customer', id=conv_id, customer=user,
        ).first()
    else:
        conversation = (Conversation.objects
                        .filter(kind='customer', customer=user)
                        .annotate(msg_count=Count('messages'))
                        .filter(msg_count__gt=0)
                        .order_by('-id')
                        .first())

    # ─── 3) الحماية الدائمة ───
    if conversation is None or not conversation.messages.exists():
        return render(request, 'chat/room_empty.html', _ctx(request))

    # ─── 4) تسجيل قراءة رسائل الإدارة ───
    MessageRead.objects.bulk_create(
        [MessageRead(user=user, message=m)
         for m in conversation.messages.exclude(sender=user)],
        ignore_conflicts=True,
    )

    # ─── 5) الطرف الآخر = جهة الإدارة ───
    # لا نمرر متغير messages إلى القالب: القالب يجلب الرسائل عبر AJAX،
    # وتمرير هذا الاسم كان يحجب رسائل التنبيهات ويطبع بطاقات غريبة أعلى الصفحة
    peer = conversation.initiator

    return render(request, 'chat/room.html', _ctx(
        request,
        conversation=conversation,
        peer=peer,
    ))


# ==================== صفحات الموظف/المدير — نموذج B ====================


# ============================================================
# البحث عن محادثة قائمة بين موظف ومستخدم آخر — بحث فقط، لا ينشئ شيئاً
# ============================================================
def _find_conversation_with(view_user, peer):
    if peer.is_staff:
        return (Conversation.objects
                .filter(kind='internal')
                .filter(Q(initiator=view_user) | Q(customer=view_user))
                .filter(Q(initiator=peer) | Q(customer=peer))
                .first())
    # العميل: قناة واحدة، السوبر يوزر يصل إليها أياً كان مالكها
    if view_user.is_superuser:
        return (Conversation.objects
                .filter(kind='customer', customer=peer)
                .first())
    # الموظف العادي: قناته هو فقط
    return (Conversation.objects
            .filter(kind='customer', customer=peer, initiator=view_user)
            .first())


# ============================================================
# صندوق وارد الموظف — نموذج B
# ============================================================
def staff_inbox(request):
    user = request.user
    if not user.is_authenticated or not user.is_staff:
        return render(request, 'chat/room_empty.html', _ctx(request))

    # مؤشر "جديد": هل توجد رسالة لم يقرأها هذا المستخدم بعد؟
    # (يقرأه قالب الأرشيف عبر c.has_unread لعرض شارة الرسالة الجديدة)
    unread_marker = (Message.objects
                     .filter(conversation=OuterRef('pk'))
                     .exclude(sender=user)
                     .exclude(read_by__user=user))

    # المحادثات الداخلية: يراها الطرفان فقط
    internal_convs = (Conversation.objects
                      .filter(kind='internal')
                      .filter(Q(initiator=user) | Q(customer=user))
                      .annotate(msg_count=Count('messages'))
                      .filter(msg_count__gt=0)
                      .annotate(has_unread=Exists(unread_marker))
                      .select_related('initiator', 'customer')
                      .order_by('-id'))

    # محادثات العملاء: السوبر يوزر يرى كل القنوات، والموظف يرى قناته فقط
    if user.is_superuser:
        customer_convs = (Conversation.objects
                          .filter(kind='customer')
                          .annotate(msg_count=Count('messages'))
                          .filter(msg_count__gt=0)
                          .annotate(has_unread=Exists(unread_marker))
                          .select_related('initiator', 'customer')
                          .order_by('-id'))
    else:
        customer_convs = (Conversation.objects
                          .filter(kind='customer', initiator=user)
                          .annotate(msg_count=Count('messages'))
                          .filter(msg_count__gt=0)
                          .annotate(has_unread=Exists(unread_marker))
                          .select_related('initiator', 'customer')
                          .order_by('-id'))

    available_users = (User.objects
                       .filter(is_active=True)
                       .exclude(id=user.id)
                       .order_by('username'))

    # إجمالي المحادثات في النظام كله — يستخدمه قالب الأرشيف في زر
    # "حذف الكل" (يظهر للمدير الأعلى فقط) وفي نص نافذة التأكيد
    total_conversations = Conversation.objects.count() if user.is_superuser else 0

    return render(request, 'chat/staff_inbox.html', _ctx(
        request,
        internal_convs=internal_convs,
        customer_convs=customer_convs,
        available_users=available_users,
        total_conversations=total_conversations,
    ))


# ============================================================
# فتح محادثة موجودة — نموذج B + رفض أمني مباشر بلا أي نقل
# ============================================================
def staff_chat(request, conv_id):
    user = request.user
    if not user.is_authenticated or not user.is_staff:
        return render(request, 'chat/room_empty.html', _ctx(request))

    conversation = Conversation.objects.filter(id=conv_id).first()

    if conversation is None or not conversation.messages.exists():
        return render(request, 'chat/room_empty.html', _ctx(request))

    # نموذج B: مالك القناة أو السوبر يوزر فقط
    if not user.is_superuser:
        if conversation.kind == 'internal':
            party_ids = {conversation.initiator_id, conversation.customer_id}
            if user.id not in party_ids:
                return render(request, 'chat/room_empty.html', _ctx(request))
        else:
            if conversation.initiator_id != user.id:
                return render(request, 'chat/room_empty.html', _ctx(request))

    # تحديد الطرف الآخر لعرضه في الواجهة
    if conversation.kind == 'internal':
        peer = (conversation.customer
                if conversation.initiator_id == user.id
                else conversation.initiator)
    else:
        peer = conversation.customer

    # تأشير الرسائل كمقروءة لهذا المستخدم
    unread = conversation.messages.exclude(sender=user)
    if unread.exists():
        MessageRead.objects.bulk_create(
            [MessageRead(user=user, message=m) for m in unread],
            ignore_conflicts=True,
        )

    # لا نمرر متغير messages إلى القالب: القالب يجلب الرسائل عبر AJAX،
    # وتمرير هذا الاسم كان يحجب رسائل التنبيهات ويطبع بطاقات غريبة أعلى الصفحة
    return render(request, 'chat/room.html', _ctx(
        request,
        conversation=conversation,
        peer=peer,
    ))


# ============================================================
# زر "بدء": توجيه ذكي حسب نموذج B
# أسماء الروابط مجردة مطابقة لملف المسارات (بدون بادئة chat:)
# ============================================================
def start_internal_conversation(request, user_id):
    user = request.user
    if not user.is_authenticated or not user.is_staff:
        return render(request, 'chat/room_empty.html', _ctx(request))

    peer = User.objects.filter(id=user_id, is_active=True).first()
    if peer is None:
        return render(request, 'chat/room_empty.html', _ctx(request))

    # الهدف عميل؟ إن كانت له قناة قائمة: المالك أو السوبر يدخلها، وغيره صفحة آمنة
    if not peer.is_staff:
        existing = (Conversation.objects
                    .filter(kind='customer', customer=peer)
                    .first())
        if existing is not None:
            if user.is_superuser or existing.initiator_id == user.id:
                return redirect('staff_chat', conv_id=existing.id)
            return render(request, 'chat/room_empty.html', _ctx(request))

    conv = _find_conversation_with(user, peer)
    if conv is not None:
        return redirect('staff_chat', conv_id=conv.id)

    return redirect('staff_new_chat', user_id=peer.id)


# ============================================================
# غرفة المسودة (محادثة جديدة لم تُنشأ بعد)
# ============================================================
def staff_new_chat(request, user_id):
    user = request.user
    if not user.is_authenticated or not user.is_staff:
        return render(request, 'chat/room_empty.html', _ctx(request))

    peer = User.objects.filter(id=user_id, is_active=True).first()
    if peer is None:
        return render(request, 'chat/room_empty.html', _ctx(request))

    if not peer.is_staff:
        existing = (Conversation.objects
                    .filter(kind='customer', customer=peer)
                    .first())
        if existing is not None:
            if user.is_superuser or existing.initiator_id == user.id:
                return redirect('staff_chat', conv_id=existing.id)
            return render(request, 'chat/room_empty.html', _ctx(request))

    return render(request, 'chat/room.html', _ctx(request, peer=peer))


# ============================================================
# إنشاء المحادثة مع أول رسالة — حماية تزامنية + قاعدة المالك
# ============================================================
@require_POST
def send_first_message(request, user_id):
    user = request.user
    if not user.is_authenticated or not user.is_staff:
        return JsonResponse({'error': 'غير مصرح'}, status=403)

    peer = User.objects.filter(id=user_id, is_active=True).first()
    if peer is None:
        return JsonResponse({'error': 'المستخدم غير موجود'}, status=404)

    content = (request.POST.get('content') or '').strip()
    if not content:
        return JsonResponse({'error': 'لا يمكن إرسال رسالة فارغة'}, status=400)

    kind = 'internal' if peer.is_staff else 'customer'

    with transaction.atomic():
        # قفل صف الطرف الآخر: يمنع إنشاء محادثتين لنفس الزوج/العميل
        User.objects.select_for_update().get(id=peer.id)

        if kind == 'customer':
            existing = (Conversation.objects
                        .filter(kind='customer', customer=peer)
                        .select_for_update()
                        .first())
            if existing is not None:
                if user.is_superuser or existing.initiator_id == user.id:
                    conv = existing
                else:
                    return JsonResponse(
                        {'error': 'هذا العميل له قناة مفتوحة يتابعها موظف آخر'},
                        status=403)
            else:
                conv = None
        else:
            conv = _find_conversation_with(user, peer)

        if conv is None:
            conv = Conversation.objects.create(
                kind=kind, customer=peer, initiator=user)

        message = Message.objects.create(
            conversation=conv, sender=user, content=content)

    # إشعار فوري للطرف الآخر حتى لو كان التطبيق مغلقاً — لا يكسر الإرسال أبداً
    _push_notify(conv, message)

    return JsonResponse({'ok': True, 'conv_id': conv.id,
                         'message_id': message.id})


# ==================== واجهات AJAX ====================


@login_required
def get_messages(request, conv_id):
    """جلب الرسائل (AJAX polling) + تسجيل قراءة المستخدم الحالي"""
    conversation = get_object_or_404(Conversation, id=conv_id)

    if not _can_access(conversation, request.user):
        return JsonResponse({'error': 'forbidden'}, status=403)

    unread_message_ids = list(
        Message.objects.filter(
            conversation=conversation,
        ).exclude(
            sender=request.user,
        ).exclude(
            read_by__user=request.user,
        ).values_list('id', flat=True)
    )

    if unread_message_ids:
        MessageRead.objects.bulk_create(
            [MessageRead(message_id=mid, user=request.user) for mid in unread_message_ids],
            ignore_conflicts=True,
        )

    msgs = conversation.messages.select_related('sender').all()
    return JsonResponse({'messages': [_serialize_message(m) for m in msgs]})


@require_POST
@login_required
def send_message(request, conv_id):
    """إرسال رسالة نصية و/أو مرفق"""
    conversation = get_object_or_404(Conversation, id=conv_id)

    if not _can_access(conversation, request.user):
        return JsonResponse({'error': 'forbidden'}, status=403)

    content = request.POST.get('content', '').strip()
    file = request.FILES.get('attachment')

    if not content and not file:
        return JsonResponse({'error': 'الرسالة فارغة'}, status=400)

    att_type = ''
    if file:
        att_type, err = _validate_attachment(file)
        if err:
            return JsonResponse({'error': err}, status=400)

    msg = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=content,
        attachment=file if file else None,
        attachment_type=att_type,
        attachment_size=file.size if file else 0,
    )

    # إشعار فوري للطرف الآخر حتى لو كان التطبيق مغلقاً — لا يكسر الإرسال أبداً
    _push_notify(conversation, msg)

    return JsonResponse(_serialize_message(msg))


@require_POST
@login_required
def delete_conversation(request, conv_id):
    """حذف المحادثة — للمدير الأعلى فقط، مع إعادة توجيه بدل JSON"""
    if not request.user.is_superuser:
        messages.error(request, 'حذف المحادثات متاح للمدير فقط.')
        return redirect('staff_inbox')

    conversation = get_object_or_404(Conversation, id=conv_id)

    for msg in conversation.messages.all():
        if msg.attachment:
            try:
                msg.attachment.delete(save=False)
            except Exception:
                pass

    conversation.delete()
    messages.success(request, 'تم حذف المحادثة بنجاح.')
    return redirect('staff_inbox')


@require_POST
@login_required
def delete_all_conversations(request):
    """
    حذف جميع المحادثات دفعة واحدة — للمدير الأعلى فقط.
    يحذف كل محادثات العملاء والداخلية في النظام كله مع رسائلها
    ومرفقاتها وسجلات قراءتها، ثم يعود إلى الأرشيف برسالة تأكيد.
    (سجل الإرسال الجماعي BroadcastLog يبقى كما هو — سجل تدقيق مستقل)
    """
    if not request.user.is_superuser:
        messages.error(request, 'حذف المحادثات متاح للمدير فقط.')
        return redirect('staff_inbox')

    with transaction.atomic():
        conv_count = Conversation.objects.count()

        if conv_count == 0:
            messages.info(request, 'لا توجد محادثات لحذفها.')
            return redirect('staff_inbox')

        # 1) حذف ملفات المرفقات من التخزين أولاً — قبل حذف السجلات،
        #    وأي ملف ناقص أو محذوف يدوياً لا يوقف العملية
        for msg in Message.objects.exclude(attachment=''):
            if msg.attachment:
                try:
                    msg.attachment.delete(save=False)
                except Exception:
                    pass

        # 2) حذف كل المحادثات — الرسائل وسجلات القراءة
        #    تُحذف تلقائياً عبر CASCADE
        Conversation.objects.all().delete()

    messages.success(
        request,
        'تم حذف جميع المحادثات ({}) مع رسائلها ومرفقاتها بنجاح.'.format(
            conv_count))
    return redirect('staff_inbox')


# من اجل ظهور التنبيه في الهيدر عند ايقونة الجرس


@login_required
def unread_count_api(request):
    """AJAX: يرجع عدد الرسائل غير المقروءة الحالية (لكل مستخدم على حدة)"""
    if request.user.is_superuser:
        count = Message.objects.exclude(
            sender=request.user,
        ).exclude(
            read_by__user=request.user,
        ).count()
    elif request.user.is_staff:
        count = Message.objects.filter(
            models.Q(
                conversation__kind='customer',
                conversation__initiator=request.user,
            ) |
            models.Q(
                conversation__kind='internal',
                conversation__customer=request.user,
            ) |
            models.Q(
                conversation__kind='internal',
                conversation__initiator=request.user,
            )
        ).exclude(
            sender=request.user,
        ).exclude(
            read_by__user=request.user,
        ).count()
    else:
        count = Message.objects.filter(
            conversation__customer=request.user,
            conversation__kind='customer',
        ).exclude(
            sender=request.user,
        ).exclude(
            read_by__user=request.user,
        ).count()
    return JsonResponse({'count': count})


@login_required
def debug_conversations(request):
    """صفحة تشخيص مؤقتة — للمدير فقط"""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'forbidden'}, status=403)

    data = {
        'conversations': [],
        'unread_by_user': {},
    }

    for c in Conversation.objects.all().order_by('-id'):
        conv_data = {
            'id': c.id,
            'kind': c.kind,
            'customer': {
                'id': c.customer.id,
                'username': c.customer.username,
                'is_staff': c.customer.is_staff,
            },
            'initiator': (
                {
                    'id': c.initiator.id,
                    'username': c.initiator.username,
                    'is_staff': c.initiator.is_staff,
                }
                if c.initiator
                else None
            ),
            'messages': [],
        }
        for m in c.messages.all().order_by('id'):
            conv_data['messages'].append({
                'id': m.id,
                'from': m.sender.username,
                'from_id': m.sender.id,
                'read_by_users': list(m.read_by.values_list('user__username', flat=True)),
                'content': m.content[:50],
                'created_at': m.created_at.isoformat(),
            })
        data['conversations'].append(conv_data)

    for u in User.objects.filter(is_active=True):
        if u.is_superuser:
            count = Message.objects.exclude(
                sender=u
            ).exclude(
                read_by__user=u
            ).count()
        elif u.is_staff:
            count = Message.objects.filter(
                models.Q(conversation__kind='customer', conversation__initiator=u) |
                models.Q(conversation__kind='internal', conversation__customer=u) |
                models.Q(conversation__kind='internal', conversation__initiator=u)
            ).exclude(sender=u).exclude(read_by__user=u).count()
        else:
            count = Message.objects.filter(
                conversation__customer=u,
                conversation__kind='customer',
            ).exclude(sender=u).exclude(read_by__user=u).count()

        data['unread_by_user'][u.username] = {
            'id': u.id,
            'is_staff': u.is_staff,
            'is_superuser': u.is_superuser,
            'unread': count,
            'push_devices': PushSubscription.objects.filter(user=u).count(),
        }

    data['push_ready'] = bool(webpush is not None and VAPID_PRIVATE_KEY)

    return JsonResponse(data, json_dumps_params={'ensure_ascii': False, 'indent': 2})


@login_required
def broadcast(request):
    """إرسال رسالة جماعية — superuser فقط"""
    if not request.user.is_superuser:
        messages.error(request, 'هذه الصفحة مخصصة للمدير الأعلى فقط.')
        return redirect('staff_inbox')

    if request.method == 'POST':
        target = request.POST.get('target', 'all')
        content = request.POST.get('content', '').strip()

        if not content:
            messages.error(request, 'نص الرسالة فارغ.')
            return render(request, 'chat/broadcast.html', {
                'target_choices': BroadcastLog.TARGET_CHOICES,
                'selected_target': target,
                'content': content,
            })

        if target not in ('staff', 'customers', 'all'):
            target = 'all'

        recipients = User.objects.filter(is_active=True).exclude(id=request.user.id)

        if target == 'staff':
            recipients = recipients.filter(is_staff=True)
        elif target == 'customers':
            recipients = recipients.filter(is_staff=False)

        recipients = list(recipients)
        recipients_count = len(recipients)

        if recipients_count == 0:
            messages.warning(request, 'لا يوجد مستلمون مطابقون لهذه الفئة.')
            return redirect('broadcast')

        conversations_created = 0
        messages_sent = 0
        push_jobs = []

        for recipient in recipients:
            if recipient.is_staff:
                conversation = Conversation.objects.filter(
                    kind='internal'
                ).filter(
                    models.Q(customer=request.user, initiator=recipient) |
                    models.Q(customer=recipient, initiator=request.user)
                ).first()

                if not conversation:
                    conversation = Conversation.objects.create(
                        kind='internal',
                        customer=recipient,
                        initiator=request.user,
                    )
                    conversations_created += 1
            else:
                conversation = Conversation.objects.filter(
                    kind='customer',
                    customer=recipient,
                ).first()

                if not conversation:
                    conversation = Conversation.objects.create(
                        kind='customer',
                        customer=recipient,
                        initiator=request.user,
                    )
                    conversations_created += 1

            msg = Message.objects.create(
                conversation=conversation,
                sender=request.user,
                content=content,
            )
            messages_sent += 1

            # تجهيز مهام الإشعار لكل مستلم (تُنفَّذ بالتوازي بعد انتهاء الحفظ)
            try:
                if webpush is not None and VAPID_PRIVATE_KEY:
                    for uid in _push_recipient_ids(conversation, request.user.id):
                        push_jobs.append(
                            (uid, _push_payload(conversation, msg, uid)))
            except Exception:
                pass

        BroadcastLog.objects.create(
            sender=request.user,
            target=target,
            content=content,
            recipients_count=recipients_count,
            conversations_created=conversations_created,
        )

        # تنفيذ الإشعارات بالتوازي (8 خيوط) حتى لا تتجاوز مدة الطلب حدود gunicorn
        if push_jobs:
            try:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    for uid, payload in push_jobs:
                        pool.submit(_send_push_to_user, uid, payload)
            except Exception:
                pass

        messages.success(
            request,
            'تم إرسال الرسالة إلى {} مستلم ({} محادثة جديدة).'.format(
                messages_sent, conversations_created
            )
        )
        return redirect('staff_inbox')

    return render(request, 'chat/broadcast.html', {
        'target_choices': BroadcastLog.TARGET_CHOICES,
        'selected_target': 'all',
        'content': '',
    })


@login_required
def share_qr_view(request):
    """صفحة مشاركة رابط المحادثة عبر QR Code — متاحة للموظفين فقط."""
    if not request.user.is_staff:
        messages.error(request, 'هذه الصفحة مخصصة للموظفين فقط.')
        return redirect('chat_room')

    import qrcode
    import io
    from qrcode.constants import ERROR_CORRECT_H

    chat_url = request.build_absolute_uri('/chat/')

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=12,
        border=4,
    )
    qr.add_data(chat_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return render(request, 'chat/share_qr.html', _ctx(
        request,
        chat_url=chat_url,
        qr_base64=qr_base64,
    ))


# ============================================================
# Web Push — نقاط الاشتراك والإشعارات و PWA
# ============================================================

@require_POST
def push_subscribe(request):
    """تسجيل اشتراك دفع جديد أو تحديث الموجود — من جهاز المستخدم نفسه"""
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'forbidden'}, status=403)

    try:
        data = json.loads((request.body or b'').decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'bad json'}, status=400)

    sub = data.get('subscription') or {}
    keys = sub.get('keys') or {}
    endpoint = (sub.get('endpoint') or '').strip()
    p256dh = (keys.get('p256dh') or '').strip()
    auth = (keys.get('auth') or '').strip()

    if not (endpoint and p256dh and auth):
        return JsonResponse({'ok': False, 'error': 'incomplete'}, status=400)

    PushSubscription.objects.update_or_create(
        endpoint=endpoint[:500],
        defaults={
            'user': request.user,
            'p256dh': p256dh,
            'auth': auth,
            'user_agent': (request.META.get('HTTP_USER_AGENT') or '')[:255],
        },
    )
    return JsonResponse({'ok': True})


@require_POST
def push_unsubscribe(request):
    """إلغاء اشتراك دفع (عند تعطيل التنبيهات أو تسجيل الخروج من الجهاز)"""
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'forbidden'}, status=403)

    try:
        data = json.loads((request.body or b'').decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'bad json'}, status=400)

    endpoint = (data.get('endpoint') or '').strip()
    if endpoint:
        PushSubscription.objects.filter(
            user=request.user, endpoint=endpoint[:500]).delete()
    return JsonResponse({'ok': True})


def service_worker(request):
    """يخدم ملف الـ Service Worker من /chat/sw.js.
    ترويسة Service-Worker-Allowed: / تجعل نطاقه كامل الموقع،
    و no-cache تضمن التقاط التحديثات سريعاً."""
    resp = HttpResponse(SW_JS, content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/'
    resp['Cache-Control'] = 'no-cache'
    return resp


@login_required
def pwa_start(request):
    """بداية تطبيق PWA — توجه كل مستخدم إلى صفحته الصحيحة."""
    if request.user.is_staff:
        return redirect('staff_inbox')
    return redirect('chat_room')


def manifest_view(request):
    """مانيفست PWA — يتيح تثبيت التطبيق على الشاشة الرئيسية
    (شرط أساسي لعمل Web Push على iOS 16.4+)."""
    base = request.build_absolute_uri
    data = {
        'name': 'BalanceIQ — المحادثات',
        'short_name': 'BalanceIQ',
        'description': 'محادثات وتنبيهات BalanceIQ الفورية',
        'lang': 'ar',
        'dir': 'rtl',
        'start_url': base(reverse('pwa_start')),
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait',
        'background_color': '#e0f7fa',
        'theme_color': '#0097a7',
        'icons': [
            {'src': base('/chat/icon-192.png'), 'sizes': '192x192',
             'type': 'image/png', 'purpose': 'any maskable'},
            {'src': base('/chat/icon-512.png'), 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'any maskable'},
            {'src': base('/chat/icon.svg'), 'sizes': 'any',
             'type': 'image/svg+xml', 'purpose': 'any'},
        ],
    }
    return JsonResponse(data)


def icon_svg(request):
    resp = HttpResponse(ICON_SVG, content_type='image/svg+xml')
    resp['Cache-Control'] = 'public, max-age=86400'
    return resp


def icon_png(request, size):
    b64 = ICON_PNG_B64.get(str(size))
    if not b64:
        raise Http404
    resp = HttpResponse(base64.b64decode(b64), content_type='image/png')
    resp['Cache-Control'] = 'public, max-age=86400'
    return resp