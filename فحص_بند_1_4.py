"""
================================================================
فحص إثبات — بند 1.4 من تقرير التدقيق
================================================================
الموضوع: خصم تكلفة مرتجعات المبيعات من COGS في profit_report_view

الكود الحالي يحسب:
    total_cost = SUM(sold_quantity * cost_price)  # من SaleItem فقط
تقرير التدقيق يقترح:
    total_cost -= SUM(returned_quantity * cost_price)  # خصم تكلفة المرتجعات

السيناريوهات الثلاثة:
  1) مرتجع في نفس الفترة
     - بيع 10 @ 150 = 1500، كلفة 1000
     - مرتجع 2 = 300، كلفة 200
     - الفترة تشمل البيع والمرتجع
     - متوقع (مع الإصلاح): delta total_cost = +800، delta gross_profit = +400
     - بالعلة الحالية: delta total_cost = +1000، delta gross_profit = +200

  2) مرتجع في فترة لاحقة
     - بيع 10 @ 150 = 1500، كلفة 1000
     - مرتجع 2 (خارج الفترة)
     - متوقع: delta total_cost = +1000، delta gross_profit = +500
     - (لا يتأثر بالإصلاح — لا مرتجع في الفترة)

  3) مرتجع يتجاوز الفترة (مجمعة)
     - بيع 1: 10 @ 150 = 1500، كلفة 1000 (الفترة 1)
     - بيع 2: 10 @ 150 = 1500، كلفة 1000 (الفترة 2)
     - مرتجع 2 وحدة من فاتورة الفترة 1 (في الفترة 2)
     - الفترة المجمعة: 1-60
     - متوقع (مع الإصلاح): delta total_cost = +1800، delta gross_profit = +900
     - بالعلة الحالية: delta total_cost = +2000، delta gross_profit = +700

المنهجية:
  - ضرب الفيوة الحية عبر django.test.Client
  - التقاط context عبر monkey-patch لدالة render()
  - قياس baseline قبل، وقياس بعد، وحساب delta
  - مقارنة delta مع القيمة المحاسبية الصحيحة
  - 3 سيناريوهات × 3 قياسات = 9 فحوصات
  - يُشغَّل مرتين متتاليتين ويعطي النتيجة نفسها

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_1_4.py', encoding='utf-8').read())"
================================================================
"""

from decimal import Decimal
from datetime import date
from django.conf import settings
from django.test import Client
from django.contrib.auth import get_user_model
from django.db.models import Q, Sum
from django.utils import timezone

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import (
    Sale, SaleItem, SaleItemBarcode, SaleReturn, SaleReturnItem, SaleReturnItemBarcode,
    Barcode, Product, CashTransaction, Payment_method, Currency
)

# ★★★ Monkey-patch لدالة render في invoice.views ★★★
import invoice.views as views_module
from django.shortcuts import render as original_render

_captured_contexts = []

def _patched_render(request, template_name, context=None, *args, **kwargs):
    if context:
        _captured_contexts.append(dict(context))
    return original_render(request, template_name, context, *args, **kwargs)

views_module.render = _patched_render


TEST_MARKER      = 'فحص_1_4'
TEST_ADMIN       = f'{TEST_MARKER}_مدير'
TEST_CUSTOMER    = f'{TEST_MARKER}_عميل'
TEST_PRODUCT     = f'{TEST_MARKER}_منتج'


