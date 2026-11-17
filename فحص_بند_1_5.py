"""
================================================================
فحص إثبات — بند 1.5 من تقرير التدقيق
================================================================
الموضوع: خصم مرتجعات المبيعات من total_sales في daily_sales_summary_report

الكود الحالي يحسب:
    total_sales = SUM(sale_final_total)  # من Sale فقط
تقرير التدقيق يقترح:
    total_sales -= SUM(return_final_total)  # خصم قيمة المرتجعات في نفس اليوم

السيناريوهات الثلاثة:
  1) مرتجع في نفس اليوم
     - بيع 10 @ 150 = 1500 (يوم 1)
     - مرتجع 2 = 300 في نفس اليوم
     - متوقع (مع الإصلاح): delta total_sales = +1200
     - بالعلة الحالية: delta total_sales = +1500

  2) مرتجع في يوم لاحق
     - بيع 10 @ 150 = 1500 (يوم 1)
     - مرتجع 2 = 300 (يوم 2)
     - الاستعلام عن يوم 1 فقط
     - متوقع: delta total_sales = +1500 (لا يتأثر - المرتجع خارج اليوم)
     - (نفس النتيجة مع/بدون إصلاح)

  3) مرتجع يتجاوز اليوم (مجموع يومين)
     - بيع 1: 10 @ 150 = 1500 (يوم 1)
     - بيع 2: 10 @ 150 = 1500 (يوم 2)
     - مرتجع 2 وحدة من فاتورة اليوم 1 (في اليوم 2)
     - الاستعلام عن مجموع اليومين
     - متوقع (مع الإصلاح): delta total_sales = +2700
     - بالعلة الحالية: delta total_sales = +3000

المنهجية:
  - ضرب الفيوة الحية عبر django.test.Client
  - التقاط context عبر monkey-patch لدالة render()
  - قياس baseline قبل، وقياس بعد، وحساب delta
  - 3 سيناريوهات × 3 قياسات = 9 فحوصات
  - يُشغَّل مرتين متتاليتين ويعطي النتيجة نفسها

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_1_5.py', encoding='utf-8').read())"
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


TEST_MARKER      = 'فحص_1_5'
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

    # المنتج بكمية 20 (يكفي 10+10 للسيناريو 3)
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


def get_report_values(client, query_date):
    """★ يستخدم monkey-patched render لالتقاط context ليوم واحد"""
    _captured_contexts.clear()

    url = f'/invoice/reports/daily-summary/?date={query_date.isoformat()}'

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

    return {
        'total_sales': ctx.get('total_sales') or Decimal('0.00'),
        'cash_received': ctx.get('cash_received') or Decimal('0.00'),
        'net_cash': ctx.get('net_cash') or Decimal('0.00'),
    }


def get_multi_day_values(client, dates):
    """مجموع قيم عدة أيام (للسيناريو 3)"""
    totals = {
        'total_sales': Decimal('0.00'),
        'cash_received': Decimal('0.00'),
        'net_cash': Decimal('0.00'),
    }
    for d in dates:
        v = get_report_values(client, d)
        if v is None:
            return None
        for k in totals:
            totals[k] += v[k]
    return totals


def run_scenario(num, title, sales_spec, returns_spec, query_dates, expected_deltas):
    print_header(f"السيناريو {num}: {title}")
    if len(query_dates) == 1:
        print(f"  اليوم المُختبر: {query_dates[0]}")
    else:
        print(f"  الأيام المُختبرَة: {query_dates}")
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
    if len(query_dates) == 1:
        before = get_report_values(client, query_dates[0])
    else:
        before = get_multi_day_values(client, query_dates)
    if before is None:
        print(f"  ⚠️ فشل قياس baseline — تخطي السيناريو")
        cleanup_test_data()
        return None
    print(f"  total_sales قبل: {before['total_sales']}")
    print(f"  cash_received قبل: {before['cash_received']}")
    print(f"  net_cash قبل: {before['net_cash']}")

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
    if len(query_dates) == 1:
        after = get_report_values(client, query_dates[0])
    else:
        after = get_multi_day_values(client, query_dates)
    if after is None:
        print(f"  ⚠️ فشل قياس بعد — تخطي السيناريو")
        cleanup_test_data()
        return None
    print(f"  total_sales بعد: {after['total_sales']}")
    print(f"  cash_received بعد: {after['cash_received']}")
    print(f"  net_cash بعد: {after['net_cash']}")

    print_step(5, "حساب delta والمقارنة")
    deltas = {
        'total_sales': after['total_sales'] - before['total_sales'],
        'cash_received': after['cash_received'] - before['cash_received'],
        'net_cash': after['net_cash'] - before['net_cash'],
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

    # ====== السيناريو 1: مرتجع في نفس اليوم ======
    expected_deltas_1 = {
        'total_sales': Decimal('1200.00'),     # 1500 - 300 (مع الإصلاح)
        'cash_received': Decimal('1500.00'),    # sale.paid_amount فقط (لا يتأثر)
        'net_cash': Decimal('1500.00'),         # cash_received - total_expenses (لا يتأثر)
    }
    r1 = run_scenario(
        1, "مرتجع في نفس اليوم",
        sales_spec=[(date(2026, 11, 15), Decimal('10.00'))],
        returns_spec=[(0, date(2026, 11, 15), Decimal('2.00'))],  # same day
        query_dates=[date(2026, 11, 15)],
        expected_deltas=expected_deltas_1
    )
    if r1: results.append(('سيناريو 1', r1))

    # ====== السيناريو 2: مرتجع في يوم لاحق ======
    expected_deltas_2 = {
        'total_sales': Decimal('1500.00'),     # لا مرتجع في هذا اليوم
        'cash_received': Decimal('1500.00'),
        'net_cash': Decimal('1500.00'),
    }
    r2 = run_scenario(
        2, "مرتجع في يوم لاحق",
        sales_spec=[(date(2026, 11, 15), Decimal('10.00'))],
        returns_spec=[(0, date(2026, 11, 16), Decimal('2.00'))],  # next day
        query_dates=[date(2026, 11, 15)],  # only day 1
        expected_deltas=expected_deltas_2
    )
    if r2: results.append(('سيناريو 2', r2))

    # ====== السيناريو 3: مرتجع يتجاوز اليوم (مجموع يومين) ======
    expected_deltas_3 = {
        'total_sales': Decimal('2700.00'),     # 3000 - 300 (مع الإصلاح)
        'cash_received': Decimal('3000.00'),    # 1500 + 1500
        'net_cash': Decimal('3000.00'),
    }
    r3 = run_scenario(
        3, "مرتجع يتجاوز اليوم (مجموع يومين)",
        sales_spec=[
            (date(2026, 11, 15), Decimal('10.00')),  # sale 1 day 1
            (date(2026, 11, 16), Decimal('10.00')),  # sale 2 day 2
        ],
        returns_spec=[(0, date(2026, 11, 16), Decimal('2.00'))],  # return on sale 1 in day 2
        query_dates=[date(2026, 11, 15), date(2026, 11, 16)],  # sum both days
        expected_deltas=expected_deltas_3
    )
    if r3: results.append(('سيناريو 3', r3))

    return results


# ==================== نقطة الدخول ====================
print_header("فحص إثبات — بند 1.5 من تقرير التدقيق")
print(f"  الموضوع: خصم مرتجعات المبيعات من total_sales في daily_sales_summary_report")
print(f"  المنهجية: 3 سيناريوهات × 3 قياسات × تشغيلان متطابقان")
print(f"  المسار المُختبر: GET /invoice/reports/daily-summary/?date=...")
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
print(f"  {'السيناريو':<35}  {'total_sales':<25}  {'cash_received':<25}  {'net_cash':<25}")
print(f"  {'-' * 110}")

for name, data in run1:
    parts = []
    for k in ['total_sales', 'cash_received', 'net_cash']:
        actual = data['deltas'][k]
        expected = data['expected'][k]
        ok = data['checks'][k]
        sign = '✓' if ok else '✗'
        parts.append(f"{sign} {actual:+}/{expected:+}")
    print(f"  {name:<35}  {parts[0]:<25}  {parts[1]:<25}  {parts[2]:<25}")

total_passed = 0
total_checks = 0
for name, data in run1:
    for k, ok in data['checks'].items():
        total_checks += 1
        if ok: total_passed += 1

print(f"\n  النتيجة النهائية: {total_passed}/{total_checks}")

# تحليل النتائج
cash_received_ok = all(
    run1[j][1]['checks'].get('cash_received') for j in range(len(run1))
)
net_cash_ok = all(
    run1[j][1]['checks'].get('net_cash') for j in range(len(run1))
)
total_sales_ok = all(
    run1[j][1]['checks'].get('total_sales') for j in range(len(run1))
)

if total_passed == total_checks and same_run:
    print(f"\n  ✅ PASS — الإصلاح موجود في الكود الحالي")
    print(f"  بند 1.5: total_sales يحسب صافي المبيعات بعد طرح مرتجعات اليوم")
    print(f"  النتيجة تطابق المعنى المحاسبي الصحيح في كل السيناريوهات الثلاثة")
elif cash_received_ok and net_cash_ok and not total_sales_ok and same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✓ cash_received صحيح (لا يتأثر بالإصلاح — sale.paid_amount فقط)")
    print(f"  ✓ net_cash صحيح رياضياً (cash_received - total_expenses، لا يشمل المرتجعات)")
    print(f"  ✗ total_sales لا يطرح مرتجعات المبيعات في نفس اليوم")
    print(f"  الفجوة في كل سيناريو = قيمة المرتجع غير المخصومة (300)")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
    print(f"  راجع الفحوصات الفاشلة أعلاه")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")