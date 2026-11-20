"""
================================================================
فحص إثبات + إغلاق — بند 3.1 من تقرير التدقيق
================================================================
الموضوع: CartItem.total_item_price يتجاهل نظام مستويات التسعير (PricingTier)

المشكلة:
  - CartItem.total_item_price يستخدم سلسلة أسعار ثابتة (wholesale → retail → ...)
  - لا يحترم ProductPriceTier المرتبط بتصنيف المنتج
  - النتيجة: العميل يرى سعراً في المتجر، وسعراً مختلفاً في السلة

الإصلاح المقترح:
  - نقل get_product_price من views.py إلى utils.py
  - تحديث CartItem.total_item_price لاستخدام get_product_price

السيناريوهات:
  1) منتج بلا مستوى تسعير → total_item_price = wholesale_price × quantity
  2) منتج بمستوى تسعير (خصم 20%) → total_item_price = tier_price × quantity (لا wholesale)
  3) Cart.total_price يحترم الـ tier أيضاً
  4) get_product_price موجودة في utils.py (وليست فقط في views.py)

المنهجية:
  - استدعاء مباشر للنماذج (لا HTTP)
  - مستخدم معزول
  - تنظيف ذاتي قبل/بعد
  - 4 فحوصات × تشغيلان متطابقان = 8 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_3_1.py', encoding='utf-8').read())"
================================================================
"""

from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import (
    Product, CartItem, Cart, Category, PricingTier, ProductPriceTier
)

TEST_MARKER = 'فحص_3_1'
TEST_USER = f'{TEST_MARKER}_مستخدم'
TEST_PRODUCT_1 = f'{TEST_MARKER}_منتج_بلا_تير'
TEST_PRODUCT_2 = f'{TEST_MARKER}_منتج_ب_تير'
TEST_CATEGORY = f'{TEST_MARKER}_تصنيف'
TEST_TIER = f'{TEST_MARKER}_مستوى'


