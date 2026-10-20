from django.db import models
from .models import Message


def unread_chat_count(request):
    """
    يحسب عدد الرسائل غير المقروءة للمستخدم الحالي.
    - superuser: كل الرسائل غير المقروءة (باستثناء رسائله)
    - موظف عادي: رسائل محادثاته (customer التي بدأها + internal طرف فيها)
    - عميل: رسائل محادثته (kind='customer')
    """
    if not request.user.is_authenticated:
        return {'unread_chat_count': 0}

    try:
        if request.user.is_superuser:
            # المدير: كل الرسائل غير المقروءة (باستثناء رسائله)
            count = Message.objects.exclude(
                sender=request.user,
            ).exclude(
                read_by__user=request.user,
            ).count()
        elif request.user.is_staff:
            # موظف عادي: فقط محادثاته
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
            # عميل: فقط محادثته
            count = Message.objects.filter(
                conversation__customer=request.user,
                conversation__kind='customer',
            ).exclude(
                sender=request.user,
            ).exclude(
                read_by__user=request.user,
            ).count()
    except Exception:
        count = 0

    return {'unread_chat_count': count}