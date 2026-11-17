"""
================================================================
فحص حارسة 3 — حذف فاتورة الشراء بلا خصم مزدوج (3/3)
================================================================
الموضوع: التحقق من أن حذف فاتورة الشراء يخصم المخزون مرة واحدة فقط
         (السلوك المؤكد على Django 4.2.16: cascade لا يستدعي delete()
         الموروثة للبنود — المخزون يُخصم مرة واحدة من purch_delete)

السيناريو:
  1) إنشاء منتج بمخزون 0
  2) إنشاء فاتورة شراء بكمية 2 → المخزون يجب أن يصبح 2
  3) حذف الفاتورة عبر الفيوة الحية → المخزون يجب أن يصبح 0 (لا -2)

المنهجية المعتمدة:
  - ضرب الفيوة الحية عبر django.test.Client
  - مستخدم فائق معزول
  - تنظيف ذاتي قبل/بعد
  - بيانات معلّمة ببادئة 'فحص_خصم_حذف_الشراء'
  - يُشغَّل مرتين متتاليتين ويعطي النتيجة نفسها
  - مخرجات بنمط PASS/FAIL وعدد نهائي 3/3

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_خصم_حذف_الشراء.py', encoding='utf-8').read())"
================================================================
"""

from decimal import Decimal
from django.conf import settings
from django.test import Client
from django.contrib.auth import get_user_model
from django.db.models import Q

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import (
    Purch, PurchItem, PurchItemBarcode,
    Barcode, Product, CashTransaction, Payment_method, Currency
)

TEST_MARKER      = 'فحص_خصم_حذف_الشراء'
TEST_ADMIN       = f'{TEST_MARKER}_مدير'
TEST_SUPPLIER    = f'{TEST_MARKER}_مورد'
TEST_PRODUCT     = f'{TEST_MARKER}_منتج'
TEST_BARCODE_PREF = f'{TEST_MARKER}_باركود_'


def cleanup_test_data():
    test_purch_ids = list(Purch.objects.filter(
        Q(purch_supplier__username=TEST_SUPPLIER) |
        Q(created_by__username=TEST_ADMIN)
    ).values_list('id', flat=True))

    if test_purch_ids:
        PurchItemBarcode.objects.filter(purch_item__purch_id__in=test_purch_ids).delete()
        PurchItem.objects.filter(purch_id__in=test_purch_ids).delete()
        Purch.objects.filter(id__in=test_purch_ids).delete()

    CashTransaction.objects.filter(
        Q(purchase_invoice_id__in=test_purch_ids) |
        Q(notes__contains=TEST_MARKER) |
        Q(created_by__username=TEST_ADMIN)
    ).delete()

    Barcode.objects.filter(barcode_in__startswith=TEST_BARCODE_PREF).delete()
    Product.objects.filter(product_name__startswith=TEST_MARKER).delete()
    User.objects.filter(username__in=[TEST_SUPPLIER, TEST_ADMIN]).delete()


