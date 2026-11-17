"""
================================================================
فحص إغلاق — بند 1.1 من تقرير التدقيق
================================================================
الموضوع: التحقق من نجاح الخيار (ب) — حذف تعديل paid_amount
         في فاتورة الشراء الأصلية عند إنشاء/حذف مرتجع الشراء

المنهجية المعتمدة:
  - ضرب الفيوهات الحية عبر django.test.Client
  - مستخدم فائق معزول
  - تنظيف ذاتي قبل/بعد
  - بيانات معلّمة ببادئة عربية 'فحص_1_1_إغلاق'
  - يُشغَّل مرتين متتاليتين ويعطي النتيجة نفسها
  - مخرجات بنمط PASS/FAIL وعدد نهائي

دورة الفحص الكاملة:
  1) إنشاء فاتورة شراء 1000/600/400/10
  2) لقطة (1) قبل المرتجع
  3) إنشاء مرتجع (إرجاع 2 = 200، استلام 200 نقداً)
  4) لقطة (2) بعد المرتجع
  5) فحص: paid_amount و balance_due لم يتغيرا (جوهر الإصلاح)
  6) فحص: حركة الصندوق +200 موجودة (لم تتأثر)
  7) فحص: المخزون -2 (لم يتأثر)
  8) فحص: purch_final_total لم يتغير
  9) حذف المرتجع عبر الفيوة الحية
 10) لقطة (3) بعد حذف المرتجع
 11) فحص: paid_amount عاد 600 (لم يتأثر بحذف المرتجع)
 12) فحص: balance_due عاد 400
 13) فحص: حركة الصندوق للمرتجع حُذفت
 14) فحص: المخزون عاد 10 (الإرجاع للمورد لُغي)
 15) التنظيف الذاتي

طريقة التشغيل من مجلد المشروع (بجانب manage.py):
    python manage.py shell -c "exec(open('فحص_إغلاق_بند_1_1.py', encoding='utf-8').read())"

متطلبات مسبقة:
  - وجود عملة افتراضية في النظام (أو أي عملة)
  - وجود طريقة دفع نقدي (is_cash=True) أو باسم 'نقداً'
  - وجود قالب purchase_return_confirm_delete.html
================================================================
"""

import os
import sys
from decimal import Decimal

# ==================== إعداد Django ====================
import django
from django.conf import settings
from django.test import Client
from django.contrib.auth import get_user_model
from django.db.models import Q

# حارسة ALLOWED_HOSTS — تضاف فقط داخل هذه العملية ولا تلمس settings.py
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import (
    Purch, PurchItem, PurchItemBarcode,
    PurchaseReturn, PurchaseReturnItem, PurchaseReturnItemBarcode,
    Barcode, Product, CashTransaction, Payment_method, Currency
)


# ==================== العلامات العربية ====================
TEST_MARKER       = 'فحص_1_1_إغلاق'
TEST_USER          = f'{TEST_MARKER}_مورد'
TEST_ADMIN         = f'{TEST_MARKER}_مدير'
TEST_PRODUCT       = f'{TEST_MARKER}_منتج'
TEST_BARCODE_PREF  = f'{TEST_MARKER}_باركود_'


# ==================== دوال مساعدة ====================
def cleanup_test_data():
    """تنظيف شامل لأي بيانات معلّمة بالعلامة"""
    test_purch_ids = list(Purch.objects.filter(
        Q(purch_supplier__username=TEST_USER) |
        Q(created_by__username=TEST_ADMIN)
    ).values_list('id', flat=True))

    if test_purch_ids:
        PurchaseReturnItemBarcode.objects.filter(
            purchase_return_item__purchase_return__original_purchase_id__in=test_purch_ids
        ).delete()
        PurchaseReturnItem.objects.filter(
            purchase_return__original_purchase_id__in=test_purch_ids
        ).delete()
        PurchaseReturn.objects.filter(
            original_purchase_id__in=test_purch_ids
        ).delete()

        PurchItemBarcode.objects.filter(
            purch_item__purch_id__in=test_purch_ids
        ).delete()
        PurchItem.objects.filter(
            purch_id__in=test_purch_ids
        ).delete()
        Purch.objects.filter(id__in=test_purch_ids).delete()

    CashTransaction.objects.filter(
        Q(purchase_invoice_id__in=test_purch_ids) |
        Q(purchase_return__original_purchase_id__in=test_purch_ids) |
        Q(notes__contains=TEST_MARKER) |
        Q(created_by__username=TEST_ADMIN)
    ).delete()

    Barcode.objects.filter(barcode_in__startswith=TEST_BARCODE_PREF).delete()
    Product.objects.filter(product_name__startswith=TEST_MARKER).delete()
    User.objects.filter(username__in=[TEST_USER, TEST_ADMIN]).delete()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


