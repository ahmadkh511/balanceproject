import logging

from .models import Profile, User, CompanySettings

# تهيئة الـ logger لتسجيل الأخطاء
logger = logging.getLogger(__name__)


def site_settings(request):
    """
    يجعل إعدادات الموقع متاحة في جميع القوالب.
    """
    context_data = {
        'company_logo': None,
        'user_profile_picture': '/static/images/default_avatar.png',
        'company_settings': None,
        'current_url_name': '',
        'user_last_login': 'غير متاح',
        'cart_count': 0,
        'unread_notifications_count': 0,
    }

    # ========== 0. اسم URL الحالي بأمان ==========
    try:
        if hasattr(request, 'resolver_match') and request.resolver_match:
            context_data['current_url_name'] = request.resolver_match.url_name or ''
    except Exception:
        pass

    # ========== 1. جلب إعدادات الشركة ==========
    try:
        settings = CompanySettings.get_settings()
        context_data['company_settings'] = settings
    except Exception as e:
        logger.warning(f"تعذر جلب إعدادات الشركة في Context Processor: {e}")

    # ========== 2. جلب شعار الشركة (للخلفية) ==========
    try:
        superuser = User.objects.filter(is_superuser=True).first()
        if superuser and hasattr(superuser, 'profile'):
            context_data['company_logo'] = superuser.profile.logo
    except (User.DoesNotExist, Profile.DoesNotExist):
        pass

    # ========== 3. صورة البروفايل + آخر دخول ==========
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            if profile.profile_picture and hasattr(profile.profile_picture, 'url'):
                context_data['user_profile_picture'] = profile.profile_picture.url
        except Exception as e:
            logger.warning(f"تعذر جلب صورة بروفايل المستخدم {request.user.id}: {e}")

        if request.user.last_login:
            context_data['user_last_login'] = request.user.last_login.strftime('%d %B %Y %H:%M')
        else:
            context_data['user_last_login'] = 'أول دخول'

    return context_data


def company_settings(request):
    """
    توفير إعدادات الشركة لجميع القوالب (نسخة مختصرة ومحسنة)
    """
    try:
        settings = CompanySettings.get_settings()
        return {'company_settings': settings}
    except Exception as e:
        logger.warning(f"تعذر جلب company_settings: {e}")
        return {'company_settings': None}