def run_test(run_number):
    print(f"\n{'=' * 60}")
    print(f"  تشغيل الفحص رقم {run_number}")
    print('=' * 60)

    cleanup_test_data()

    # ====== [1] إعداد البيانات ======
    print("\n[1] إعداد البيانات الأساسية")

    currency = Currency.objects.filter(is_default=True).first()
    if not currency:
        currency = Currency.objects.first()

    cash_method = Payment_method.objects.filter(is_cash=True).first()
    if not cash_method:
        cash_method = Payment_method.objects.filter(
            name__in=['نقداً', 'نقدا', 'Cash']
        ).first()
    if not cash_method:
        print("  ✗ لا توجد طريقة دفع نقدي")
        cleanup_test_data()
        return 0

    supplier = User.objects.create(
        username=TEST_SUPPLIER,
        first_name=TEST_MARKER,
        last_name='المورد'
    )

    admin = User.objects.create_superuser(
        username=TEST_ADMIN,
        password='Test@12345',
        first_name=TEST_MARKER,
        last_name='المدير'
    )

    # المنتج بكمية ابتدائية 0
    product = Product.objects.create(
        product_name=TEST_PRODUCT,
        purch_price=Decimal('100.00'),
        sale_price=Decimal('150.00'),
        current_stock_quantity=Decimal('0.00'),
        average_purchase_cost=Decimal('0.00')
    )

    bc1 = Barcode.objects.create(
        barcode_in=f'{TEST_BARCODE_PREF}1',
        product=product, status='active', is_primary=False
    )
    bc2 = Barcode.objects.create(
        barcode_in=f'{TEST_BARCODE_PREF}2',
        product=product, status='active', is_primary=False
    )

    print(f"  المنتج: {product.product_name} | مخزون ابتدائي: 0")
    print(f"  الباركودات: {bc1.barcode_in}, {bc2.barcode_in}")

    # ====== [2] إنشاء فاتورة شراء ======
    print("\n[2] إنشاء فاتورة شراء (شراء 2 وحدة = 200)")

    purch = Purch.objects.create(
        purch_supplier=supplier,
        purch_currency=currency,
        purch_payment_method=cash_method,
        purch_tax_percentage=Decimal('0.00'),
        purch_discount=Decimal('0.00'),
        purch_addition=Decimal('0.00'),
        paid_amount=Decimal('200.00'),
        created_by=admin
    )

    purch_item = PurchItem.objects.create(
        purch=purch,
        product=product,
        item_name=product.product_name,
        purchased_quantity=Decimal('2.00'),
        unit_price=Decimal('100.00'),
        purch_currency=currency,
        exchange_rate_at_purchase=Decimal('1.00')
    )

    PurchItemBarcode.objects.create(
        purch_item=purch_item, barcode=bc1,
        quantity_used=Decimal('1.00'), barcode_status='active'
    )
    PurchItemBarcode.objects.create(
        purch_item=purch_item, barcode=bc2,
        quantity_used=Decimal('1.00'), barcode_status='active'
    )

    # تحديث المخزون (يضيف 2)
    purch_item.update_product_stock()
    purch.calculate_and_save_totals()
    purch.refresh_from_db()
    product.refresh_from_db()

    stock_after_purchase = product.current_stock_quantity
    print(f"  فاتورة: {purch.uniqueId} | كمية البند: 2")
    print(f"  المخزون بعد الشراء: {stock_after_purchase} (يجب 2)")

    check_1 = (stock_after_purchase == Decimal('2.00'))
    print(f"  ✓ الفحص 1: المخزون = 2 بعد الشراء: {check_1}")

    # ====== [3] حذف الفاتورة ======
    print("\n[3] حذف فاتورة الشراء عبر الفيوة الحية")

    client = Client()
    client.force_login(admin)

    response = client.post(f'/invoice/purch/{purch.slug}/delete/', {})
    print(f"  HTTP status: {response.status_code}")
    if hasattr(response, 'url'):
        print(f"  Redirect to: {response.url}")

    # ====== [4] فحص المخزون بعد الحذف ======
    print("\n[4] فحص المخزون بعد الحذف — يجب أن يكون 0 (لا -2)")

    product.refresh_from_db()
    stock_after_delete = product.current_stock_quantity
    print(f"  المخزون بعد الحذف: {stock_after_delete}")
    print(f"  (تقرير التدقيق الساكن توقع -2 = خصم مزدوج، لكن المثبت حياً 0)")

    check_2 = (stock_after_delete == Decimal('0.00'))
    print(f"  ✓ الفحص 2: المخزون = 0 بعد الحذف (لا خصم مزدوج): {check_2}")

    # ====== [5] التنظيف الذاتي ======
    print("\n[5] التحقق من التنظيف الذاتي")

    cleanup_test_data()
    cleanup_ok = (
        not Purch.objects.filter(
            Q(purch_supplier__username=TEST_SUPPLIER) |
            Q(created_by__username=TEST_ADMIN)
        ).exists() and
        not Product.objects.filter(product_name__startswith=TEST_MARKER).exists() and
        not User.objects.filter(username__in=[TEST_SUPPLIER, TEST_ADMIN]).exists() and
        not CashTransaction.objects.filter(notes__contains=TEST_MARKER).exists() and
        not Barcode.objects.filter(barcode_in__startswith=TEST_BARCODE_PREF).exists()
    )

    check_3 = cleanup_ok
    print(f"  ✓ الفحص 3: التنظيف الذاتي نجح (لا بقایا): {check_3}")

    # ====== [6] العداد النهائي ======
    print(f"\n[6] نتيجة التشغيل {run_number}")
    checks = [check_1, check_2, check_3]
    passed = sum(checks)
    for i, ok in enumerate(checks, 1):
        sign = '✓' if ok else '✗'
        print(f"  {sign} الفحص {i}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/3")
    return passed


# ==================== نقطة الدخول ====================
print('=' * 60)
print('  فحص حارسة 3 — حذف فاتورة الشراء بلا خصم مزدوج (3/3)')
print('=' * 60)
print(f"  المسار المُختبر: POST /invoice/purch/<slug>/delete/ → purch_delete")
print(f"  العلامة: {TEST_MARKER}")
print(f"  التوقع: بعد شراء كمية 2 ثم حذف الفاتورة، المخزون = 0 (لا -2)")

results = []
for i in [1, 2]:
    p = run_test(i)
    results.append(p)

print(f"\n{'=' * 60}")
print(f"  التشغيل 1: {results[0]}/3")
print(f"  التشغيل 2: {results[1]}/3")
same = (results[0] == results[1])
print(f"  متطابقة: {same}")
final = results[0]
print(f"  النتيجة النهائية: {final}/3")

if final == 3 and same:
    print(f"\n  ✅ PASS — الحارسة سليمة في التشغيلين بنفس النتيجة")
    print(f"  لا يوجد خصم مزدوج عند حذف فاتورة الشراء (المخزون 2 → 0 بالضبط)")
elif same:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")
print('=' * 60)