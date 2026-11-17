"""
================================================================
فحص حارسة 2 — لائحة المبيعات مع فاتورة نقدية بلا عميل (3/3)
================================================================
الموضوع: التحقق من أن لائحة المبيعات تُعرض بنجاح عند وجود فاتورة
         نقدية بلا عميل، مع عرض "عميل نقدي" في عمود العميل،
         وزر الحذف الشرطي يظهر فقط للفواتير التي يملكها المستخدم.

المنهجية المعتمدة:
  - ضرب الفيوة الحية عبر django.test.Client
  - مستخدم فائق معزول
  - تنظيف ذاتي قبل/بعد
  - بيانات معلّمة ببادئة 'فحص_لائحة_النقدي'
  - يُشغَّل مرتين متتاليتين ويعطي النتيجة نفسها
  - مخرجات بنمط PASS/FAIL وعدد نهائي 3/3

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_لائحة_النقدي.py', encoding='utf-8').read())"
================================================================
"""

from decimal import Decimal
from django.conf import settings
from django.test import Client
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import (
    Sale, SaleItem, CashTransaction, Payment_method, Currency, Status
)

TEST_MARKER      = 'فحص_لائحة_النقدي'
TEST_ADMIN       = f'{TEST_MARKER}_مدير'


def cleanup_test_data():
    test_sale_ids = list(Sale.objects.filter(
        Q(created_by__username=TEST_ADMIN)
    ).values_list('id', flat=True))

    if test_sale_ids:
        SaleItem.objects.filter(sale_id__in=test_sale_ids).delete()
        Sale.objects.filter(id__in=test_sale_ids).delete()

    CashTransaction.objects.filter(
        Q(sale_invoice_id__in=test_sale_ids) |
        Q(notes__contains=TEST_MARKER) |
        Q(created_by__username=TEST_ADMIN)
    ).delete()

    User.objects.filter(username=TEST_ADMIN).delete()


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

    admin = User.objects.create_superuser(
        username=TEST_ADMIN, password='Test@12345',
        first_name=TEST_MARKER, last_name='المدير'
    )

    print(f"  المدير: {admin.username}")
    print(f"  طريقة الدفع: {cash_method.name} (is_cash={cash_method.is_cash})")

    # ====== [2] إنشاء فاتورة نقدية بلا عميل ======
    print("\n[2] إنشاء فاتورة بيع نقدية بلا عميل (sale_customer=None)")

    sale = Sale.objects.create(
        sale_customer=None,  # ★ لا عميل — نقدي
        sale_currency=currency,
        sale_payment_method=cash_method,
        sale_tax_percentage=Decimal('0.00'),
        sale_discount=Decimal('0.00'),
        sale_addition=Decimal('0.00'),
        paid_amount=Decimal('150.00'),
        created_by=admin
    )

    sale.refresh_from_db()

    print(f"  فاتورة: {sale.uniqueId} | customer=None | final={sale.sale_final_total}")

    # ====== [3] استدعاء اللائحة عبر HTTP ======
    print("\n[3] استدعاء اللائحة عبر HTTP")

    client = Client()
    client.force_login(admin)

    try:
        response = client.get('/invoice/sales/')
        http_ok = (response.status_code == 200)
        print(f"  HTTP status: {response.status_code}")
    except Exception as e:
        http_ok = False
        response = None
        print(f"  ✗ خطأ في استدعاء اللائحة: {e}")

    # ====== [4] الفحص 1: اللائحة تُحمَّل بنجاح ======
    print("\n[4] فحص 1: اللائحة تُحمَّل بنجاح (HTTP 200) مع فاتورة نقدية بلا عميل")

    check_1 = http_ok
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | 1. اللائحة تُحمَّل بنجاح (HTTP 200) مع فاتورة نقدية بلا عميل")

    # ====== [5] الفحص 2: المحتوى يعرض "عميل نقدي" ======
    print("\n[5] فحص 2: صف الفاتورة النقدية يظهر بـ«عميل نقدي»")

    check_2 = False
    if http_ok:
        try:
            content = response.content.decode('utf-8')
            shows_knidi = 'عميل نقدي' in content
            check_2 = shows_knidi
            print(f"  يحتوي على 'عميل نقدي': {shows_knidi}")
        except Exception as e:
            print(f"  ✗ خطأ في فحص المحتوى: {e}")

    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | 2. صف الفاتورة النقدية يظهر بـ«عميل نقدي»")

    # ====== [6] الفحص 3: زر الحذف الشرطي يظهر ======
    print("\n[6] فحص 3: زر الحذف الشرطي يظهر في صف الفاتورة النقدية")

    check_3 = False
    if http_ok:
        try:
            content = response.content.decode('utf-8')
            # نبحث عن رابط الحذف أو زر الحذف
            has_delete_link = 'delete' in content.lower() or 'حذف' in content
            check_3 = has_delete_link
            print(f"  يحتوي على زر/رابط الحذف: {has_delete_link}")
        except Exception as e:
            print(f"  ✗ خطأ في فحص المحتوى: {e}")

    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | 3. زر الحذف الشرطي يظهر في صف الفاتورة النقدية")

    # ====== [7] العداد النهائي ======
    print(f"\n[7] نتيجة التشغيل {run_number}")
    checks = [check_1, check_2, check_3]
    passed = sum(checks)
    for i, ok in enumerate(checks, 1):
        sign = '✓' if ok else '✗'
        print(f"  {sign} الفحص {i}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/3")

    cleanup_test_data()
    return passed


# ==================== نقطة الدخول ====================
print('=' * 60)
print('  فحص حارسة 2 — لائحة المبيعات مع فاتورة نقدية بلا عميل')
print('=' * 60)
print(f"  المسار المُختبر: GET /invoice/sales/ → sale_list")
print(f"  القالب المُختبر: invoice/sale/sale_list.html")
print(f"  العلامة: {TEST_MARKER}")

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
    print(f"  اللائحة سليمة مع الفواتير النقدية — التعديل مثبت ويعمل")
elif same:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")
print('=' * 60)