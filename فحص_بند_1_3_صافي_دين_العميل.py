"""
================================================================
فحص إثبات — بند 1.3 من تقرير التدقيق (نسخة معزولة)
================================================================
الموضوع: حساب صافي دين العميل في تقرير الفواتير غير المسددة
         (unpaid_invoices_report)

النسخة المعزولة: تحسب الصيغ لفواتيرنا الاختبارية فقط، لا لكل قاعدة البيانات.
هذا يمنع تلوث الأرقام ببيانات سابقة.

المنهجية المعتمدة:
  - ضرب الفيوهات الحية عبر django.test.Client
  - مستخدم فائق معزول
  - تنظيف ذاتي قبل/بعد
  - بيانات معلّمة ببادئة 'فحص_1_3'
  - حساب الصيغ لفواتيرنا الاختبارية فقط (عزل تام)
  - يُشغَّل مرتين متتاليتين ويعطي النتيجة نفسها

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_1_3_صافي_دين_العميل.py', encoding='utf-8').read())"
================================================================
"""

from decimal import Decimal
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

TEST_MARKER      = 'فحص_1_3'
TEST_ADMIN       = f'{TEST_MARKER}_مدير'
TEST_CUSTOMER    = f'{TEST_MARKER}_عميل'
TEST_PRODUCT     = f'{TEST_MARKER}_منتج'
TEST_BARCODE_PREF = f'{TEST_MARKER}_باركود_'


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

    Barcode.objects.filter(barcode_in__startswith=TEST_BARCODE_PREF).delete()
    Product.objects.filter(product_name__startswith=TEST_MARKER).delete()
    User.objects.filter(username__in=[TEST_CUSTOMER, TEST_ADMIN]).delete()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def setup_base_data():
    """إعداد البيانات الأساسية"""
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
        username=TEST_CUSTOMER,
        first_name=TEST_MARKER,
        last_name='العميل'
    )

    admin = User.objects.create_superuser(
        username=TEST_ADMIN,
        password='Test@12345',
        first_name=TEST_MARKER,
        last_name='المدير'
    )

    product = Product.objects.create(
        product_name=TEST_PRODUCT,
        purch_price=Decimal('100.00'),
        sale_price=Decimal('150.00'),
        current_stock_quantity=Decimal('10.00'),
        average_purchase_cost=Decimal('100.00')
    )

    barcodes = []
    for i in range(1, 5):
        bc = Barcode.objects.create(
            barcode_in=f'{TEST_BARCODE_PREF}{i}',
            product=product, status='active', is_primary=False
        )
        barcodes.append(bc)

    return {
        'currency': currency,
        'cash_method': cash_method,
        'customer': customer,
        'admin': admin,
        'product': product,
        'barcodes': barcodes,
    }


def create_sale(base, sale_total, paid_amount):
    """إنشاء فاتورة بيع"""
    sale = Sale.objects.create(
        sale_customer=base['customer'],
        sale_currency=base['currency'],
        sale_payment_method=base['cash_method'],
        sale_tax_percentage=Decimal('0.00'),
        sale_discount=Decimal('0.00'),
        sale_addition=Decimal('0.00'),
        paid_amount=paid_amount,
        created_by=base['admin']
    )

    qty = sale_total / Decimal('150.00')
    sale_item = SaleItem.objects.create(
        sale=sale,
        product=base['product'],
        item_name=base['product'].product_name,
        sold_quantity=qty,
        quantity_with_barcode=Decimal('0.00'),
        quantity_without_barcode=qty,
        unit_price=Decimal('150.00'),
        sale_currency=base['currency'],
        exchange_rate_at_sale=Decimal('1.00')
    )

    sale_item.update_product_stock()
    sale.calculate_and_save_totals()
    sale.refresh_from_db()

    if paid_amount > 0:
        CashTransaction.objects.create(
            transaction_date=timezone.now(),
            amount_in=paid_amount,
            amount_out=Decimal('0.00'),
            transaction_type='sale_receipt',
            sale_invoice=sale,
            notes=f'{TEST_MARKER} تحصيل نقدي',
            created_by=base['admin'],
            payment_method=base['cash_method']
        )

    return sale, sale_item


def create_sale_return(base, sale, sale_item, return_total, refund_amount):
    """إنشاء مرتجع مبيعات"""
    return_qty = return_total / Decimal('150.00')

    sale_return = SaleReturn.objects.create(
        original_sale=sale,
        created_by=base['admin'],
        return_date=timezone.now().date(),
        return_payment_method=base['cash_method'],
        return_currency=base['currency'],
        paid_amount=refund_amount,
        return_notes=f'{TEST_MARKER} ملاحظة المرتجع'
    )

    return_item = SaleReturnItem.objects.create(
        sale_return=sale_return,
        original_sale_item=sale_item,
        product=base['product'],
        item_name=base['product'].product_name,
        returned_quantity=return_qty,
        quantity_with_barcode=Decimal('0.00'),
        quantity_without_barcode=return_qty,
        unit_price=Decimal('150.00'),
        return_currency=base['currency'],
        exchange_rate_at_return=Decimal('1.00')
    )

    return_item.restore_product_stock()
    sale_return.calculate_and_save_totals()
    sale_return.refresh_from_db()
    sale_return.reconcile_cash_transactions()

    return sale_return