def cleanup_test_data():
    """تنظيف شامل"""
    test_user_ids = list(User.objects.filter(username=TEST_USER).values_list('id', flat=True))
    test_cart_ids = list(Cart.objects.filter(user_id__in=test_user_ids).values_list('id', flat=True))
    
    if test_cart_ids:
        CartItem.objects.filter(cart_id__in=test_cart_ids).delete()
        Cart.objects.filter(id__in=test_cart_ids).delete()
    
    test_product_ids = list(Product.objects.filter(
        product_name__in=[TEST_PRODUCT_1, TEST_PRODUCT_2]
    ).values_list('id', flat=True))
    
    if test_product_ids:
        ProductPriceTier.objects.filter(product_id__in=test_product_ids).delete()
        Product.objects.filter(id__in=test_product_ids).delete()
    
    test_tier_ids = list(PricingTier.objects.filter(name=TEST_TIER).values_list('id', flat=True))
    test_category_ids = list(Category.objects.filter(name=TEST_CATEGORY).values_list('id', flat=True))
    
    if test_category_ids:
        Category.objects.filter(id__in=test_category_ids).delete()
    if test_tier_ids:
        PricingTier.objects.filter(id__in=test_tier_ids).delete()
    
    User.objects.filter(username=TEST_USER).delete()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    cleanup_test_data()
    
    # ====== [1] إعداد البيانات ======
    print_step(1, "إعداد البيانات الأساسية")
    
    user = User.objects.create(username=TEST_USER, first_name=TEST_MARKER)
    cart = Cart.objects.create(user=user)
    print(f"  المستخدم: {user.username}")
    print(f"  السلة: {cart.id}")
    
    # منتج 1: بلا تير (سعر الجملة = 100)
    product1 = Product.objects.create(
        product_name=TEST_PRODUCT_1,
        purch_price=Decimal('80.00'),
        sale_price=Decimal('120.00'),
        wholesale_price=Decimal('100.00'),
        current_stock_quantity=Decimal('10.00'),
        average_purchase_cost=Decimal('80.00')
    )
    print(f"  المنتج 1 (بلا تير): {product1.product_name} | wholesale=100")
    
    # منتج 2: بـ تير (سعر الجملة = 200، تير = 160 بخصم 20%)
    product2 = Product.objects.create(
        product_name=TEST_PRODUCT_2,
        purch_price=Decimal('150.00'),
        sale_price=Decimal('250.00'),
        wholesale_price=Decimal('200.00'),
        current_stock_quantity=Decimal('10.00'),
        average_purchase_cost=Decimal('150.00')
    )
    print(f"  المنتج 2 (بـ تير): {product2.product_name} | wholesale=200")
    
    # إنشاء Tier و Category و ProductPriceTier
    tier = PricingTier.objects.create(name=TEST_TIER, discount_percent=Decimal('20.00'))
    print(f"  Tier: {tier.name} (خصم 20%)")
    
    category = Category.objects.create(name=TEST_CATEGORY, pricing_tier=tier)
    print(f"  Category: {category.name} → Tier: {tier.name}")
    
    product2.category = category
    product2.save()
    
    # ProductPriceTier: 200 × (1 - 0.20) = 160
    product_tier_price = ProductPriceTier.objects.create(
        product=product2,
        tier=tier,
        price=Decimal('160.00')
    )
    print(f"  ProductPriceTier: {product2.product_name} = 160")
    
    # ====== [2] إنشاء CartItems ======
    print_step(2, "إنشاء عناصر السلة")
    
    item1 = CartItem.objects.create(cart=cart, product=product1, quantity=2)
    item2 = CartItem.objects.create(cart=cart, product=product2, quantity=3)
    print(f"  Item 1: {product1.product_name} × 2")
    print(f"  Item 2: {product2.product_name} × 3")
    
    # ====== [3] فحص 1: منتج بلا تير ======
    print_step(3, "فحص 1: منتج بلا تير (total_item_price = wholesale × qty)")
    
    # متوقع: 100 × 2 = 200
    expected_1 = Decimal('200.00')
    actual_1 = item1.total_item_price
    check_1 = (actual_1 == expected_1)
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | item1.total_item_price = {actual_1} (متوقع {expected_1})")
    
    # ====== [4] فحص 2: منتج بـ تير ======
    print_step(4, "فحص 2: ★ منتج بـ تير (total_item_price = tier_price × qty)")
    
    # متوقع: 160 × 3 = 480 (لا 200 × 3 = 600)
    expected_2 = Decimal('480.00')
    actual_2 = item2.total_item_price
    check_2 = (actual_2 == expected_2)
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | item2.total_item_price = {actual_2} (متوقع {expected_2})")
    
    if not check_2:
        print(f"     ✗ العلة: السلة تستخدم wholesale ({Decimal('200.00') * 3}) بدل tier_price (160 × 3)")
    
    # ====== [5] فحص 3: Cart.total_price يحترم الـ tier ======
    print_step(5, "فحص 3: Cart.total_price يحترم الـ tier")
    
    # متوقع: 200 (item1) + 480 (item2) = 680 (لا 200 + 600 = 800)
    expected_3 = Decimal('680.00')
    actual_3 = cart.total_price
    check_3 = (actual_3 == expected_3)
    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | cart.total_price = {actual_3} (متوقع {expected_3})")
    
    # ====== [6] فحص 4: get_product_price في utils.py ======
    print_step(6, "فحص 4: get_product_price موجودة في utils.py (نقلت من views.py)")
    
    try:
        from invoice.utils import get_product_price
        check_4 = callable(get_product_price)
        print(f"  ✓ get_product_price موجودة في utils.py ومُستدعاة بنجاح")
        
        # اختبار سريع: get_product_price(product2) يجب = 160
        price_test = get_product_price(product2)
        price_ok = (price_test == Decimal('160.00'))
        print(f"    get_product_price(product2) = {price_test} (متوقع 160) → {price_ok}")
        if not price_ok:
            check_4 = False
    except ImportError:
        check_4 = False
        print(f"  ✗ get_product_price غير موجودة في utils.py (ما زالت في views.py)")
    except Exception as e:
        check_4 = False
        print(f"  ✗ خطأ: {e}")
    
    sign = '✓' if check_4 else '✗'
    print(f"  {sign} {'PASS' if check_4 else 'FAIL'} | get_product_price في utils.py")
    
    # ====== [7] العداد النهائي ======
    print_step(7, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3, check_4]
    descriptions = [
        'منتج بلا تير: total_item_price = wholesale × qty',
        '★ منتج بـ تير: total_item_price = tier_price × qty (لا wholesale)',
        'Cart.total_price يحترم الـ tier',
        'get_product_price موجودة في utils.py',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/4")
    
    cleanup_test_data()
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 3.1 من تقرير التدقيق")
print(f"  الموضوع: CartItem.total_item_price يتجاهل نظام مستويات التسعير")
print(f"  المنهجية: استدعاء مباشر + 4 فحوصات × تشغيلان")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    p, checks = run_test(i)
    all_results.append((p, checks))

print_header("الخلاصة النهائية")

run1_p, run1_checks = all_results[0]
run2_p, run2_checks = all_results[1]
same_run = (run1_checks == run2_checks)

print(f"  التشغيل 1: {run1_p}/4")
print(f"  التشغيل 2: {run2_p}/4")
print(f"  متطابقة: {same_run}")
print(f"  النتيجة النهائية: {run1_p}/4")

# تحليل النتائج
check_2_passes = run1_checks[1]  # منتج بـ تير

if run1_p == 4 and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 3.1 أُغلق بدليل رقمي:")
    print(f"    - CartItem.total_item_price يستخدم get_product_price")
    print(f"    - يحترم مستويات التسعير (PricingTier)")
    print(f"    - Cart.total_price يعكس الأسعار الصحيحة")
    print(f"    - get_product_price في utils.py (نقلت من views.py)")
elif not check_2_passes and same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✗ الفحص 2 فشل: السلة تستخدم wholesale بدل tier_price")
    print(f"  الأثر: العميل يرى سعراً في المتجر، وسعراً مختلفاً في السلة")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
    print(f"  راجع الفحوصات الفاشلة أعلاه")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")