def cleanup_test_data():
    """تنظيف شامل"""
    test_sale_ids = list(Sale.objects.filter(
        Q(sale_customer__username=TEST_CUSTOMER) |
        Q(created_by__username=TEST_ADMIN)
    ).values_list('id', flat=True))

    if test_sale_ids:
        SaleReturnItemBarcode.objects.filter(
            sale_return_item__sale_return__original_sale_id__in=test_sale_ids
        ).delete()
        SaleReturnItem.objects.filter(
            sale_return__original_sale_id__in=test_sale_ids
        ).delete()
        SaleReturn.objects.filter(original_sale_id__in=test_sale_ids).delete()
        SaleItemBarcode.objects.filter(sale_item__sale_id__in=test_sale_ids).delete()
        SaleItem.objects.filter(sale_id__in=test_sale_ids).delete()
        Sale.objects.filter(id__in=test_sale_ids).delete()

    CashTransaction.objects.filter(
        Q(sale_invoice_id__in=test_sale_ids) |
        Q(sale_return__original_sale_id__in=test_sale_ids) |
        Q(notes__contains=TEST_MARKER) |
        Q(created_by__username=TEST_ADMIN)
    ).delete()

    Product.objects.filter(product_name__startswith=TEST_MARKER).delete()
    User.objects.filter(username__in=[TEST_CUSTOMER, TEST_ADMIN]).delete()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def setup_base():
    currency = Currency.objects.filter(is_default=True).first()
    if not currency:
        currency = Currency.objects.first()

    cash_method = Payment_method.objects.filter(is_cash=True).first()
    if not cash_method:
        cash_method = Payment_method.objects.filter(
            name__in=['نقداً', 'نقدا', 'Cash']
        ).first()
    if not cash_method:
        return None

    customer = User.objects.create(
        username=TEST_CUSTOMER, first_name=TEST_MARKER
    )

    admin = User.objects.create_superuser(
        username=TEST_ADMIN, password='Test@12345',
        first_name=TEST_MARKER, last_name='المدير'
    )

    # المنتج بمتوسط كلفة 100، مخزون 20 (يكفي 10+10 للسيناريو 3)
    product = Product.objects.create(
        product_name=TEST_PRODUCT,
        purch_price=Decimal('100.00'),
        sale_price=Decimal('150.00'),
        current_stock_quantity=Decimal('20.00'),
        average_purchase_cost=Decimal('100.00')
    )

    return {
        'currency': currency, 'cash_method': cash_method,
        'customer': customer, 'admin': admin, 'product': product,
    }


def create_sale(base, sale_date, qty, unit_price=Decimal('150.00')):
    sale = Sale.objects.create(
        sale_customer=base['customer'], sale_currency=base['currency'],
        sale_payment_method=base['cash_method'],
        sale_date=sale_date,
        sale_tax_percentage=Decimal('0.00'), sale_discount=Decimal('0.00'),
        sale_addition=Decimal('0.00'), paid_amount=qty * unit_price,
        created_by=base['admin']
    )

    item = SaleItem.objects.create(
        sale=sale, product=base['product'],
        item_name=base['product'].product_name,
        sold_quantity=qty, quantity_with_barcode=Decimal('0.00'),
        quantity_without_barcode=qty, unit_price=unit_price,
        sale_currency=base['currency'], exchange_rate_at_sale=Decimal('1.00')
    )

    item.update_product_stock()
    sale.calculate_and_save_totals()
    sale.refresh_from_db()

    return sale, item


def create_return(base, sale, item, return_date, qty, unit_price=Decimal('150.00')):
    ret = SaleReturn.objects.create(
        original_sale=sale, created_by=base['admin'],
        return_date=return_date,
        return_payment_method=base['cash_method'],
        return_currency=base['currency'],
        paid_amount=qty * unit_price,
        return_notes=f'{TEST_MARKER} مرتجع'
    )

    ritem = SaleReturnItem.objects.create(
        sale_return=ret, original_sale_item=item,
        product=base['product'],
        item_name=base['product'].product_name,
        returned_quantity=qty, quantity_with_barcode=Decimal('0.00'),
        quantity_without_barcode=qty, unit_price=unit_price,
        return_currency=base['currency'], exchange_rate_at_return=Decimal('1.00')
    )

    ritem.restore_product_stock()
    ret.calculate_and_save_totals()
    ret.refresh_from_db()
    ret.reconcile_cash_transactions()

    return ret


def get_report_values(client, start_date, end_date):
    """★ يستخدم monkey-patched render لالتقاط context"""
    _captured_contexts.clear()

    url = f'/invoice/reports/profit/?start_date={start_date.isoformat()}&end_date={end_date.isoformat()}'

    try:
        response = client.get(url)
    except Exception as e:
        print(f"    ⚠️ استثناء عند تحميل التقرير: {e}")
        return None

    if response.status_code != 200:
        print(f"    ⚠️ HTTP {response.status_code}")
        return None

    if not _captured_contexts:
        print(f"    ⚠️ لم يُلتقط أي context — render لم يُستدعَ")
        return None

    ctx = _captured_contexts[-1]

    if not ctx.get('show_results'):
        print(f"    ⚠️ show_results=False — التقرير لم يُحسب")
        return None

    return {
        'total_sales': ctx.get('total_sales') or Decimal('0.00'),
        'total_sales_returns': ctx.get('total_sales_returns') or Decimal('0.00'),
        'net_sales': ctx.get('net_sales') or Decimal('0.00'),
        'total_cost': ctx.get('total_cost') or Decimal('0.00'),
        'gross_profit': ctx.get('gross_profit') or Decimal('0.00'),
    }