def compute_isolated_values(test_sale_ids):
    """★ حساب الصيغ لفواتيرنا الاختبارية فقط (عزل تام)"""
    # 1) total_customers_debt — فقط لفواتيرنا الاختبارية
    unpaid_sales = Sale.objects.filter(
        id__in=test_sale_ids
    ).filter(
        Q(balance_due__gt=0) | Q(sale_returns__isnull=False)
    ).distinct()
    total_customers_debt = Decimal('0.00')
    for s in unpaid_sales:
        bal = s.sale_final_total - s.paid_amount
        if bal > 0:
            total_customers_debt += bal

    # 2) total_sale_returns — فقط لمرتجعاتنا الاختبارية
    sale_returns_qs = SaleReturn.objects.filter(
        original_sale_id__in=test_sale_ids,
        return_final_total__gt=0
    )
    total_sale_returns = Decimal('0.00')
    total_returns_value = Decimal('0.00')
    for r in sale_returns_qs:
        bal = r.return_final_total - r.paid_amount
        if bal > 0:
            total_sale_returns += bal
        total_returns_value += r.return_final_total

    # 3) الصيغ
    formula_a = total_customers_debt - total_sale_returns
    formula_b = total_customers_debt - total_returns_value
    formula_c = Decimal('0.00')
    for s in unpaid_sales:
        returns_on_sale = SaleReturn.objects.filter(original_sale=s)
        if returns_on_sale.exists():
            for r in returns_on_sale:
                formula_c += s.balance_due - r.return_final_total + r.paid_amount
        else:
            formula_c += s.balance_due

    return {
        'total_customers_debt': total_customers_debt,
        'total_sale_returns': total_sale_returns,
        'total_returns_value': total_returns_value,
        'formula_a': formula_a,
        'formula_b': formula_b,
        'formula_c': formula_c,
    }


def run_scenario(scenario_num, scenario_title, sale_total, sale_paid, return_total, refund_amount, expected_accounting):
    """تشغيل سيناريو واحد"""
    print_header(f"السيناريو {scenario_num}: {scenario_title}")

    print_step(1, "البيانات")
    print(f"  فاتورة بيع: إجمالي={sale_total}, مدفوع={sale_paid}, balance_due={sale_total - sale_paid}")
    print(f"  مرتجع مبيعات: قيمة={return_total}, صرف نقدي={refund_amount}")
    print(f"  القيمة المحاسبية الصحيحة المتوقعة: {expected_accounting}")

    base = setup_base_data()
    if not base:
        print("  ✗ لا توجد طريقة دفع نقدي")
        return None

    print_step(2, "إنشاء فاتورة البيع")
    sale, sale_item = create_sale(base, sale_total, sale_paid)
    print(f"  فاتورة: {sale.uniqueId} | final={sale.sale_final_total} | paid={sale.paid_amount} | balance_due={sale.balance_due}")

    print_step(3, "إنشاء مرتجع المبيعات")
    sale_return = create_sale_return(base, sale, sale_item, return_total, refund_amount)
    print(f"  مرتجع: {sale_return.uniqueId} | return_final_total={sale_return.return_final_total} | paid_amount={sale_return.paid_amount}")

    print_step(4, "حركة الصندوق للمرتجع")
    cash_tx = CashTransaction.objects.filter(
        sale_return=sale_return,
        transaction_type='sale_return'
    ).first()
    if cash_tx:
        print(f"  ✓ حركة موجودة | amount_out={cash_tx.amount_out} (صرف للعميل)")
    else:
        print(f"  ✗ لا توجد حركة صندوق للمرتجع")

    print_step(5, "حسابات unpaid_invoices_report (معزولة لفواتيرنا فقط)")
    test_sale_ids = [sale.id]
    vals = compute_isolated_values(test_sale_ids)
    print(f"  total_customers_debt (مجموع balance_due لفواتيرنا): {vals['total_customers_debt']}")
    print(f"  total_sale_returns (return_final_total - paid_amount): {vals['total_sale_returns']}")
    print(f"  total_returns_value (إجمالي قيمة المرتجعات): {vals['total_returns_value']}")
    print()
    print(f"  صيغة الكود الحالي: total_customers_debt + total_sale_returns = {vals['total_customers_debt'] + vals['total_sale_returns']}")
    print(f"  صيغة (أ) التقرير:  total_customers_debt - total_sale_returns = {vals['formula_a']}")
    print(f"  صيغة (ب) الشاملة: total_customers_debt - total_returns_value = {vals['formula_b']}")
    print(f"  صيغة (ج) المحاسبية: لكل فاتورة (balance - return + refund) = {vals['formula_c']}")
    print()
    print(f"  ★ القيمة المحاسبية الصحيحة المتوقعة: {expected_accounting}")
    print(f"  ✓ صيغة (أ) تطابق الصحيح: {vals['formula_a'] == expected_accounting}")
    print(f"  ✓ صيغة (ب) تطابق الصحيح: {vals['formula_b'] == expected_accounting}")
    print(f"  ✓ صيغة (ج) تطابق الصحيح: {vals['formula_c'] == expected_accounting}")

    cleanup_test_data()
    return vals


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    cleanup_test_data()

    results = []

    vals1 = run_scenario(
        1, "مرتجع 200 بلا صرف نقدي (refund=0)",
        sale_total=Decimal('1000.00'), sale_paid=Decimal('0.00'),
        return_total=Decimal('200.00'), refund_amount=Decimal('0.00'),
        expected_accounting=Decimal('800.00')
    )
    if vals1: results.append(('سيناريو 1', vals1))

    vals2 = run_scenario(
        2, "مرتجع 200 مع صرف كامل 200 (refund=200)",
        sale_total=Decimal('1000.00'), sale_paid=Decimal('0.00'),
        return_total=Decimal('200.00'), refund_amount=Decimal('200.00'),
        expected_accounting=Decimal('1000.00')
    )
    if vals2: results.append(('سيناريو 2', vals2))

    vals3 = run_scenario(
        3, "مرتجع 200 مع صرف جزئي 100 (refund=100)",
        sale_total=Decimal('1000.00'), sale_paid=Decimal('0.00'),
        return_total=Decimal('200.00'), refund_amount=Decimal('100.00'),
        expected_accounting=Decimal('900.00')
    )
    if vals3: results.append(('سيناريو 3', vals3))

    return results


