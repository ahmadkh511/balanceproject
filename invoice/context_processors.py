import logging
from .models import Cart

# تهيئة الـ logger لتسجيل الأخطاء
logger = logging.getLogger(__name__)


def cart_count(request):
    """
    Context Processor: جلب عدد عناصر سلة التسوق
    """
    count = 0
    
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.filter(user=request.user).first()
            if cart:
                count = cart.items.count()
        except Exception as e:
            logger.warning(f"تعذر جلب عدد عناصر سلة المستخدم {request.user.id}: {e}")
    else:
        session_key = request.session.session_key
        if session_key:
            try:
                cart = Cart.objects.filter(session_key=session_key, user__isnull=True).first()
                if cart:
                    count = cart.items.count()
            except Exception as e:
                logger.warning(f"تعذر جلب عدد عناصر سلة الزائر (الجلسة: {session_key}): {e}")
    
    return {'cart_count': count}


# ❌ تم حذف الدالة company_settings لتجنب التكرار
# لأنها موجودة بالفعل في accounts.context_processors.site_settings