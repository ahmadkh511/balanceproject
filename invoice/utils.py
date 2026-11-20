# انشاءنا هذا الملف من اجل فصل المهام في الايمل 
from decimal import Decimal
import logging
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.mail import get_connection, send_mail
from django.contrib.auth.hashers import check_password
from django.shortcuts import render
from .models import EmailSetting, PricingSetting
logger = logging.getLogger(__name__)


# ==========================================
# دوال نظام البريد الإلكتروني
# ==========================================

def get_active_email_connection():
    """
    تجلب إعدادات البريد من قاعدة البيانات وتُنشئ اتصالاً جاهزاً للإرسال.
    """
    try:
        # جلب الإعدادات (نفترض أن هناك صف واحد فقط pk=1)
        config = EmailSetting.objects.get(pk=1)
        
        # إنشاء اتصال باستخدام البيانات المخزنة
        connection = get_connection(
            backend=config.email_backend,
            host=config.email_host,
            port=config.email_port,
            username=config.email_host_user,
            password=config.email_host_password,
            use_tls=config.email_use_tls,
            use_ssl=config.email_use_ssl,  # ★★★ بند 3.4 — قراءة من قاعدة البيانات بدل hardcoded False
        )
        return connection, config.default_from_email
    except EmailSetting.DoesNotExist:
        # في حال عدم وجود إعدادات في قاعدة البيانات
        logger.warning("إعدادات البريد غير موجودة في قاعدة البيانات.")
        return None, None


def send_custom_email(subject, message, recipient_list):
    """
    دالة مخصصة للإرسال تستخدم إعدادات قاعدة البيانات.
    استخدم هذه الدالة في جميع أنحاء المشروع.
    """
    connection, from_email = get_active_email_connection()
    
    if connection and from_email:
        try:
            send_mail(
                subject,
                message,
                from_email,
                recipient_list,
                fail_silently=False,
                connection=connection 
            )
            return True, "تم الإرسال بنجاح"
        except Exception as e:
            return False, str(e)
    else:
        return False, "إعدادات البريد غير مكتملة في النظام"


# ==========================================
# دوال نظام التسعير
# ==========================================



def verify_pricing_password(provided_password):
    """
    التحقق من كلمة مرور نظام التسعير (بطريقة آمنة ومشفرة باستخدام Django)

    ★★★ بند 2.1 — إصلاح ثغرة "المرور بدون كلمة مرور معرّفة" ★★★
    السلوك الجديد (Fail-Secure):
    - كلمة مرور فارغة من المدخل → مرفوضة (كما كان)
    - لا توجد كلمة مرور معرّفة في قاعدة البيانات → مرفوضة (سابقاً: كانت تُقبل!)
    - توجد كلمة مرور → التحقق منها عبر check_password
    اختبار: فحص_بند_2_1.py → 8/8
    """
    if not provided_password or not str(provided_password).strip():
        return False
        
    provided_password = str(provided_password).strip()
    settings = PricingSetting.get_settings()
    stored_password = settings.pricing_password
    
    # ★ بند 2.1: لا توجد كلمة مرور معرّفة → ارفض كل المحاولات
    # (سابقاً: return True → يقبل أي إدخال — ثغرة أمنية)
    if not stored_password:
        return False
        
    # استخدام دالة Django الآمنة للتحقق من النص المشفر
    return check_password(provided_password, stored_password)



def is_custom_password_set():
    """
    هل تم تعيين كلمة مرور مخصصة في قاعدة البيانات؟
    (تُستخدم في لوحة التحكم لعرض شارة "محمي" أو "افتراضي")
    """
    settings = PricingSetting.get_settings()
    pw = settings.pricing_password
    
    if not pw:
        return False
        
    # التأكد من أن كلمة المرور محفوظة بتشفير Django الصحيح وليس نصاً عادياً أو هاشاً قديماً
    return pw.startswith(('pbkdf2_sha256$', 'argon2$', 'bcrypt_sha256$'))


def is_pricing_password_set():
    """
    هل تم تعيين كلمة مرور لنظام التسعير؟
    (تُستخدم لتمييز "لا توجد كلمة معرّفة" عن "كلمة مرور خاطئة" — بند 2.1)
    """
    settings = PricingSetting.get_settings()
    return bool(settings.pricing_password)



# ==========================================
# دوال التسعير
# ==========================================

def get_product_price(product):
    """
    تحديد السعر النهائي للمنتج في المتجر
    
    ★★★ بند 3.1 — نقل من views.py إلى utils.py ★★★
    1. تبحث في تصنيف المنتج (إذا كان مربوطاً بمستوى تسعير).
    2. إذا لم تجد، ترجع لسعر الجملة.
    
    استخدمت في:
    - views.py (store_front, control_store, إلخ)
    - models.py (CartItem.total_item_price) — بند 3.1
    """
    if hasattr(product, 'category') and product.category and hasattr(product.category, 'pricing_tier') and product.category.pricing_tier:
        tier_id = product.category.pricing_tier.id
        try:
            from .models import ProductPriceTier
            tier_price = ProductPriceTier.objects.get(product=product, tier_id=tier_id)
            if tier_price.price and tier_price.price > 0:
                return tier_price.price
        except ProductPriceTier.DoesNotExist:
            pass

    return product.wholesale_price or Decimal('0.00')






























# ==========================================
# زخرفة حماية الصلاحيات العليا
# للمشرف الأعلى (superuser) فقط
# ==========================================







def superuser_required(view_func):
    """
    زخرفة موحدة تحمي الصفحات والعمليات الحساسة
    (مركز النسخ الاحتياطي: الإنشاء، التحميل، الحذف، الاسترجاع، تصفير المصنع).

    السلوك:
    - زائر غير مسجل: يُحوَّل إلى صفحة تسجيل الدخول (نفس سلوك login_required).
    - مستخدم مسجل دون صلاحية المدير الأعلى: يرى صفحة 403 الأنيقة الموجودة في المشروع.
    - المشرف الأعلى (superuser): يدخل بشكل طبيعي.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return render(request, 'invoice/403.html', status=403)
    return _wrapped