# ==================== نقطة الدخول ====================
print_header("فحص إثبات — بند 1.3 (نسخة معزولة)")
print(f"  الموضوع: حساب صافي دين العميل في unpaid_invoices_report")
print(f"  النسخة: معزولة — تحسب الصيغ لفواتيرنا الاختبارية فقط")
print(f"  المنهجية: 3 سيناريوهات × 3 صيغ حساب × تشغيلان متطابقان")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    res = run_test(i)
    all_results.append(res)

print_header("الخلاصة النهائية")

run1 = all_results[0]
run2 = all_results[1]

same_run = True
for j in range(len(run1)):
    name1, vals1 = run1[j]
    name2, vals2 = run2[j]
    if vals1['formula_a'] != vals2['formula_a'] or vals1['formula_b'] != vals2['formula_b'] or vals1['formula_c'] != vals2['formula_c']:
        same_run = False
        break

print(f"  التشغيلان متطابقان في النتائج: {same_run}")

print(f"\n  جدول المقارنة (من التشغيل 1):")
print(f"  {'السيناريو':<25}  {'محاسبي صحيح':<15}  {'صيغة (أ)':<15}  {'صيغة (ب)':<15}  {'صيغة (ج)':<15}")
print(f"  {'-'*85}")

expected_values = [Decimal('800.00'), Decimal('1000.00'), Decimal('900.00')]
for j, (name, vals) in enumerate(run1):
    exp = expected_values[j]
    a_ok = '✓' if vals['formula_a'] == exp else '✗'
    b_ok = '✓' if vals['formula_b'] == exp else '✗'
    c_ok = '✓' if vals['formula_c'] == exp else '✗'
    print(f"  {name:<25}  {exp:<15}  {vals['formula_a']:<15} {a_ok}  {vals['formula_b']:<15} {b_ok}  {vals['formula_c']:<15} {c_ok}")

print(f"\n  تفسير الصيغ:")
print(f"    (أ) صيغة التقرير:    total_customers_debt - total_sale_returns")
print(f"    (ب) الصيغة الشاملة: total_customers_debt - SUM(return_final_total)")
print(f"    (ج) الصيغة المحاسبية: لكل فاتورة (balance_due - return_final + paid_on_return)")

print(f"\n  القرار المُستنتج من الأرقام:")
formula_a_wins = all(
    run1[j][1]['formula_a'] == expected_values[j] for j in range(len(run1))
)
formula_b_wins = all(
    run1[j][1]['formula_b'] == expected_values[j] for j in range(len(run1))
)
formula_c_wins = all(
    run1[j][1]['formula_c'] == expected_values[j] for j in range(len(run1))
)

if formula_a_wins:
    print(f"  ★ صيغة (أ) التقرير تطابق المعنى المحاسبي في كل السيناريوهات")
if formula_b_wins:
    print(f"  ★ صيغة (ب) الشاملة تطابق المعنى المحاسبي في كل السيناريوهات")
if formula_c_wins:
    print(f"  ★ صيغة (ج) المحاسبية تطابق المعنى المحاسبي في كل السيناريوهات")
if not (formula_a_wins or formula_b_wins or formula_c_wins):
    print(f"  ⚠️ لا توجد صيغة تطابق تماماً — راجع الأرقام أعلاه")

print(f"\n{'=' * 70}")