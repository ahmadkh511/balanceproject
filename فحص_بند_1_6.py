"""
================================================================
فحص إثبات + إغلاق — بند 1.6 من تقرير التدقيق
================================================================
الموضوع: تحصين SaleItem.delete() لمراعاة المرتجعات

المشكلة:
  - SaleItem.delete() تستعيد المخزون بناءً على sold_quantity الكاملة.
  - لو حُذف بند عليه مرتجع (مثلاً بيع 10، مرتجع 2)، الكود يُعيد 10 للمخزون.
  - النتيجة: المخزون يزيد بـ 2 وحدات وهمية (لأن وحدتين رجعتا سابقاً).

الإصلاح المقترح:
  - حساب الكمية الفعّالة (sold - returned) في delete() وإعادتها للمخزون فقط.

السيناريوهات:
  1) حذف بند بيع بلا مرتجع → يُعيد sold_quantity (2) للمخزون
  2) حذف بند بيع عليه مرتجع (مبيع 4، مرتجع 2) → يُعيد 2 فقط للمخزون (لا 4)

المنهجية:
  - استدعاء مباشر للنماذج (لا HTTP لتجنب حواجز sale_edit)
  - مستخدم معزول
  - تنظيف ذاتي قبل/بعد
  - 2 سيناريوهات × تشغيلان متطابقان = 4 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_1_6.py', encoding='utf-8').read())"
================================================================
"""

from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q, Sum

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import (
    Sale, SaleItem, SaleReturn, SaleReturnItem, Product, Payment_method, Currency
)

TEST_MARKER = 'فحص_1_6'
TEST_ADMIN = f'{TEST_MARKER}_مدير'
TEST_CUSTOMER = f'{TEST_MARKER}_عميل'
TEST_PRODUCT_1 = f'{TEST_MARKER}_منتج_1'
TEST_PRODUCT_2 = f'{TEST_MARKER}_منتج_2'