# ==================== الفحص الرئيسي ====================
def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")

    cleanup_test_data()

    # ====== [1] إعداد البيانات الأساسية ======
    print_step(1, "إعداد البيانات الأساسية")

    currency = Currency.objects.filter(is_default=True).first()
    if not currency:
        currency = Currency.objects.first()

    cash_method = Payment_method.objects.filter(is_cash=True).first()
    if not cash_method:
        cash_method = Payment_method.objects.filter(
            name__in=['نقداً', 'نقدا', 'Cash']
        ).first()
    if not cash_method:
        print("  ✗ لا توجد طريقة دفع نقدي في النظام")
        cleanup_test_data()
        return False, 0

    supplier = User.objects.create(
        username=TEST_USER,
        first_name=TEST_MARKER,
        last_name='المورد'
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
        current_stock_quantity=Decimal('0.00'),
        average_purchase_cost=Decimal('0.00')
    )

    bc1 = Barcode.objects.create(
        barcode_in=f'{TEST_BARCODE_PREF}1',
        product=product,
        status='active',
        is_primary=False
    )
    bc2 = Barcode.objects.create(
        barcode_in=f'{TEST_BARCODE_PREF}2',
        product=product,
        status='active',
        is_primary=False
    )

    print(f"  المنتج: {product.product_name} | الباركودات: {bc1.barcode_in}, {bc2.barcode_in}")
    print(f"  طريقة الدفع: {cash_method.name} (is_cash={cash_method.is_cash})")

    # ====== [2] إنشاء فاتورة شراء بدفع جزئي ======
    print_step(2, "إنشاء فاتورة شراء (إجمالي 1000، مدفوع 600)")

    purch = Purch.objects.create(
        purch_supplier=supplier,
        purch_currency=currency,
        purch_payment_method=cash_method,
        purch_tax_percentage=Decimal('0.00'),
        purch_discount=Decimal('0.00'),
        purch_addition=Decimal('0.00'),
        paid_amount=Decimal('600.00'),
        created_by=admin
    )

    purch_item = PurchItem.objects.create(
        purch=purch,
        product=product,
        item_name=product.product_name,
        purchased_quantity=Decimal('10.00'),
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

    purch_item.update_product_stock()
    purch.calculate_and_save_totals()
    purch.refresh_from_db()
    product.refresh_from_db()
    purch.create_cash_transaction()

    print(f"  فاتورة: {purch.uniqueId} | final_total={purch.purch_final_total} | paid={purch.paid_amount} | balance={purch.balance_due}")
    print(f"  المخزون: {product.current_stock_quantity}")

    # ====== [3] لقطة (1) قبل المرتجع ======
    print_step(3, "لقطة (1) قبل المرتجع")

    state_1 = {
        'paid_amount':      purch.paid_amount,
        'balance_due':      purch.balance_due,
        'is_paid':          purch.is_paid,
        'purch_final_total': purch.purch_final_total,
        'stock':            product.current_stock_quantity,
        'cash_balance':     CashTransaction.get_cash_balance(),
    }
    for k, v in state_1.items():
        print(f"  {k}: {v}")

    initial_ok = (
        state_1['purch_final_total'] == Decimal('1000.00') and
        state_1['paid_amount']       == Decimal('600.00') and
        state_1['balance_due']       == Decimal('400.00') and
        not state_1['is_paid'] and
        state_1['stock']             == Decimal('10.00')
    )
    print(f"  ✓ الحالة الأولية سليمة (1000/600/400/10): {initial_ok}")
    if not initial_ok:
        cleanup_test_data()
        return False, 0

    # ====== [4] إنشاء المرتجع ======
    print_step(4, "إنشاء مرتجع (إرجاع 2 = 200، استلام 200 نقداً)")

    client = Client()
    client.force_login(admin)

    post_data = {
        'return_date':  '2026-11-16',
        'paid_amount':  '200.00',
        'return_notes': f'{TEST_MARKER} ملاحظة المرتجع',
        f'item-{purch_item.id}-original_item':       str(purch_item.id),
        f'item-{purch_item.id}-product':            str(product.id),
        f'item-{purch_item.id}-purchased_quantity': '10.00',
        f'item-{purch_item.id}-return_unit_price':  '100.00',
        f'item-{purch_item.id}-return_total':       '200.00',
        f'item-{purch_item.id}-original_barcodes':  [str(bc1.id), str(bc2.id)],
    }

    response = client.post(f'/invoice/purchases/{purch.slug}/return/', post_data)
    print(f"  HTTP status: {response.status_code}")
    if hasattr(response, 'url'):
        print(f"  Redirect to: {response.url}")

    # ====== [5] لقطة (2) بعد المرتجع ======
    print_step(5, "لقطة (2) بعد المرتجع — يجب ألا تتغير paid_amount و balance_due")

    purch.refresh_from_db()
    product.refresh_from_db()

    purchase_returns = PurchaseReturn.objects.filter(original_purchase=purch)
    print(f"  عدد المرتجعات: {purchase_returns.count()}")
    if purchase_returns.exists():
        pr = purchase_returns.first()
        print(f"  المرتجع: {pr.uniqueId} | return_final_total={pr.return_final_total} | paid={pr.paid_amount}")

    state_2 = {
        'paid_amount':      purch.paid_amount,
        'balance_due':      purch.balance_due,
        'is_paid':          purch.is_paid,
        'purch_final_total': purch.purch_final_total,
        'stock':            product.current_stock_quantity,
        'cash_balance':     CashTransaction.get_cash_balance(),
    }

    print(f"\n  ★★★ فاتورة الشراء بعد المرتجع ★★★")
    for k in state_2:
        before = state_1[k]
        after = state_2[k]
        try:
            delta = after - before
            arrow = '  (Δ = 0 — لم يتغير ✓)' if delta == 0 else f'  (Δ = {delta:+})'
        except Exception:
            arrow = ''
        print(f"  {k}: {after}{arrow}")

    # ====== [6] فحص حركة الصندوق ======
    print_step(6, "حركة الصندوق للمرتجع")

    cash_txs = CashTransaction.objects.filter(
        transaction_type='purchase_return'
    ).filter(
        Q(purchase_invoice=purch) |
        Q(notes__contains=TEST_MARKER)
    )
    print(f"  عدد حركات الصندوق: {cash_txs.count()}")
    for tx in cash_txs:
        print(f"  - amount_in: {tx.amount_in} | المرتجع: {tx.purchase_return.uniqueId if tx.purchase_return else '—'}")

    # ====== [7] فحوصات ما بعد الإنشاء ======
    print_step(7, "فحوصات الإصلاح بعد إنشاء المرتجع")

    paid_unchanged     = (state_2['paid_amount']      == state_1['paid_amount'])
    balance_unchanged  = (state_2['balance_due']      == state_1['balance_due'])
    total_unchanged    = (state_2['purch_final_total'] == state_1['purch_final_total'])
    stock_reduced_2    = (state_2['stock']            == Decimal('8.00'))
    cash_in_200        = (state_2['cash_balance']     - state_1['cash_balance'] == Decimal('200.00'))
    return_created     = purchase_returns.exists()
    cash_tx_created    = (cash_txs.count() == 1)
    redirect_302       = (response.status_code == 302)
    old_behavior_gone  = (state_2['paid_amount'] == Decimal('600.00') and state_2['balance_due'] == Decimal('400.00'))

    print(f"  ✓ HTTP 302 (إنشاء ناجح):                       {redirect_302}")
    print(f"  ✓ المرتجع أُنشئ في قاعدة البيانات:              {return_created}")
    print(f"  ✓ ★ paid_amount لم يتغير (600 = 600):           {paid_unchanged}")
    print(f"  ✓ ★ balance_due لم يتغير (400 = 400):           {balance_unchanged}")
    print(f"  ✓ purch_final_total لم يتغير (1000 = 1000):    {total_unchanged}")
    print(f"  ✓ المخزون نقص 2 (10 → 8):                      {stock_reduced_2}")
    print(f"  ✓ cash_balance زادت 200:                       {cash_in_200}")
    print(f"  ✓ حركة صندوق للمرتجع موجودة:                   {cash_tx_created}")
    print(f"  ★ السلوك القديم اختفى كلياً:                    {old_behavior_gone}")

    if not return_created:
        print(f"\n  ⚠️ لم يُنشأ المرتجع — إيقاف الفحص")
        cleanup_test_data()
        return False, 0

    # ====== [8] حذف المرتجع ======
    print_step(8, "حذف المرتجع عبر الفيوة الحية")

    pr_slug = purchase_returns.first().slug
    response_del = client.post(f'/invoice/purchase-returns/{pr_slug}/delete/', {})
    print(f"  HTTP status: {response_del.status_code}")
    if hasattr(response_del, 'url'):
        print(f"  Redirect to: {response_del.url}")

    # ====== [9] لقطة (3) بعد حذف المرتجع ======
    print_step(9, "لقطة (3) بعد حذف المرتجع — يجب العودة للحالة (1)")

    purch.refresh_from_db()
    product.refresh_from_db()

    state_3 = {
        'paid_amount':      purch.paid_amount,
        'balance_due':      purch.balance_due,
        'is_paid':          purch.is_paid,
        'purch_final_total': purch.purch_final_total,
        'stock':            product.current_stock_quantity,
        'cash_balance':     CashTransaction.get_cash_balance(),
    }

    print(f"\n  ★★★ فاتورة الشراء بعد حذف المرتجع ★★★")
    print(f"  (يجب أن تتطابق مع لقطة (1) قبل المرتجع)")
    for k in state_3:
        v1 = state_1[k]
        v3 = state_3[k]
        same = (v1 == v3)
        sign = '✓' if same else '✗'
        print(f"  {sign} {k}: {v3}  (لقطة 1: {v1})")

    cash_txs_after_del = CashTransaction.objects.filter(
        transaction_type='purchase_return'
    ).filter(
        Q(purchase_invoice=purch) |
        Q(notes__contains=TEST_MARKER)
    )
    print(f"\n  حركات الصندوق للمرتجع بعد الحذف: {cash_txs_after_del.count()} (يجب أن تكون 0)")

    # ====== [10] فحوصات ما بعد الحذف ======
    print_step(10, "فحوصات بعد حذف المرتجع")

    paid_restored       = (state_3['paid_amount']      == state_1['paid_amount'])
    balance_restored    = (state_3['balance_due']      == state_1['balance_due'])
    total_restored      = (state_3['purch_final_total'] == state_1['purch_final_total'])
    stock_restored      = (state_3['stock']            == Decimal('10.00'))
    cash_restored       = (state_3['cash_balance']     == state_1['cash_balance'])
    cash_tx_deleted     = (cash_txs_after_del.count() == 0)
    return_deleted      = not PurchaseReturn.objects.filter(original_purchase=purch).exists()

    print(f"  ✓ المرتجع حُذف من قاعدة البيانات:               {return_deleted}")
    print(f"  ✓ ★ paid_amount لم يتأثر بالحذف (600 = 600):    {paid_restored}")
    print(f"  ✓ ★ balance_due لم يتأثر بالحذف (400 = 400):    {balance_restored}")
    print(f"  ✓ purch_final_total لم يتأثر (1000 = 1000):    {total_restored}")
    print(f"  ✓ المخزون عاد 10 (إعادة الكمية):              {stock_restored}")
    print(f"  ✓ cash_balance عاد (حذف الحركة):              {cash_restored}")
    print(f"  ✓ حركة الصندوق للمرتجع حُذفت:                  {cash_tx_deleted}")

    # ====== [11] العداد النهائي ======
    print_step(11, "نتيجة فحوصات التشغيل")

    cleanup_test_data()
    cleanup_ok = (
        not Purch.objects.filter(
            Q(purch_supplier__username=TEST_USER) |
            Q(created_by__username=TEST_ADMIN)
        ).exists() and
        not PurchaseReturn.objects.filter(
            original_purchase__purch_supplier__username=TEST_USER
        ).exists() and
        not Product.objects.filter(product_name__startswith=TEST_MARKER).exists() and
        not User.objects.filter(username=TEST_USER).exists() and
        not User.objects.filter(username=TEST_ADMIN).exists() and
        not CashTransaction.objects.filter(notes__contains=TEST_MARKER).exists() and
        not Barcode.objects.filter(barcode_in__startswith=TEST_BARCODE_PREF).exists()
    )

    checks = [
        ('الحالة الأولية سليمة (1000/600/400/10)',                           initial_ok),
        ('إنشاء المرتجع ناجح (HTTP 302)',                                  redirect_302),
        ('سجل PurchaseReturn أُنشئ',                                       return_created),
        ('★ paid_amount لم يتغير بعد المرتجع (600 = 600) — جوهر الإصلاح',  paid_unchanged),
        ('★ balance_due لم يتغير بعد المرتجع (400 = 400)',                balance_unchanged),
        ('purch_final_total لم يتغير بعد المرتجع',                         total_unchanged),
        ('المخزون نقص 2 (10 → 8)',                                        stock_reduced_2),
        ('cash_balance زادت 200 (حركة الصندوق سليمة)',                    cash_in_200),
        ('حركة صندوق purchase_return موجودة',                              cash_tx_created),
        ('★ السلوك القديم اختفى كلياً (paid+200/balance-200)',             old_behavior_gone),
        ('حذف المرتجع ناجح',                                               return_deleted),
        ('★ paid_amount لم يتأثر بحذف المرتجع (600 = 600)',               paid_restored),
        ('★ balance_due لم يتأثر بحذف المرتجع (400 = 400)',               balance_restored),
        ('purch_final_total لم يتأثر بحذف المرتجع',                        total_restored),
        ('المخزون عاد 10 بعد حذف المرتجع',                                stock_restored),
        ('cash_balance عاد (حركة الصندوق حُذفت)',                         cash_restored),
        ('حركة الصندوق للمرتجع حُذفت',                                    cash_tx_deleted),
        ('التنظيف الذاتي نجح (لا بقایا)',                                  cleanup_ok),
    ]

    print()
    passed = 0
    for desc, ok in checks:
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
        if ok:
            passed += 1
    total = len(checks)
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/{total}")

    return (passed == total), passed


# ==================== نقطة الدخول ====================
print_header("فحص إغلاق — بند 1.1 من تقرير التدقيق (الخيار ب)")
print(f"  الموضوع: التحقق من حذف تعديل paid_amount عند إنشاء/حذف مرتجع الشراء")
print(f"  المنهجية: دورة كاملة (إنشاء فاتورة → مرتجع → حذف المرتجع)")
print(f"  المسارات المُختبرة:")
print(f"    - POST /invoice/purchases/<slug>/return/  → purch_return_create_view")
print(f"    - POST /invoice/purchase-returns/<slug>/delete/  → purchase_return_delete_view")
print(f"  العلامة المستخدمة: {TEST_MARKER}")

results = []
for i in [1, 2]:
    ok, count = run_test(i)
    results.append((ok, count))

print_header("الخلاصة النهائية")

both_pass    = all(ok for ok, _ in results)
same_count   = (results[0][1] == results[1][1])
final_count  = results[0][1]
total_checks = 18

print(f"  التشغيل 1: {results[0][1]}/{total_checks}")
print(f"  التشغيل 2: {results[1][1]}/{total_checks}")
print(f"  النتيجة متطابقة بين التشغيلين: {same_count}")
print(f"  النتيجة النهائية: {final_count}/{total_checks}")

if both_pass and same_count:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 1.1 أُغلق بدليل رقمي:")
    print(f"    - إنشاء مرتجع الشراء لم يعد يعدّل paid_amount في الفاتورة الأصلية")
    print(f"    - حذف مرتجع الشراء لم يعد يعدّل paid_amount أيضاً")
    print(f"    - حركة الصندوق (+200) ما زالت تُسجَّل بصحة عند الإنشاء")
    print(f"    - حركة الصندوق تُحذف بصحة عند حذف المرتجع")
    print(f"    - المخزون يُخصم عند المرتجع ويُعاد عند الحذف")
    print(f"    - السلوك متسق مع مرتجع المبيعات (لا تعديل على الفاتورة الأصلية)")
elif same_count and not both_pass:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
    print(f"  راجع الفحوصات الفاشلة أعلاه — قد يحتاج الكود إلى تعديل إضافي")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")
    print(f"  راجع السجل — قد تكون هناك بيانات متبقية")







    

print(f"\n{'=' * 70}")