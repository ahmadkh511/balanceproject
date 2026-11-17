"""
================================================================
فحص حارسة 1 — حذف فاتورة البيع كاملة (10/10)
================================================================
الموضوع: التحقق من أن حذف فاتورة البيع يسترجع كل شيء بشكل صحيح
         (المخزون، الباركودات، حركات الصندوق) — معاملة ذرية واحدة

المنهجية المعتمدة:
  - ضرب الفيوة الحية عبر django.test.Client
  - مستخدم فائق معزول
  - تنظيف ذاتي قبل/بعد
  - بيانات معلّمة ببادئة 'فحص_حذف_البيع'
  - يُشغَّل مرتين متتاليتين ويعطي النتيجة نفسها
  - مخرجات بنمط PASS/FAIL وعدد نهائي 10/10

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_حذف_البيع.py', encoding='utf-8').read())"
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
    Sale, SaleItem, SaleItemBarcode, SaleReturn,
    Barcode, Product, CashTransaction, Payment_method, Currency
)

TEST_MARKER      = 'فحص_حذف_البيع'
TEST_ADMIN       = f'{TEST_MARKER}_مدير'
TEST_CUSTOMER    = f'{TEST_MARKER}_عميل'
TEST_PRODUCT     = f'{TEST_MARKER}_منتج'
TEST_BARCODE_PREF = f'{TEST_MARKER}_باركود_'


def cleanup_test_data():
    test_sale_ids = list(Sale.objects.filter(
        Q(sale_customer__username=TEST_CUSTOMER) |
        Q(created_by__username=TEST_ADMIN)
    ).values_list('id', flat=True))

    if test_sale_ids:
        SaleItemBarcode.objects.filter(sale_item__sale_id__in=test_sale_ids).delete()
        SaleItem.objects.filter(sale_id__in=test_sale_ids).delete()
        Sale.objects.filter(id__in=test_sale_ids).delete()

    CashTransaction.objects.filter(
        Q(sale_invoice_id__in=test_sale_ids) |
        Q(notes__contains=TEST_MARKER) |
        Q(created_by__username=TEST_ADMIN)
    ).delete()

    Barcode.objects.filter(barcode_in__startswith=TEST_BARCODE_PREF).delete()
    Product.objects.filter(product_name__startswith=TEST_MARKER).delete()
    User.objects.filter(username__in=[TEST_CUSTOMER, TEST_ADMIN]).delete()


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

    # المنتج بكمية ابتدائية 5
    product = Product.objects.create(
        product_name=TEST_PRODUCT,
        purch_price=Decimal('100.00'),
        sale_price=Decimal('150.00'),
        current_stock_quantity=Decimal('5.00'),
        average_purchase_cost=Decimal('100.00')
    )

    bc1 = Barcode.objects.create(
        barcode_in=f'{TEST_BARCODE_PREF}1',
        product=product, status='active', is_primary=False
    )
    bc2 = Barcode.objects.create(
        barcode_in=f'{TEST_BARCODE_PREF}2',
        product=product, status='active', is_primary=False
    )

    print(f"  المنتج: {product.product_name} | مخزون ابتدائي: 5")
    print(f"  الباركودات: {bc1.barcode_in}, {bc2.barcode_in} (نشطة)")

    # ====== [2] إنشاء فاتورة بيع ======
    print("\n[2] إنشاء فاتورة بيع (بيع 2 وحدة = 300، مدفوع 300 نقداً)")

    sale = Sale.objects.create(
        sale_customer=customer,
        sale_currency=currency,
        sale_payment_method=cash_method,
        sale_tax_percentage=Decimal('0.00'),
        sale_discount=Decimal('0.00'),
        sale_addition=Decimal('0.00'),
        paid_amount=Decimal('300.00'),
        created_by=admin
    )

    sale_item = SaleItem.objects.create(
        sale=sale,
        product=product,
        item_name=product.product_name,
        sold_quantity=Decimal('2.00'),
        quantity_with_barcode=Decimal('2.00'),
        quantity_without_barcode=Decimal('0.00'),
        unit_price=Decimal('150.00'),
        sale_currency=currency,
        exchange_rate_at_sale=Decimal('1.00')
    )

    # ربط الباركودين وتغيير حالتهما إلى sold
    sib1 = SaleItemBarcode.objects.create(
        sale_item=sale_item, barcode=bc1,
        quantity_used=Decimal('1.00'), barcode_status='active'
    )
    sib2 = SaleItemBarcode.objects.create(
        sale_item=sale_item, barcode=bc2,
        quantity_used=Decimal('1.00'), barcode_status='active'
    )
    bc1.status = 'sold'; bc1.save()
    bc2.status = 'sold'; bc2.save()

    # خصم المخزون (البيع يخصم)
    product.current_stock_quantity = Decimal('5.00') - Decimal('2.00')
    product.save(update_fields=['current_stock_quantity'])
    product.refresh_from_db()

    # حساب الإجماليات
    sale.calculate_and_save_totals()
    sale.refresh_from_db()

    # حركة الصندوق
    CashTransaction.objects.create(
        transaction_date=__import__('django.utils.timezone', fromlist=['now']).now(),
        amount_in=Decimal('300.00'),
        amount_out=Decimal('0.00'),
        transaction_type='sale_receipt',
        sale_invoice=sale,
        notes=f'{TEST_MARKER} تحصيل نقدي',
        created_by=admin,
        payment_method=cash_method
    )

    print(f"  فاتورة: {sale.uniqueId} | final={sale.sale_final_total} | paid={sale.paid_amount}")
    print(f"  المخزون بعد البيع: {product.current_stock_quantity} (5 - 2 = 3)")
    print(f"  الباركودات: status={bc1.status}, {bc2.status}")

    # ====== [3] لقطة قبل الحذف ======
    print("\n[3] لقطة قبل الحذف")

    sale_exists_before     = Sale.objects.filter(pk=sale.pk).exists()
    sale_item_count_before  = SaleItem.objects.filter(sale=sale).count()
    sib_count_before        = SaleItemBarcode.objects.filter(sale_item=sale_item).count()
    cash_count_before       = CashTransaction.objects.filter(sale_invoice=sale).count()
    bc_sold_before          = Barcode.objects.filter(barcode_in__in=[bc1.barcode_in, bc2.barcode_in], status='sold').count()
    stock_before            = product.current_stock_quantity

    print(f"  الفاتورة موجودة: {sale_exists_before}")
    print(f"  بنود الفاتورة: {sale_item_count_before}")
    print(f"  روابط الباركود: {sib_count_before}")
    print(f"  حركات الصندوق: {cash_count_before}")
    print(f"  باركودات status=sold: {bc_sold_before}")
    print(f"  المخزون: {stock_before}")

    state_ok = (
        sale_exists_before and
        sale_item_count_before == 1 and
        sib_count_before == 2 and
        cash_count_before == 1 and
        bc_sold_before == 2 and
        stock_before == Decimal('3.00')
    )
    print(f"  ✓ الحالة قبل الحذف سليمة: {state_ok}")

    # ====== [4] محاولة الحذف بـ GET (يجب ألا يحذف) ======
    print("\n[4] محاولة الحذف بـ GET (يجب ألا يحذف — يحوّل لتفاصيل الفاتورة)")

    client = Client()
    client.force_login(admin)

    response_get = client.get(f'/invoice/sale/{sale.slug}/delete/')
    print(f"  HTTP status: {response_get.status_code}")
    print(f"  الفاتورة ما زالت موجودة بعد GET: {Sale.objects.filter(pk=sale.pk).exists()}")

    get_did_not_delete = (
        response_get.status_code == 302 and
        Sale.objects.filter(pk=sale.pk).exists()
    )
    print(f"  ✓ GET لم يحذف (آمن): {get_did_not_delete}")

    # ====== [5] الحذف بـ POST ======
    print("\n[5] الحذف بـ POST (المسار الحقيقي للحذف)")

    response_post = client.post(f'/invoice/sale/{sale.slug}/delete/', {})
    print(f"  HTTP status: {response_post.status_code}")
    if hasattr(response_post, 'url'):
        print(f"  Redirect to: {response_post.url}")

    # ====== [6] لقطة بعد الحذف ======
    print("\n[6] لقطة بعد الحذف — يجب أن يُسترجع كل شيء")

    sale_exists_after      = Sale.objects.filter(pk=sale.pk).exists()
    sale_item_count_after  = SaleItem.objects.filter(sale_id=sale.pk).count()
    sib_count_after        = SaleItemBarcode.objects.filter(sale_item__sale_id=sale.pk).count()
    cash_count_after       = CashTransaction.objects.filter(sale_invoice_id=sale.pk).count()

    bc1.refresh_from_db()
    bc2.refresh_from_db()
    bc_active_after = 0
    if bc1.status == 'active': bc_active_after += 1
    if bc2.status == 'active': bc_active_after += 1

    product.refresh_from_db()
    stock_after = product.current_stock_quantity

    print(f"  الفاتورة موجودة: {sale_exists_after} (يجب False)")
    print(f"  بنود الفاتورة: {sale_item_count_after} (يجب 0)")
    print(f"  روابط الباركود: {sib_count_after} (يجب 0)")
    print(f"  حركات الصندوق: {cash_count_after} (يجب 0)")
    print(f"  باركودات status=active: {bc_active_after} (يجب 2)")
    print(f"  المخزون: {stock_after} (يجب 5 — عاد للأصلي)")

    # ====== [7] فحوصات الحارسة ======
    print("\n[7] فحوصات الحارسة")

    cleanup_test_data()
    cleanup_ok = (
        not Sale.objects.filter(
            Q(sale_customer__username=TEST_CUSTOMER) |
            Q(created_by__username=TEST_ADMIN)
        ).exists() and
        not Product.objects.filter(product_name__startswith=TEST_MARKER).exists() and
        not User.objects.filter(username__in=[TEST_CUSTOMER, TEST_ADMIN]).exists() and
        not CashTransaction.objects.filter(notes__contains=TEST_MARKER).exists() and
        not Barcode.objects.filter(barcode_in__startswith=TEST_BARCODE_PREF).exists()
    )

    checks = [
        ('الحالة قبل الحذف سليمة (فاتورة + بند + باركودان + حركة صندوق + مخزون 3)',  state_ok),
        ('★ GET لا يحذف (يعيد التوجيه لتفاصيل الفاتورة)',                       get_did_not_delete),
        ('★ POST يحذف بنجاح (HTTP 302)',                                     response_post.status_code == 302),
        ('الفاتورة حُذفت من قاعدة البيانات',                                  not sale_exists_after),
        ('بنود الفاتورة حُذفت (SaleItem.count = 0)',                          sale_item_count_after == 0),
        ('روابط الباركود حُذفت (SaleItemBarcode.count = 0)',                 sib_count_after == 0),
        ('حركات الصندوق حُذفت (CashTransaction.count = 0)',                  cash_count_after == 0),
        ('★ الباركودات عادت نشطة (status=active, count = 2)',                bc_active_after == 2),
        ('★ المخزون استُرجع (3 → 5 — عاد للأصلي)',                            stock_after == Decimal('5.00')),
        ('التنظيف الذاتي نجح (لا بقایا)',                                     cleanup_ok),
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
    return passed


# ==================== نقطة الدخول ====================
print('=' * 60)
print('  فحص حارسة 1 — حذف فاتورة البيع (10/10)')
print('=' * 60)
print(f"  المسار المُختبر: POST /invoice/sale/<slug>/delete/ → sale_delete")
print(f"  العلامة: {TEST_MARKER}")

results = []
for i in [1, 2]:
    p = run_test(i)
    results.append(p)

print(f"\n{'=' * 60}")
print(f"  التشغيل 1: {results[0]}/10")
print(f"  التشغيل 2: {results[1]}/10")
same = (results[0] == results[1])
print(f"  متطابقة: {same}")
final = results[0]
print(f"  النتيجة النهائية: {final}/10")

if final == 10 and same:
    print(f"\n  ✅ PASS — الحارسة سليمة في التشغيلين بنفس النتيجة")
elif same:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")
print('=' * 60)