"""
================================================================
فحص إثبات + إغلاق — بند 2.5 من تقرير التدقيق
================================================================
الموضوع: convert_order_to_invoice لا يُعيّن sale_payment_method

المشكلة:
  - عند تحويل طلب متجر إلى فاتورة بيع، لا يُحدد sale_payment_method
  - sale_payment_method = None
  - إن عُدّلت الفاتورة لاحقاً (sale_edit)، يستدعي reconcile_cash_transactions
    التي ترى is_cash = False (لأن payment_method = None) → تحذف حركة الصندوق
  - النتيجة: حركة الصندوق تضيع، كشف الصندوق يُظهر مبلغاً أقل من الواقع

الإصلاح المقترح:
  - تعيين sale_payment_method للطريقة النقدية الافتراضية
  - تعيين sale_currency للعملة الأساسية
  - استدعاء sale.reconcile_cash_transactions() بدل إنشاء CashTransaction يدوي

السيناريوهات:
  1) تحويل طلب متجر إلى فاتورة → التحقق من sale_payment_method و sale_currency
  2) التحقق من وجود حركة صندوق (CashTransaction)
  3) محاكاة sale_edit (استدعاء reconcile_cash_transactions) → حركة الصندوق يجب أن تبقى
  4) التحقق من المبلغ الصحيح (paid_amount = order.total_amount)

المنهجية:
  - HTTP حي عبر django.test.Client
  - مستخدم فائق معزول
  - تنظيف ذاتي قبل/بعد
  - 6 فحوصات × تشغيلان متطابقان = 12 قياساً

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_2_5.py', encoding='utf-8').read())"
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
    Sale, SaleItem, SaleItemBarcode, CashTransaction,
    Product, Payment_method, Currency, WebsiteOrder, WebsiteOrderItem
)

TEST_MARKER = 'فحص_2_5'
TEST_ADMIN = f'{TEST_MARKER}_مدير'
TEST_CUSTOMER = f'{TEST_MARKER}_عميل'
TEST_PRODUCT = f'{TEST_MARKER}_منتج'


def cleanup_test_data():
    """تنظيف شامل"""
    test_user_ids = list(User.objects.filter(
        Q(username=TEST_CUSTOMER) | Q(username=TEST_ADMIN)
    ).values_list('id', flat=True))
    
    test_sale_ids = list(Sale.objects.filter(
        Q(sale_customer_id__in=test_user_ids) | Q(created_by_id__in=test_user_ids)
    ).values_list('id', flat=True))
    
    test_order_ids = list(WebsiteOrder.objects.filter(
        Q(user_id__in=test_user_ids) | Q(full_name__startswith=TEST_MARKER)
    ).values_list('id', flat=True))
    
    if test_sale_ids:
        SaleItemBarcode.objects.filter(sale_item__sale_id__in=test_sale_ids).delete()
        SaleItem.objects.filter(sale_id__in=test_sale_ids).delete()
        Sale.objects.filter(id__in=test_sale_ids).delete()
    
    if test_order_ids:
        WebsiteOrderItem.objects.filter(order_id__in=test_order_ids).delete()
        WebsiteOrder.objects.filter(id__in=test_order_ids).delete()
    
    CashTransaction.objects.filter(
        Q(sale_invoice_id__in=test_sale_ids) |
        Q(notes__contains=TEST_MARKER) |
        Q(created_by_id__in=test_user_ids)
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
        username=TEST_CUSTOMER, first_name=TEST_MARKER, last_name='العميل'
    )
    
    admin = User.objects.create_superuser(
        username=TEST_ADMIN, password='Test@12345',
        first_name=TEST_MARKER, last_name='المدير'
    )
    
    # منتج بكمية 10
    product = Product.objects.create(
        product_name=TEST_PRODUCT,
        purch_price=Decimal('100.00'),
        sale_price=Decimal('150.00'),
        current_stock_quantity=Decimal('10.00'),
        average_purchase_cost=Decimal('100.00')
    )
    
    return {
        'currency': currency,
        'cash_method': cash_method,
        'customer': customer,
        'admin': admin,
        'product': product,
    }


def create_website_order(base, qty=2, unit_price=Decimal('150.00')):
    """إنشاء طلب متجر اختباري"""
    total = qty * unit_price
    
    order = WebsiteOrder.objects.create(
        user=base['customer'],
        full_name=f'{TEST_MARKER} زبون',
        phone='1234567890',
        address=f'{TEST_MARKER} عنوان اختباري',
        total_amount=total,
        status='new',
    )
    
    WebsiteOrderItem.objects.create(
        order=order,
        product=base['product'],
        product_name=base['product'].product_name,
        price=unit_price,
        quantity=int(qty),
    )
    
    return order


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    cleanup_test_data()
    
    base = setup_base()
    if not base:
        print("  ✗ لا توجد طريقة دفع نقدي")
        return None
    
    client = Client()
    client.force_login(base['admin'])
    
    # ====== [1] إنشاء طلب متجر ======
    print_step(1, "إنشاء طلب متجر اختباري")
    order = create_website_order(base, qty=2, unit_price=Decimal('150.00'))
    print(f"  طلب #{order.id} | total={order.total_amount}")
    
    # ====== [2] تحويل الطلب لفاتورة عبر HTTP ======
    print_step(2, "تحويل الطلب لفاتورة عبر POST /invoice/manage/order/<id>/convert/")
    
    response = client.post(f'/invoice/manage/order/{order.id}/convert/')
    print(f"  HTTP status: {response.status_code}")
    if hasattr(response, 'url'):
        print(f"  Redirect to: {response.url}")
    
    http_ok = (response.status_code == 302)
    
    # ====== [3] فحص 1: HTTP 302 ======
    print_step(3, "فحص 1: التحويل ناجح (HTTP 302)")
    check_1 = http_ok
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | HTTP status = {response.status_code}")
    
    # ====== [4] فحص 2: sale_payment_method معيّنة ======
    print_step(4, "فحص 2: ★ sale_payment_method معيّنة (جوهر الإصلاح)")
    
    order.refresh_from_db()
    sale = order.related_sale
    
    if sale:
        payment_method_set = (sale.sale_payment_method is not None)
        check_2 = payment_method_set
        sign = '✓' if check_2 else '✗'
        print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | sale_payment_method = {sale.sale_payment_method}")
        if not check_2:
            print(f"     ✗ العلة موجودة: sale_payment_method = None")
    else:
        check_2 = False
        print(f"  ✗ FAIL | sale غير موجود (التحويل فشل)")
    
    # ====== [5] فحص 3: sale_currency معيّنة ======
    print_step(5, "فحص 3: sale_currency معيّنة")
    
    if sale:
        currency_set = (sale.sale_currency is not None)
        check_3 = currency_set
        sign = '✓' if check_3 else '✗'
        print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | sale_currency = {sale.sale_currency}")
    else:
        check_3 = False
        print(f"  ✗ FAIL | sale غير موجود")
    
    # ====== [6] فحص 4: حركة الصندوق موجودة ======
    print_step(6, "فحص 4: حركة صندوق أُنشئت (CashTransaction)")
    
    if sale:
        cash_tx = CashTransaction.objects.filter(
            sale_invoice=sale, transaction_type='sale_receipt'
        ).first()
        
        cash_tx_exists = (cash_tx is not None)
        check_4 = cash_tx_exists
        sign = '✓' if check_4 else '✗'
        print(f"  {sign} {'PASS' if check_4 else 'FAIL'} | حركة موجودة")
        if cash_tx:
            print(f"     amount_in = {cash_tx.amount_in} (متوقع {order.total_amount})")
    else:
        check_4 = False
        print(f"  ✗ FAIL | sale غير موجود")
    
    # ====== [7] فحص 5: المبلغ صحيح ======
    print_step(7, "فحص 5: paid_amount = order.total_amount")
    
    if sale:
        amount_correct = (sale.paid_amount == order.total_amount)
        check_5 = amount_correct
        sign = '✓' if check_5 else '✗'
        print(f"  {sign} {'PASS' if check_5 else 'FAIL'} | paid_amount = {sale.paid_amount} (متوقع {order.total_amount})")
    else:
        check_5 = False
        print(f"  ✗ FAIL | sale غير موجود")
    
    # ====== [8] فحص 6: حركة الصندوق تبقى بعد reconcile ======
    print_step(8, "فحص 6: ★ حركة الصندوق تبقى بعد reconcile (محاكاة sale_edit)")
    
    if sale and sale.sale_payment_method:
        # محاكاة ما يحدث في sale_edit: استدعاء reconcile_cash_transactions
        try:
            sale.reconcile_cash_transactions()
            
            cash_tx_after = CashTransaction.objects.filter(
                sale_invoice=sale, transaction_type='sale_receipt'
            ).first()
            
            cash_tx_preserved = (cash_tx_after is not None and cash_tx_after.amount_in == order.total_amount)
            check_6 = cash_tx_preserved
            sign = '✓' if check_6 else '✗'
            print(f"  {sign} {'PASS' if check_6 else 'FAIL'} | حركة لا تزال موجودة بعد reconcile")
            if cash_tx_after:
                print(f"     amount_in بعد reconcile = {cash_tx_after.amount_in}")
        except Exception as e:
            check_6 = False
            print(f"  ✗ FAIL | استثناء: {e}")
    elif sale and not sale.sale_payment_method:
        # العلة: payment_method = None → reconcile سيحذف الحركة!
        try:
            sale.reconcile_cash_transactions()
            
            cash_tx_after = CashTransaction.objects.filter(
                sale_invoice=sale, transaction_type='sale_receipt'
            ).first()
            
            # قبل الإصلاح: reconcile يحذف الحركة (لأن is_cash=False)
            check_6 = False  # نفشل لأن الحركة حُذفت
            print(f"  ✗ FAIL | حركة الصندوق حُذفت بعد reconcile (payment_method=None → is_cash=False)")
            if cash_tx_after is None:
                print(f"     ✗ تأكيد: لا توجد حركة صندوق بعد reconcile")
        except Exception as e:
            check_6 = False
            print(f"  ✗ FAIL | استثناء: {e}")
    else:
        check_6 = False
        print(f"  ✗ FAIL | sale غير موجود")
    
    # ====== [9] العداد النهائي ======
    print_step(9, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3, check_4, check_5, check_6]
    descriptions = [
        'HTTP 302 (التحويل ناجح)',
        '★ sale_payment_method معيّنة (جوهر الإصلاح)',
        'sale_currency معيّنة',
        'حركة صندوق أُنشئت (CashTransaction)',
        'paid_amount = order.total_amount',
        '★ حركة الصندوق تبقى بعد reconcile (محاكاة sale_edit)',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/6")
    
    cleanup_test_data()
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 2.5 من تقرير التدقيق")
print(f"  الموضوع: convert_order_to_invoice — تعيين sale_payment_method")
print(f"  المنهجية: HTTP حي + 6 فحوصات × تشغيلان")
print(f"  المسار المُختبر: POST /invoice/manage/order/<id>/convert/")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    p, checks = run_test(i)
    all_results.append((p, checks))

print_header("الخلاصة النهائية")

run1_p, run1_checks = all_results[0]
run2_p, run2_checks = all_results[1]
same_run = (run1_checks == run2_checks)

print(f"  التشغيل 1: {run1_p}/6")
print(f"  التشغيل 2: {run2_p}/6")
print(f"  متطابقة: {same_run}")
print(f"  النتيجة النهائية: {run1_p}/6")

# تحليل النتائج
check_2_passes = run1_checks[1]  # sale_payment_method معيّنة
check_6_passes = run1_checks[5]  # حركة تبقى بعد reconcile

if run1_p == 6 and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 2.5 أُغلق بدليل رقمي:")
    print(f"    - convert_order_to_invoice يُعيّن sale_payment_method")
    print(f"    - sale_currency معيّنة للعملة الأساسية")
    print(f"    - حركة الصندوق تُنشأ وتحفظ بعد reconcile")
    print(f"    - السلوك متسق مع sale_create (نفس النمط)")
elif not check_2_passes and same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✗ الفحص 2 فشل: sale_payment_method = None")
    print(f"  الأثر: عند sale_edit لاحقاً، reconcile_cash_transactions يحذف الحركة")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
elif check_2_passes and not check_6_passes and same_run:
    print(f"\n  ⚠️ العلة موجودة: sale_payment_method معيّن لكن reconcile يحذف الحركة")
    print(f"  راجع الكود — قد يكون payment_method غير نقدية")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
    print(f"  راجع الفحوصات الفاشلة أعلاه")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")