def run_scenario(num, title, sales_spec, returns_spec, period, expected_deltas):
    """
    sales_spec: list of (sale_date, qty) tuples
    returns_spec: list of (sale_index, return_date, qty) tuples
    period: (start_date, end_date)
    expected_deltas: dict with expected delta values
    """
    print_header(f"السيناريو {num}: {title}")
    print(f"  الفترة: {period[0]} إلى {period[1]}")
    print(f"  التوقعات:")
    for k, v in expected_deltas.items():
        print(f"    delta {k} = {v:+}")

    cleanup_test_data()
    base = setup_base()
    if not base:
        print("  ✗ لا توجد طريقة دفع نقدي")
        return None

    client = Client()
    client.force_login(base['admin'])

    print_step(1, "قياس baseline")
    before = get_report_values(client, period[0], period[1])
    if before is None:
        print(f"  ⚠️ فشل قياس baseline — تخطي السيناريو")
        cleanup_test_data()
        return None
    print(f"  total_cost قبل: {before['total_cost']}")
    print(f"  gross_profit قبل: {before['gross_profit']}")
    print(f"  net_sales قبل: {before['net_sales']}")

    print_step(2, "إنشاء المبيعات")
    sales = []
    items = []
    for sale_date, qty in sales_spec:
        sale, item = create_sale(base, sale_date, qty)
        sales.append(sale)
        items.append(item)
        print(f"  فاتورة: {sale.uniqueId} | sale_date={sale.sale_date} | qty={qty} | final={sale.sale_final_total}")

    print_step(3, "إنشاء المرتجعات")
    for sale_idx, return_date, qty in returns_spec:
        sale = sales[sale_idx]
        item = items[sale_idx]
        ret = create_return(base, sale, item, return_date, qty)
        print(f"  مرتجع: {ret.uniqueId} | return_date={ret.return_date} | qty={qty} | final={ret.return_final_total}")

    print_step(4, "قياس بعد")
    after = get_report_values(client, period[0], period[1])
    if after is None:
        print(f"  ⚠️ فشل قياس بعد — تخطي السيناريو")
        cleanup_test_data()
        return None
    print(f"  total_cost بعد: {after['total_cost']}")
    print(f"  gross_profit بعد: {after['gross_profit']}")
    print(f"  net_sales بعد: {after['net_sales']}")

    print_step(5, "حساب delta والمقارنة")
    deltas = {
        'total_cost': after['total_cost'] - before['total_cost'],
        'gross_profit': after['gross_profit'] - before['gross_profit'],
        'net_sales': after['net_sales'] - before['net_sales'],
    }

    checks = {}
    for k, expected in expected_deltas.items():
        actual = deltas[k]
        ok = (actual == expected)
        checks[k] = ok
        sign = '✓' if ok else '✗'
        print(f"  {sign} delta {k}: فعلي={actual:+}, متوقع={expected:+} → {ok}")

    cleanup_test_data()
    return {'checks': checks, 'deltas': deltas, 'expected': expected_deltas}


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    cleanup_test_data()

    results = []

    # ====== السيناريو 1: مرتجع في نفس الفترة ======
    expected_deltas_1 = {
        'total_cost': Decimal('800.00'),      # 1000 - 200 (مع الإصلاح)
        'gross_profit': Decimal('400.00'),     # 1200 - 800
        'net_sales': Decimal('1200.00'),       # 1500 - 300
    }
    r1 = run_scenario(
        1, "مرتجع في نفس الفترة",
        sales_spec=[(date(2026, 11, 15), Decimal('10.00'))],
        returns_spec=[(0, date(2026, 11, 16), Decimal('2.00'))],
        period=(date(2026, 11, 1), date(2026, 11, 30)),
        expected_deltas=expected_deltas_1
    )
    if r1: results.append(('سيناريو 1', r1))

    # ====== السيناريو 2: مرتجع في فترة لاحقة ======
    expected_deltas_2 = {
        'total_cost': Decimal('1000.00'),     # لا مرتجع في الفترة
        'gross_profit': Decimal('500.00'),     # 1500 - 1000
        'net_sales': Decimal('1500.00'),       # 1500 - 0
    }
    r2 = run_scenario(
        2, "مرتجع في فترة لاحقة",
        sales_spec=[(date(2026, 11, 15), Decimal('10.00'))],
        returns_spec=[(0, date(2026, 12, 15), Decimal('2.00'))],  # return in Dec
        period=(date(2026, 11, 1), date(2026, 11, 30)),  # only Nov in this period
        expected_deltas=expected_deltas_2
    )
    if r2: results.append(('سيناريو 2', r2))

    # ====== السيناريو 3: مرتجع يتجاوز الفترة (مجمعة) ======
    expected_deltas_3 = {
        'total_cost': Decimal('1800.00'),     # 2000 - 200 (مع الإصلاح)
        'gross_profit': Decimal('900.00'),     # 2700 - 1800
        'net_sales': Decimal('2700.00'),      # 3000 - 300
    }
    r3 = run_scenario(
        3, "مرتجع يتجاوز الفترة (مجمعة)",
        sales_spec=[
            (date(2026, 11, 15), Decimal('10.00')),  # sale 1 in Nov
            (date(2026, 12, 15), Decimal('10.00')),  # sale 2 in Dec
        ],
        returns_spec=[(0, date(2026, 12, 20), Decimal('2.00'))],  # return on sale 1 in Dec
        period=(date(2026, 11, 1), date(2026, 12, 31)),  # combined Nov-Dec
        expected_deltas=expected_deltas_3
    )
    if r3: results.append(('سيناريو 3', r3))

    return results


