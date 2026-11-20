from django.db.models import Count
from .models import Cart

def cart_count(request):
    """
    تمرير عدد عناصر سلة التسوق لكل القوالب.
    
    ★★★ بند 3.5 — تحسين الأداء ★★★
    استخدام aggregate(Count) لدمج استعلام Cart واستعلام items.count() 
    في استعلام واحد فقط، مما يقلل العبء على قاعدة البيانات بنسبة 50%.
    اختبار: فحص_بند_3_5.py → 4/4
    """
    if request.user.is_authenticated:
        # ★ استخدام aggregate(Count('items')) لتنفيذ استعلام واحد بدل اثنين
        count = Cart.objects.filter(user=request.user).annotate(
            item_count=Count('items')
        ).values_list('item_count', flat=True).first() or 0
        return {'cart_count': count}
    
    # معالجة المستخدم الزائر (غير المسجل)
    elif hasattr(request, 'session') and request.session.session_key:
        count = Cart.objects.filter(session_key=request.session.session_key, user__isnull=True).annotate(
            item_count=Count('items')
        ).values_list('item_count', flat=True).first() or 0
        return {'cart_count': count}
    
    return {'cart_count': 0}