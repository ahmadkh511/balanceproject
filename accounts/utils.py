# ============================================
# accounts/utils.py — حارس البيانات (نسخة الأدوار النهائية)
# ============================================
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.shortcuts import redirect

GROUP_VIEW_ONLY = 'تصفح'   # اسم مجموعتك الفعلي


def is_view_only(user):
    """هل المستخدم عضو في مجموعة التصفح (مشاهدة فقط)؟"""
    return user.is_authenticated and user.groups.filter(name=GROUP_VIEW_ONLY).exists()


def block_view_only(view_func):
    """
    يمنع أعضاء مجموعة التصفح من أي فيو يغيّر بيانات (إنشاء/تعديل/حذف)
    برسالة ودية بدل صفحة 403 الخام.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and is_view_only(request.user) and not request.user.is_superuser:
            messages.error(request, 'حسابك للقراءة فقط — لا يمكنك الإضافة أو التعديل أو الحذف.')
            return redirect(request.META.get('HTTP_REFERER') or '/')
        return view_func(request, *args, **kwargs)
    return _wrapped


def get_user_scoped_queryset(queryset, request):
    """
    القوائم: سوبر أو "تصفح" يرى كل السجلات، غير ذلك يرى ما أنشأه فقط.
    """
    user = request.user
    if user.is_superuser or is_view_only(user):
        return queryset
    if hasattr(queryset.model, 'created_by'):
        return queryset.filter(created_by=user)
    return queryset


def check_object_view(obj, request):
    """صفحات التفاصيل: "تصفح" يمرّ دائماً"""
    user = request.user
    if user.is_superuser or is_view_only(user):
        return True
    if hasattr(obj, 'created_by') and obj.created_by is not None and obj.created_by == user:
        return True
    raise PermissionDenied('ليس لديك صلاحية للوصول إلى هذا العنصر.')


def check_object_owner(obj, request):
    """التعديل والحذف فقط: "تصفح" يُمنع دائماً"""
    user = request.user
    if user.is_superuser:
        return True
    if is_view_only(user):
        raise PermissionDenied('حسابك للقراءة فقط.')
    if hasattr(obj, 'created_by') and obj.created_by is not None and obj.created_by == user:
        return True
    raise PermissionDenied('ليس لديك صلاحية للوصول إلى هذا العنصر.')