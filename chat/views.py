import os

from PIL import Image

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Conversation, Message, MessageRead, BroadcastLog

from django.db.models import Count
from django.shortcuts import render
from .models import Conversation, MessageRead
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Conversation, Message, MessageRead

User = get_user_model()



from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Conversation, Message, MessageRead

User = get_user_model()

#===============من اجل الحماية  ctx  ==================
#===============================


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
    - الموظف/المدير: يصل لكل المحادثات
    - العميل: يصل لمحادثات customer التي هو طرفها
    - أي مستخدم: يصل لمحادثات internal التي هو طرف فيها
    """
    if user.is_staff:
        return True
    if conversation.customer_id == user.id:
        return True
    if conversation.kind == 'internal' and conversation.initiator_id == user.id:
        return True
    return False


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
    peer = conversation.initiator

    messages = (conversation.messages
                .select_related('sender')
                .order_by('created_at', 'id'))

    return render(request, 'chat/room.html', _ctx(
        request,
        conversation=conversation,
        peer=peer,
        messages=messages,
    ))

    
# ==================== صفحات الموظف/المدير ====================

# ============================================================
# مساعد السياق: يضمن وصول csp_nonce لكل قالب دون إخلال
# ============================================================

# ============================================================
# مساعد السياق: يضمن وصول csp_nonce لكل قالب دون إخلال
# ============================================================
def _ctx(request, **data):
    nonce = getattr(request, 'csp_nonce', None)
    if nonce:
        data['csp_nonce'] = nonce
    return data


# ============================================================
# البحث عن محادثة قائمة بين موظف ومستخدم آخر حسب نموذج B
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

    # المحادثات الداخلية: يراها الطرفان فقط
    internal_convs = (Conversation.objects
                      .filter(kind='internal')
                      .filter(Q(initiator=user) | Q(customer=user))
                      .annotate(msg_count=Count('messages'))
                      .filter(msg_count__gt=0)
                      .select_related('initiator', 'customer')
                      .order_by('-id'))

    # محادثات العملاء: السوبر يوزر يرى كل القنوات، والموظف يرى قناته فقط
    if user.is_superuser:
        customer_convs = (Conversation.objects
                          .filter(kind='customer')
                          .annotate(msg_count=Count('messages'))
                          .filter(msg_count__gt=0)
                          .select_related('initiator', 'customer')
                          .order_by('-id'))
    else:
        customer_convs = (Conversation.objects
                          .filter(kind='customer', initiator=user)
                          .annotate(msg_count=Count('messages'))
                          .filter(msg_count__gt=0)
                          .select_related('initiator', 'customer')
                          .order_by('-id'))

    available_users = (User.objects
                       .filter(is_active=True)
                       .exclude(id=user.id)
                       .order_by('username'))

    return render(request, 'chat/staff_inbox.html', _ctx(
        request,
        internal_convs=internal_convs,
        customer_convs=customer_convs,
        available_users=available_users,
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

    messages = (conversation.messages
                .select_related('sender')
                .order_by('created_at', 'id'))

    return render(request, 'chat/room.html', _ctx(
        request,
        conversation=conversation,
        peer=peer,
        messages=messages,
    ))


# ============================================================
# زر "بدء": توجيه ذكي حسب نموذج B
# أسماء الروابط مجردة مطابقة لملف المسارات لديك (بدون بادئة chat:)
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

    return JsonResponse({'ok': True, 'conv_id': conv.id,
                         'message_id': message.id})





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
        }

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

            Message.objects.create(
                conversation=conversation,
                sender=request.user,
                content=content,
            )
            messages_sent += 1

        BroadcastLog.objects.create(
            sender=request.user,
            target=target,
            content=content,
            recipients_count=recipients_count,
            conversations_created=conversations_created,
        )

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
    import base64
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

    return render(request, 'chat/share_qr.html', {
        'chat_url': chat_url,
        'qr_base64': qr_base64,
    })