def cleanup_test_data():
    test_user_ids = list(User.objects.filter(username__in=[TEST_CUSTOMER, TEST_ADMIN]).values_list('id', flat=True))
    test_sale_ids = list(Sale.objects.filter(Q(sale_customer_id__in=test_user_ids) | Q(created_by_id__in=test_user_ids)).values_list('id', flat=True))
    
    if test_sale_ids:
        SaleReturnItem.objects.filter(sale_return__original_sale_id__in=test_sale_ids).delete()
        SaleReturn.objects.filter(original_sale_id__in=test_sale_ids).delete()
        SaleItem.objects.filter(sale_id__in=test_sale_ids).delete()
        Sale.objects.filter(id__in=test_sale_ids).delete()
    
    Product.objects.filter(product_name__in=[TEST_PRODUCT_1, TEST_PRODUCT_2]).delete()
    User.objects.filter(username__in=[TEST_CUSTOMER, TEST_ADMIN]).delete()


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
    
    currency = Currency.objects.filter(is_default=True).first() or Currency.objects.first()
    cash_method = Payment_method.objects.filter(is_cash=True).first()
    
    customer = User.objects.create(username=TEST_CUSTOMER, first_name=TEST_MARKER)
    admin = User.objects.create_superuser(username=TEST_ADMIN, password='Test@12345', first_name=TEST_MARKER)
    
    # المنتج الأول (لبند بلا مرتجع) - مخزون ابتدائي 10
    product1 = Product.objects.create(
        product_name=TEST_PRODUCT_1, purch_price=Decimal('100.00'), sale_price=Decimal('150.00'),
        current_stock_quantity=Decimal('10.00'), average_purchase_cost=Decimal('100.00')
    )
    
    # المنتج الثاني (لبند عليه مرتجع) - مخزون ابتدائي 10
    product2 = Product.objects.create(
        product_name=TEST_PRODUCT_2, purch_price=Decimal('100.00'), sale_price=Decimal('150.00'),
        current_stock_quantity=Decimal('10.00'), average_purchase_cost=Decimal('100.00')
    )
    
    # فاتورة بيع
    sale = Sale.objects.create(
        sale_customer=customer, sale_currency=currency, sale_payment_method=cash_method,
        paid_amount=Decimal('1000.00'), created_by=admin
    )
    
    # بند 1: بيع 2 من product1 (بلا مرتجع)
    item1 = SaleItem.objects.create(
        sale=sale, product=product1, item_name=product1.product_name,
        sold_quantity=Decimal('2.00'), unit_price=Decimal('150.00')
    )
    item1.update_product_stock() # المخزون: 10 - 2 = 8
    
    # بند 2: بيع 4 من product2
    item2 = SaleItem.objects.create(
        sale=sale, product=product2, item_name=product2.product_name,
        sold_quantity=Decimal('4.00'), unit_price=Decimal('150.00')
    )
    item2.update_product_stock() # المخزون: 10 - 4 = 6
    
    # إنشاء مرتجع بيع لبند 2 (إرجاع 2 وحدات)
    sale_return = SaleReturn.objects.create(
        original_sale=sale, created_by=admin, return_date='2026-11-21',
        return_payment_method=cash_method, return_currency=currency, paid_amount=Decimal('300.00')
    )
    return_item = SaleReturnItem.objects.create(
        sale_return=sale_return, original_sale_item=item2, product=product2,
        item_name=product2.product_name, returned_quantity=Decimal('2.00'), unit_price=Decimal('150.00')
    )
    return_item.restore_product_stock() # المخزون: 6 + 2 = 8
    
    product1.refresh_from_db()
    product2.refresh_from_db()
    print(f"  الحالة قبل الحذف:")
    print(f"  - المنتج 1 (بلا مرتجع): مخزون = {product1.current_stock_quantity} (متوقع 8)")
    print(f"  - المنتج 2 (عليه مرتجع): مخزون = {product2.current_stock_quantity} (متوقع 8)")
    
    # ====== [2] السيناريو 1: حذف بند بلا مرتجع ======
    print_step(2, "السيناريو 1: حذف بند بيع بلا مرتجع (item1)")
    
    item1.delete()
    product1.refresh_from_db()
    
    # المتوقع: المخزون يعود لـ 10 (استرجاع 2 وحدات)
    expected_stock_1 = Decimal('10.00')
    actual_stock_1 = product1.current_stock_quantity
    check_1 = (actual_stock_1 == expected_stock_1)
    
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | مخزون المنتج 1 بعد الحذف = {actual_stock_1} (متوقع {expected_stock_1})")
    
    # ====== [3] السيناريو 2: حذف بند عليه مرتجع ======
    print_step(3, "السيناريو 2: ★ حذف بند بيع عليه مرتجع (item2)")
    
    item2.delete()
    product2.refresh_from_db()
    
    # المتوقع: المخزون يعود لـ 10 (استرجاع 2 وحدات فقط، لأن 2 رجعتا سابقاً)
    expected_stock_2 = Decimal('10.00')
    actual_stock_2 = product2.current_stock_quantity
    check_2 = (actual_stock_2 == expected_stock_2)
    
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | مخزون المنتج 2 بعد الحذف = {actual_stock_2} (متوقع {expected_stock_2})")
    if not check_2:
        print(f"     ✗ العلة: الكود أضاف sold_quantity الكاملة (4) بدل الفعّالة (2). النتيجة الخاطئة: 12")
    
    # ====== [4] العداد النهائي ======
    print_step(4, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2]
    descriptions = [
        'حذف بند بلا مرتجع: استرجاع sold_quantity للمخزون',
        '★ حذف بند عليه مرتجع: استرجاع الكمية الفعّالة (sold - returned) فقط',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/2")
    
    cleanup_test_data()
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 1.6 من تقرير التدقيق")
print(f"  الموضوع: تحصين SaleItem.delete() لمراعاة المرتجعات")
print(f"  المنهجية: استدعاء مباشر + 2 سيناريوهات × تشغيلان")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    p, checks = run_test(i)
    all_results.append((p, checks))

print_header("الخلاصة النهائية")

run1_p, run1_checks = all_results[0]
run2_p, run2_checks = all_results[1]
same_run = (run1_checks == run2_checks)

print(f"  التشغيل 1: {run1_p}/2")
print(f"  التشغيل 2: {run2_p}/2")
print(f"  متطابقة: {same_run}")
print(f"  النتيجة النهائية: {run1_p}/2")

if run1_p == 2 and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 1.6 أُغلق بدليل رقمي:")
    print(f"    - SaleItem.delete() يحسب الكمية الفعّالة (sold - returned)")
    print(f"    - المخزون يُسترجع بدقة حتى لو حُذف بند عليه مرتجع")
elif not run1_checks[1] and same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✗ الفحص 2 فشل: الكود يسترجع sold_quantity الكاملة بدل الفعّالة")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")