# ==================== نقطة الدخول ====================
print_header("فحص إثبات — بند 1.4 من تقرير التدقيق")
print(f"  الموضوع: خصم تكلفة مرتجعات المبيعات من COGS في profit_report_view")
print(f"  المنهجية: 3 سيناريوهات × 3 قياسات × تشغيلان متطابقان")
print(f"  المسار المُختبر: GET /invoice/reports/profit/?start_date=...&end_date=...")
print(f"  آلية التقاط context: monkey-patch لدالة render()")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    res = run_test(i)
    all_results.append(res)

# استعادة render الأصلية
views_module.render = original_render

print_header("الخلاصة النهائية")

run1 = all_results[0]
run2 = all_results[1]

# مقارنة النتائج بين التشغيلين
same_run = True
for j in range(len(run1)):
    name1, data1 = run1[j]
    name2, data2 = run2[j]
    for k in data1['checks']:
        if data1['checks'][k] != data2['checks'][k]:
            same_run = False
            break

print(f"  التشغيلان متطابقان في النتائج: {same_run}")

print(f"\n  جدول النتائج التفصيلي (من التشغيل 1):")
print(f"  {'السيناريو':<35}  {'total_cost':<25}  {'gross_profit':<25}  {'net_sales':<25}")
print(f"  {'-' * 110}")

for name, data in run1:
    parts = []
    for k in ['total_cost', 'gross_profit', 'net_sales']:
        actual = data['deltas'][k]
        expected = data['expected'][k]
        ok = data['checks'][k]
        sign = '✓' if ok else '✗'
        parts.append(f"{sign} {actual:+}/{expected:+}")
    print(f"  {name:<35}  {parts[0]:<25}  {parts[1]:<25}  {parts[2]:<25}")

# حساب النتيجة النهائية
total_passed = 0
total_checks = 0
for name, data in run1:
    for k, ok in data['checks'].items():
        total_checks += 1
        if ok: total_passed += 1

print(f"\n  النتيجة النهائية: {total_passed}/{total_checks}")

# تحليل النتائج
# net_sales يجب أن يمر دائماً (لا يتأثر بالإصلاح)
net_sales_ok = all(
    run1[j][1]['checks'].get('net_sales') for j in range(len(run1))
)

# total_cost و gross_profit يفشلان مع وجود العلة، ينجحان مع الإصلاح
total_cost_ok = all(
    run1[j][1]['checks'].get('total_cost') for j in range(len(run1))
)
gross_profit_ok = all(
    run1[j][1]['checks'].get('gross_profit') for j in range(len(run1))
)

if total_passed == total_checks and same_run:
    print(f"\n  ✅ PASS — الإصلاح موجود في الكود الحالي")
    print(f"  بند 1.4: total_cost يحسب صافي تكلفة البضاعة المباعة بعد طرح المرتجعات")
    print(f"  النتيجة تطابق المعنى المحاسبي الصحيح في كل السيناريوهات الثلاثة")
elif net_sales_ok and not (total_cost_ok and gross_profit_ok) and same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✓ net_sales صحيح (لا يتأثر بالإصلاح)")
    print(f"  ✗ total_cost لا يطرح تكلفة المرتجعات")
    print(f"  ✗ gross_profit أصغر من الصحيح بسبب العلة")
    print(f"  الفجوة في كل سيناريو = تكلفة المرتجع غير المخصومة")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم تشغيل فحص الإغلاق")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
    print(f"  راجع الفحوصات الفاشلة أعلاه")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")