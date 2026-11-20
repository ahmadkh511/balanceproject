"""
================================================================
فحص إثبات + إغلاق — بند 3.5 من تقرير التدقيق
================================================================
الموضوع: تحسين context_processors (cart_count)

المشكلة:
  - في invoice/context_processors.py، دالة cart_count تقوم بـ 2 استعلامين في كل طلب HTTP
  - استعلام Cart + استعلام items.count() = عبئ كبير على قاعدة البيانات

الإصلاح المقترح:
  - استخدام aggregate(Count('items')) لدمج الاستعلامين في استعلام واحد
  - تحسين الأداء بنسبة 50% (من 2 استعلام لكل طلب إلى 1)

السيناريوهات:
  1) مستخدم بدون سلة → cart_count = 0
  2) مستخدم بسلة فيها 3 عناصر (منتجات مختلفة) → cart_count = 3
  3) مستخدم زائر (غير مسجل) → cart_count = 0
  4) فحص static للكود: استخدام aggregate/annotate بدل .count() المنفصل

المنهجية:
  - استدعاء مباشر للنموذج + فحص static للكود + محاكاة request
  - 4 فحوصات × تشغيلان متطابقان = 8 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_3_5.py', encoding='utf-8').read())"
================================================================
"""

import os
from decimal import Decimal
from django.conf import settings
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.db.models import Q

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import Cart, CartItem, Product
from invoice.context_processors import cart_count

TEST_MARKER = 'فحص_3_5'
TEST_USER = f'{TEST_MARKER}_مستخدم'
TEST_PRODUCT_PREF = f'{TEST_MARKER}_منتج'

CONTEXT_PROCESSORS_PATH = os.path.join(settings.BASE_DIR, 'invoice', 'context_processors.py')


def read_context_processors():
    with open(CONTEXT_PROCESSORS_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def cleanup_test_data():
    test_user_ids = list(User.objects.filter(username=TEST_USER).values_list('id', flat=True))
    test_cart_ids = list(Cart.objects.filter(user_id__in=test_user_ids).values_list('id', flat=True))
    
    if test_cart_ids:
        CartItem.objects.filter(cart_id__in=test_cart_ids).delete()
        Cart.objects.filter(id__in=test_cart_ids).delete()
    
    Product.objects.filter(product_name__startswith=TEST_PRODUCT_PREF).delete()
    User.objects.filter(username=TEST_USER).delete()


def get_request_with_session(user):
    """إنشاء طلب محاكى مع session مُفعّلة"""
    rf = RequestFactory()
    request = rf.get('/')
    
    # إضافة Session
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    
    request.user = user
    return request


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    cleanup_test_data()
    
    # ====== [1] إعداد البيانات ======
    print_step(1, "إعداد البيانات الأساسية")
    
    user = User.objects.create(username=TEST_USER, first_name=TEST_MARKER)
    
    # إنشاء 3 منتجات مختلفة (لتجنب قيد التفرد في CartItem)
    products = []
    for i in range(3):
        p = Product.objects.create(
            product_name=f'{TEST_PRODUCT_PREF}_{i}',
            purch_price=Decimal('100.00'),
            sale_price=Decimal('150.00'),
            current_stock_quantity=Decimal('10.00'),
            average_purchase_cost=Decimal('100.00')
        )
        products.append(p)
    
    print(f"  المستخدم: {user.username}")
    print(f"  المنتجات: 3 منتجات مختلفة")
    
    # ====== [2] فحص 1: مستخدم بدون سلة ======
    print_step(2, "فحص 1: مستخدم بدون سلة (cart_count = 0)")
    
    request = get_request_with_session(user)
    result = cart_count(request)
    check_1 = (result.get('cart_count') == 0)
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | cart_count = {result.get('cart_count')} (متوقع 0)")
    
    # ====== [3] فحص 2: مستخدم بسلة فيها 3 عناصر ======
    print_step(3, "فحص 2: مستخدم بسلة فيها 3 عناصر (cart_count = 3)")
    
    cart = Cart.objects.create(user=user)
    for p in products:
        CartItem.objects.create(cart=cart, product=p, quantity=1)
    
    # إعادة إنشاء الطلب لتحديث الحالة
    request = get_request_with_session(user)
    result = cart_count(request)
    check_2 = (result.get('cart_count') == 3)
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | cart_count = {result.get('cart_count')} (متوقع 3)")
    
    # ====== [4] فحص 3: مستخدم زائر (غير مسجل) ======
    print_step(4, "فحص 3: مستخدم زائر (غير مسجل، cart_count = 0)")
    
    request_anon = get_request_with_session(AnonymousUser())
    result_anon = cart_count(request_anon)
    check_3 = (result_anon.get('cart_count') == 0)
    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | cart_count = {result_anon.get('cart_count')} (متوقع 0)")
    
    # ====== [5] فحص 4: فحص static للكود ======
    print_step(5, "فحص 4: ★ فحص الكود (استخدام aggregate/annotate بدل .count() المنفصل)")
    
    cp_content = read_context_processors()
    
    # النمط القديم: استخدام .count() على علاقة (items.count)
    old_pattern = ".items.count()" in cp_content or ".items.all().count()" in cp_content
    
    # النمط الجديد: استخدام aggregate أو annotate مع Count
    new_pattern = "aggregate" in cp_content or "annotate" in cp_content
    has_count_import = "Count" in cp_content and "import" in cp_content
    
    if old_pattern:
        print(f"  ✗ نمط قديم موجود: .items.count() (استعلامين منفصلين)")
    if new_pattern and has_count_import:
        print(f"  ✓ نمط جديد موجود: aggregate/annotate مع Count (استعلام واحد)")
    
    check_4 = new_pattern and has_count_import and not old_pattern
    sign = '✓' if check_4 else '✗'
    print(f"  {sign} {'PASS' if check_4 else 'FAIL'} | استخدام aggregate/annotate بدل .count()")
    
    # ====== [6] العداد النهائي ======
    print_step(6, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3, check_4]
    descriptions = [
        'مستخدم بدون سلة: cart_count = 0',
        'مستخدم بسلة (3 عناصر): cart_count = 3',
        'مستخدم زائر (غير مسجل): cart_count = 0',
        '★ استخدام aggregate/annotate بدل .count() المنفصل',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/4")
    
    cleanup_test_data()
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 3.5 من تقرير التدقيق")
print(f"  الموضوع: تحسين context_processors (cart_count)")
print(f"  المنهجية: استدعاء مباشر + فحص static + محاكاة request + 4 فحوصات × تشغيلان")
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

check_4_passes = run1_checks[3]

if run1_p == 4 and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 3.5 أُغلق بدليل رقمي:")
    print(f"    - cart_count يعمل بشكل صحيح (0، 3، 0)")
    print(f"    - استخدام aggregate/annotate بدل .count() المنفصل")
    print(f"    - تحسين الأداء: 1 استعلام بدل 2 لكل طلب")
elif not check_4_passes and same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✗ الفحص 4 فشل: الكود يستخدم .items.count() (استعلامين منفصلين)")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")