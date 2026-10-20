import os
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import models
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from PIL import Image


from .models import Conversation, Message, MessageRead


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


def chat_room(request):
    """محادثة العميل — إذا لم يسجل دخول، صفحة مخصصة، وإذا لا توجد محادثة، صفحة أخرى"""

    # 1. إذا لم يسجل الدخول → صفحة دخول مخصصة
    if not request.user.is_authenticated:
        from django.urls import reverse
        return render(request, 'chat/login_prompt.html', {
            'login_url': reverse('accounts:login'),
        })

    # 2. إذا مسجل → ابحث عن محادثته
    conversation = Conversation.objects.filter(
        customer=request.user,
        kind='customer',
    ).first()

    # 3. إذا لا توجد محادثة → صفحة "لا توجد محادثة"
    if not conversation:
        return render(request, 'chat/room_empty.html')

    # 4. كل شيء جاهز → صفحة المحادثة
    return render(request, 'chat/room.html', {
        'conversation': conversation,
        'max_size': settings.CHAT_MAX_FILE_SIZE,
    })

#=================== صفحات الموظف/المدير ====================

@login_required
def staff_inbox(request):
    """صندوق الموظف: تبويبان — عملاء / داخلي"""
    if not request.user.is_staff:
        messages.error(request, 'هذه الصفحة مخصصة للموظفين فقط.')
        return redirect('chat_room')

    if request.user.is_superuser:
        # المدير يرى كل شيء
        customer_convs = Conversation.objects.filter(kind='customer').select_related('customer')
        internal_convs = Conversation.objects.filter(kind='internal').select_related('customer', 'initiator')
    else:
        # موظف عادي: فقط محادثاته
        customer_convs = Conversation.objects.filter(
            kind='customer',
            initiator=request.user,
        ).select_related('customer')
        internal_convs = Conversation.objects.filter(
            kind='internal'
        ).filter(
            models.Q(customer=request.user) | models.Q(initiator=request.user)
        ).select_related('customer', 'initiator')

    # أضف علامة "غير مقروء" لكل محادثة
    customer_convs_list = []
    for c in customer_convs:
        c.has_unread = c.messages.exclude(
            sender=request.user
        ).exclude(
            read_by__user=request.user
        ).exists()
        customer_convs_list.append(c)

    internal_convs_list = []
    for c in internal_convs:
        c.has_unread = c.messages.exclude(
            sender=request.user
        ).exclude(
            read_by__user=request.user
        ).exists()
        internal_convs_list.append(c)

    available_users = User.objects.filter(
        is_active=True
    ).exclude(
        id=request.user.id
    ).order_by('username')

    return render(request, 'chat/staff_inbox.html', {
        'customer_convs': customer_convs_list,
        'internal_convs': internal_convs_list,
        'available_users': available_users,
    })


@login_required
def staff_chat(request, conv_id):
    """فتح محادثة معينة (من الموظف)"""
    if not request.user.is_staff:
        messages.error(request, 'هذه الصفحة مخصصة للموظفين فقط.')
        return redirect('chat_room')

    conversation = get_object_or_404(Conversation, id=conv_id)
    return render(request, 'chat/room.html', {
        'conversation': conversation,
        'max_size': settings.CHAT_MAX_FILE_SIZE,
    })



@login_required
def start_internal_conversation(request, user_id):
    """
    بدء محادثة مع مستخدم:
    - إذا كان الطرف الآخر عميلاً (is_staff=False) → محادثة customer
    - إذا كان موظفاً (is_staff=True) → محادثة internal
    """
    if not request.user.is_staff:
        messages.error(request, 'هذه الصفحة مخصصة للموظفين فقط.')
        return redirect('chat_room')

    peer = get_object_or_404(User, id=user_id, is_active=True)

    if peer.id == request.user.id:
        messages.warning(request, 'لا يمكنك بدء محادثة مع نفسك.')
        return redirect('staff_inbox')

    if peer.is_staff:
        # موظف ↔ موظف → محادثة داخلية
        conversation = Conversation.objects.filter(
            kind='internal'
        ).filter(
            models.Q(customer=request.user, initiator=peer) |
            models.Q(customer=peer, initiator=request.user)
        ).first()

        if not conversation:
            conversation = Conversation.objects.create(
                kind='internal',
                customer=peer,
                initiator=request.user,
            )
    else:
        # موظف → عميل → محادثة customer (نفس نوع ما ينشئه العميل)
        conversation = Conversation.objects.filter(
            kind='customer',
            customer=peer,
        ).first()

        if not conversation:
            conversation = Conversation.objects.create(
                kind='customer',
                customer=peer,
            )

    return redirect('staff_chat', conv_id=conversation.id)


# ==================== API ====================


@login_required
def get_messages(request, conv_id):
    """جلب الرسائل (AJAX polling) + تسجيل قراءة المستخدم الحالي"""
    conversation = get_object_or_404(Conversation, id=conv_id)

    if not _can_access(conversation, request.user):
        return JsonResponse({'error': 'forbidden'}, status=403)

    # سجّل قراءة المستخدم الحالي لكل رسالة في المحادثة لم يقرأها بعد
    # (باستثناء رسائله هو)
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

    # حذف الملفات من القرص
    for msg in conversation.messages.all():
        if msg.attachment:
            try:
                msg.attachment.delete(save=False)
            except Exception:
                pass

    conversation.delete()
    messages.success(request, 'تم حذف المحادثة بنجاح.')
    return redirect('staff_inbox')




#من اجل ظهور التنبيه في الهيدر عند ايقونة الجرس


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

    from django.contrib.auth.models import User

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

    # احسب عدد غير المقروء لكل مستخدم (بناءً على MessageRead + منطق superuser/staff/client)
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