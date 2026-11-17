"""
================================================================
فحص إغلاق — بند 1.3 من تقرير التدقيق (محصّن بالـ monkey-patch)
================================================================
الموضوع: التحقق من إصلاح صافي دين العميل والمورد في unpaid_invoices_report

المنهجية:
  - قياس baseline قبل إنشاء أي بيانات
  - إنشاء سيناريو (فاتورة + مرتجع)
  - التقاط context عبر monkey-patch لدالة render()
  - حساب الفرق عن baseline
  - المقارنة مع القيمة المحاسبية الصحيحة
  - 3 سيناريوهات للعميل + 3 للمورد = 6 سيناريوهات
  - يُشغَّل مرتين متتاليتين ويعطي النتيجة نفسها

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_إغلاق_بند_1_3.py', encoding='utf-8').read())"
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
    Purch, PurchItem, PurchItemBarcode, PurchaseReturn, PurchaseReturnItem, PurchaseReturnItemBarcode,
    Barcode, Product, CashTransaction, Payment_method, Currency
)

# ★★★ Monkey-patch لدالة render في invoice.views ★★★
# هذا يلتقط الـ context المارّ للقالب بصرف النظر عن إعدادات Django
import invoice.views as views_module
from django.shortcuts import render as original_render

_captured_contexts = []

def _patched_render(request, template_name, context=None, *args, **kwargs):
    if context:
        _captured_contexts.append(dict(context))
    return original_render(request, template_name, context, *args, **kwargs)

views_module.render = _patched_render


TEST_MARKER      = 'فحص_1_3_إغلاق'
TEST_ADMIN       = f'{TEST_MARKER}_مدير'
TEST_CUSTOMER    = f'{TEST_MARKER}_عميل'
TEST_SUPPLIER    = f'{TEST_MARKER}_مورد'
TEST_PRODUCT_S   = f'{TEST_MARKER}_منتج_بيع'
TEST_PRODUCT_P   = f'{TEST_MARKER}_منتج_شراء'
TEST_BARCODE_PREF = f'{TEST_MARKER}_باركود_'


def cleanup_test_data():
    test_sale_ids = list(Sale.objects.filter(
        Q(sale_customer__username=TEST_CUSTOMER) |
        Q(created_by__username=TEST_ADMIN)
    ).values_list('id', flat=True))
    test_purch_ids = list(Purch.objects.filter(
        Q(purch_supplier__username=TEST_SUPPLIER) |
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

    if test_purch_ids:
        PurchaseReturnItemBarcode.objects.filter(
            purchase_return_item__purchase_return__original_purchase_id__in=test_purch_ids
        ).delete()
        PurchaseReturnItem.objects.filter(
            purchase_return__original_purchase_id__in=test_purch_ids
        ).delete()
        PurchaseReturn.objects.filter(original_purchase_id__in=test_purch_ids).delete()
        PurchItemBarcode.objects.filter(purch_item__purch_id__in=test_purch_ids).delete()
        PurchItem.objects.filter(purch_id__in=test_purch_ids).delete()
        Purch.objects.filter(id__in=test_purch_ids).delete()

    CashTransaction.objects.filter(
        Q(sale_invoice_id__in=test_sale_ids) |
        Q(purchase_invoice_id__in=test_purch_ids) |
        Q(sale_return__original_sale_id__in=test_sale_ids) |
        Q(purchase_return__original_purchase_id__in=test_purch_ids) |
        Q(notes__contains=TEST_MARKER) |
        Q(created_by__username=TEST_ADMIN)
    ).delete()

    Barcode.objects.filter(barcode_in__startswith=TEST_BARCODE_PREF).delete()
    Product.objects.filter(product_name__startswith=TEST_MARKER).delete()
    User.objects.filter(username__in=[TEST_CUSTOMER, TEST_SUPPLIER, TEST_ADMIN]).delete()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def get_report_values(client):
    """★ يستخدم monkey-patched render لالتقاط context"""
    # مسح أي contexts سابقة
    _captured_contexts.clear()

    try:
        response = client.get('/invoice/reports/unpaid-invoices/')
    except Exception as e:
        print(f"    ⚠️ استثناء عند تحميل التقرير: {e}")
        return None

    if response.status_code != 200:
        print(f"    ⚠️ HTTP {response.status_code}")
        return None

    # ★ قراءة context من القائمة الملتقطة
    if not _captured_contexts:
        print(f"    ⚠️ لم يُلتقط أي context — render لم يُستدعَ")
        return None

    # نأخذ آخر context (الفiew قد يستدعي render مرة واحدة فقط)
    ctx = _captured_contexts[-1]

    try:
        return {
            'net_customer_debt': ctx.get('net_customer_debt'),
            'net_supplier_debt': ctx.get('net_supplier_debt'),
        }
    except Exception as e:
        print(f"    ⚠️ خطأ في قراءة context: {e}")
        return None


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

    customer = User.objects.create(username=TEST_CUSTOMER, first_name=TEST_MARKER)
    supplier = User.objects.create(username=TEST_SUPPLIER, first_name=TEST_MARKER)
    admin = User.objects.create_superuser(
        username=TEST_ADMIN, password='Test@12345',
        first_name=TEST_MARKER, last_name='المدير'
    )

    product_sale = Product.objects.create(
        product_name=TEST_PRODUCT_S,
        purch_price=Decimal('100.00'), sale_price=Decimal('150.00'),
        current_stock_quantity=Decimal('10.00'),
        average_purchase_cost=Decimal('100.00')
    )
    product_purch = Product.objects.create(
        product_name=TEST_PRODUCT_P,
        purch_price=Decimal('100.00'), sale_price=Decimal('150.00'),
        current_stock_quantity=Decimal('0.00'),
        average_purchase_cost=Decimal('0.00')
    )

    return {
        'currency': currency, 'cash_method': cash_method,
        'customer': customer, 'supplier': supplier, 'admin': admin,
        'product_sale': product_sale, 'product_purch': product_purch,
    }


def create_sale(base, total, paid):
    sale = Sale.objects.create(
        sale_customer=base['customer'], sale_currency=base['currency'],
        sale_payment_method=base['cash_method'],
        sale_tax_percentage=Decimal('0.00'), sale_discount=Decimal('0.00'),
        sale_addition=Decimal('0.00'), paid_amount=paid, created_by=base['admin']
    )
    qty = total / Decimal('150.00')
    item = SaleItem.objects.create(
        sale=sale, product=base['product_sale'],
        item_name=base['product_sale'].product_name,
        sold_quantity=qty, quantity_with_barcode=Decimal('0.00'),
        quantity_without_barcode=qty, unit_price=Decimal('150.00'),
        sale_currency=base['currency'], exchange_rate_at_sale=Decimal('1.00')
    )
    item.update_product_stock()
    sale.calculate_and_save_totals()
    sale.refresh_from_db()
    if paid > 0:
        CashTransaction.objects.create(
            transaction_date=timezone.now(), amount_in=paid,
            amount_out=Decimal('0.00'), transaction_type='sale_receipt',
            sale_invoice=sale, notes=f'{TEST_MARKER} تحصيل',
            created_by=base['admin'], payment_method=base['cash_method']
        )
    return sale, item


def create_sale_return(base, sale, item, total, refund):
    qty = total / Decimal('150.00')
    ret = SaleReturn.objects.create(
        original_sale=sale, created_by=base['admin'],
        return_date=timezone.now().date(),
        return_payment_method=base['cash_method'],
        return_currency=base['currency'],
        paid_amount=refund, return_notes=f'{TEST_MARKER} مرتجع'
    )
    ritem = SaleReturnItem.objects.create(
        sale_return=ret, original_sale_item=item,
        product=base['product_sale'],
        item_name=base['product_sale'].product_name,
        returned_quantity=qty, quantity_with_barcode=Decimal('0.00'),
        quantity_without_barcode=qty, unit_price=Decimal('150.00'),
        return_currency=base['currency'], exchange_rate_at_return=Decimal('1.00')
    )
    ritem.restore_product_stock()
    ret.calculate_and_save_totals()
    ret.refresh_from_db()
    ret.reconcile_cash_transactions()
    return ret


def create_purch(base, total, paid):
    purch = Purch.objects.create(
        purch_supplier=base['supplier'], purch_currency=base['currency'],
        purch_payment_method=base['cash_method'],
        purch_tax_percentage=Decimal('0.00'), purch_discount=Decimal('0.00'),
        purch_addition=Decimal('0.00'), paid_amount=paid, created_by=base['admin']
    )
    qty = total / Decimal('100.00')
    item = PurchItem.objects.create(
        purch=purch, product=base['product_purch'],
        item_name=base['product_purch'].product_name,
        purchased_quantity=qty, unit_price=Decimal('100.00'),
        purch_currency=base['currency'], exchange_rate_at_purchase=Decimal('1.00')
    )
    item.update_product_stock()
    purch.calculate_and_save_totals()
    purch.refresh_from_db()
    if paid > 0:
        CashTransaction.objects.create(
            transaction_date=timezone.now(),
            amount_in=Decimal('0.00'), amount_out=paid,
            transaction_type='purchase_payment',
            purchase_invoice=purch, notes=f'{TEST_MARKER} دفع',
            created_by=base['admin'], payment_method=base['cash_method']
        )
    return purch, item


def create_purch_return(base, purch, item, total, refund):
    qty = total / Decimal('100.00')
    ret = PurchaseReturn.objects.create(
        original_purchase=purch, created_by=base['admin'],
        return_date=timezone.now().date(),
        purch_currency=base['currency'],
        paid_amount=refund, return_notes=f'{TEST_MARKER} مرتجع شراء'
    )
    ritem = PurchaseReturnItem.objects.create(
        purchase_return=ret, original_item=item,
        product=base['product_purch'],
        purchased_quantity=qty, returned_quantity=qty,
        return_unit_price=Decimal('100.00')
    )
    ritem.save()
    ret.calculate_and_save_totals()
    ret.refresh_from_db()

    if refund > 0:
        CashTransaction.objects.create(
            transaction_date=timezone.now(),
            amount_in=refund, amount_out=Decimal('0.00'),
            transaction_type='purchase_return',
            purchase_invoice=purch, purchase_return=ret,
            notes=f'{TEST_MARKER} استلام مرتجع شراء',
            created_by=base['admin'], payment_method=base['cash_method']
        )
    return ret


def run_customer_scenario(num, title, total, paid, ret_total, refund, expected_delta):
    print_header(f"سيناريو العميل {num}: {title}")
    print(f"  فاتورة: total={total}, paid={paid}")
    print(f"  مرتجع: total={ret_total}, refund={refund}")
    print(f"  التوقع: delta net_customer_debt = {expected_delta}")

    cleanup_test_data()
    base = setup_base()
    if not base:
        print("  ✗ لا توجد طريقة دفع نقدي")
        return False

    client = Client()
    client.force_login(base['admin'])

    print_step(1, "قياس baseline")
    before = get_report_values(client)
    if before is None or before.get('net_customer_debt') is None:
        print(f"  ⚠️ فشل قياس baseline — تخطي السيناريو")
        cleanup_test_data()
        return False
    print(f"  net_customer_debt قبل: {before['net_customer_debt']}")

    print_step(2, "إنشاء فاتورة البيع")
    sale, item = create_sale(base, total, paid)
    print(f"  فاتورة: {sale.uniqueId} | balance_due={sale.balance_due}")

    print_step(3, "إنشاء مرتجع المبيعات")
    ret = create_sale_return(base, sale, item, ret_total, refund)
    print(f"  مرتجع: {ret.uniqueId} | final={ret.return_final_total} | paid={ret.paid_amount}")

    print_step(4, "قياس بعد")
    after = get_report_values(client)
    if after is None or after.get('net_customer_debt') is None:
        print(f"  ⚠️ فشل قياس بعد — تخطي السيناريو")
        cleanup_test_data()
        return False

    delta = after['net_customer_debt'] - before['net_customer_debt']
    print(f"  net_customer_debt بعد: {after['net_customer_debt']}")
    print(f"  delta = {after['net_customer_debt']} - {before['net_customer_debt']} = {delta}")

    ok = (delta == expected_delta)
    print(f"  ★ الفرق = {delta} (متوقع {expected_delta}): {ok}")

    if not ok:
        if delta > expected_delta:
            print(f"  ✗ الفرق أكبر من المتوقع — السلوك القديم (+) ما زال موجوداً")
        else:
            print(f"  ✗ الفرق أصغر من المتوقع — راجع الحساب")

    cleanup_test_data()
    return ok


def run_supplier_scenario(num, title, total, paid, ret_total, refund, expected_delta):
    print_header(f"سيناريو المورد {num}: {title}")
    print(f"  فاتورة شراء: total={total}, paid={paid}")
    print(f"  مرتجع شراء: total={ret_total}, refund={refund}")
    print(f"  التوقع: delta net_supplier_debt = {expected_delta}")

    cleanup_test_data()
    base = setup_base()
    if not base:
        print("  ✗ لا توجد طريقة دفع نقدي")
        return False

    client = Client()
    client.force_login(base['admin'])

    print_step(1, "قياس baseline")
    before = get_report_values(client)
    if before is None or before.get('net_supplier_debt') is None:
        print(f"  ⚠️ فشل قياس baseline — تخطي السيناريو")
        cleanup_test_data()
        return False
    print(f"  net_supplier_debt قبل: {before['net_supplier_debt']}")

    print_step(2, "إنشاء فاتورة الشراء")
    purch, item = create_purch(base, total, paid)
    print(f"  فاتورة: {purch.uniqueId} | balance_due={purch.balance_due}")

    print_step(3, "إنشاء مرتجع الشراء")
    ret = create_purch_return(base, purch, item, ret_total, refund)
    print(f"  مرتجع: {ret.uniqueId} | final={ret.return_final_total} | paid={ret.paid_amount}")

    print_step(4, "قياس بعد")
    after = get_report_values(client)
    if after is None or after.get('net_supplier_debt') is None:
        print(f"  ⚠️ فشل قياس بعد — تخطي السيناريو")
        cleanup_test_data()
        return False

    delta = after['net_supplier_debt'] - before['net_supplier_debt']
    print(f"  net_supplier_debt بعد: {after['net_supplier_debt']}")
    print(f"  delta = {after['net_supplier_debt']} - {before['net_supplier_debt']} = {delta}")

    ok = (delta == expected_delta)
    print(f"  ★ الفرق = {delta} (متوقع {expected_delta}): {ok}")

    if not ok:
        if delta > expected_delta:
            print(f"  ✗ الفرق أكبر من المتوقع — السلوك القديم (+) ما زال موجوداً")

    cleanup_test_data()
    return ok


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    cleanup_test_data()

    results = []

    r1 = run_customer_scenario(1, "مرتجع 200 بلا صرف",
        Decimal('1000.00'), Decimal('0.00'),
        Decimal('200.00'), Decimal('0.00'),
        Decimal('800.00'))
    results.append(('سيناريو عميل 1', r1))

    r2 = run_customer_scenario(2, "مرتجع 200 مع صرف كامل 200",
        Decimal('1000.00'), Decimal('0.00'),
        Decimal('200.00'), Decimal('200.00'),
        Decimal('1000.00'))
    results.append(('سيناريو عميل 2', r2))

    r3 = run_customer_scenario(3, "مرتجع 200 مع صرف جزئي 100",
        Decimal('1000.00'), Decimal('0.00'),
        Decimal('200.00'), Decimal('100.00'),
        Decimal('900.00'))
    results.append(('سيناريو عميل 3', r3))

    r4 = run_supplier_scenario(1, "مرتجع 200 بلا استلام",
        Decimal('1000.00'), Decimal('0.00'),
        Decimal('200.00'), Decimal('0.00'),
        Decimal('800.00'))
    results.append(('سيناريو مورد 1', r4))

    r5 = run_supplier_scenario(2, "مرتجع 200 مع استلام كامل 200",
        Decimal('1000.00'), Decimal('0.00'),
        Decimal('200.00'), Decimal('200.00'),
        Decimal('1000.00'))
    results.append(('سيناريو مورد 2', r5))

    r6 = run_supplier_scenario(3, "مرتجع 200 مع استلام جزئي 100",
        Decimal('1000.00'), Decimal('0.00'),
        Decimal('200.00'), Decimal('100.00'),
        Decimal('900.00'))
    results.append(('سيناريو مورد 3', r6))

    return results


# ==================== نقطة الدخول ====================
print_header("فحص إغلاق — بند 1.3 من تقرير التدقيق (محصّن بالـ monkey-patch)")
print(f"  الموضوع: التحقق من إصلاح صافي دين العميل والمورد")
print(f"  المنهجية: 3 سيناريوهات عميل + 3 سيناريوهات مورد = 6 فحوصات")
print(f"  المسار المُختبر: GET /invoice/reports/unpaid-invoices/")
print(f"  آلية التقاط context: monkey-patch لدالة render()")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    res = run_test(i)
    all_results.append(res)

# ★ استعادة render الأصلية
views_module.render = original_render

print_header("الخلاصة النهائية")

run1 = all_results[0]
run2 = all_results[1]
same_run = all(run1[j][1] == run2[j][1] for j in range(len(run1)))
print(f"  التشغيلان متطابقان: {same_run}")

print(f"\n  نتائج التشغيل 1:")
passed = 0
for name, ok in run1:
    sign = '✓' if ok else '✗'
    print(f"  {sign} {name}")
    if ok: passed += 1
total = len(run1)
print(f"\n  النتيجة النهائية: {passed}/{total}")

if passed == total and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 1.3 أُغلق بدليل رقمي:")
    print(f"    - net_customer_debt يحسب صافي دين العميل بعد طرح المرتجعات غير المسددة")
    print(f"    - net_supplier_debt يحسب صافي دين المورد بعد طرح المرتجعات غير المسددة")
    print(f"    - السلوك متسق عبر سيناريوهات (بلا صرف، صرف كامل، صرف جزئي)")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
    print(f"  راجع الفحوصات الفاشلة — قد يكون السلوك القديم ما زال موجوداً")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")