"""
================================================================
فحص إثبات + إغلاق — بند 3.3 من تقرير التدقيق
================================================================
الموضوع: إصلاح توليد أرقام الفواتير (استخدام aggregate(Max) بدل order_by)

المشكلة:
  - الكود الحالي يستخدم Purch.objects.order_by('-_last_invoice_number').first()
  - يحمل كائن الفاتورة بالكامل للذاكرة (كفاءة منخفضة)
  - عرضة لـ Race Condition (فواتير مكررة عند التزامن)

الإصلاح المقترح:
  - استخدام aggregate(Max('_last_invoice_number')) بدل order_by().first()
  - أسرع (SQL MAX) ولا يحمل كائناً للذاكرة

السيناريوهات:
  1) توليد رقم فاتورة شراء جديد (P000X)
  2) توليد رقم فاتورة بيع جديد (S000X)
  3) توليد فاتورتين متتاليتين (أرقام متتالية)
  4) فحص static للكود: استخدام aggregate(Max) بدل order_by().first()

المنهجية:
  - استدعاء مباشر للنماذج + فحص static للكود
  - 4 فحوصات × تشغيلان متطابقان = 8 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_3_3.py', encoding='utf-8').read())"
================================================================
"""

import os
import re
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import Purch, Sale, Payment_method, Currency

TEST_MARKER = 'فحص_3_3'
TEST_ADMIN = f'{TEST_MARKER}_مدير'
TEST_SUPPLIER = f'{TEST_MARKER}_مورد'
TEST_CUSTOMER = f'{TEST_MARKER}_عميل'

MODELS_PY_PATH = os.path.join(settings.BASE_DIR, 'invoice', 'models.py')


def read_models_py():
    with open(MODELS_PY_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def cleanup_test_data():
    """تنظيف شامل"""
    test_user_ids = list(User.objects.filter(
        username__in=[TEST_SUPPLIER, TEST_CUSTOMER, TEST_ADMIN]
    ).values_list('id', flat=True))
    
    test_purch_ids = list(Purch.objects.filter(
        Q(purch_supplier_id__in=test_user_ids) | Q(created_by_id__in=test_user_ids)
    ).values_list('id', flat=True))
    test_sale_ids = list(Sale.objects.filter(
        Q(sale_customer_id__in=test_user_ids) | Q(created_by_id__in=test_user_ids)
    ).values_list('id', flat=True))
    
    Purch.objects.filter(id__in=test_purch_ids).delete()
    Sale.objects.filter(id__in=test_sale_ids).delete()
    User.objects.filter(id__in=test_user_ids).delete()


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    cleanup_test_data()
    
    # ====== [1] إعداد البيانات ======
    print_step(1, "إعداد البيانات الأساسية")
    
    currency = Currency.objects.filter(is_default=True).first()
    if not currency:
        currency = Currency.objects.first()
    
    cash_method = Payment_method.objects.filter(is_cash=True).first()
    
    supplier = User.objects.create(username=TEST_SUPPLIER, first_name=TEST_MARKER)
    customer = User.objects.create(username=TEST_CUSTOMER, first_name=TEST_MARKER)
    admin = User.objects.create_superuser(
        username=TEST_ADMIN, password='Test@12345', first_name=TEST_MARKER, last_name='المدير'
    )
    print(f"  تم إنشاء مستخدمين اختباريين")
    
    # ====== [2] فحص 1: توليد رقم فاتورة شراء ======
    print_step(2, "فحص 1: توليد رقم فاتورة شراء جديد (P000X)")
    
    purch1 = Purch.objects.create(
        purch_supplier=supplier,
        purch_currency=currency,
        purch_payment_method=cash_method,
        paid_amount=Decimal('100.00'),
        created_by=admin
    )
    purch1.refresh_from_db()
    
    pattern_purch = re.match(r'^P(\d+)$', purch1.uniqueId)
    check_1 = bool(pattern_purch)
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | رقم الفاتورة: {purch1.uniqueId} (المتوقع: P000X)")
    
    # ====== [3] فحص 2: توليد رقم فاتورة بيع ======
    print_step(3, "فحص 2: توليد رقم فاتورة بيع جديد (S000X)")
    
    sale1 = Sale.objects.create(
        sale_customer=customer,
        sale_currency=currency,
        sale_payment_method=cash_method,
        paid_amount=Decimal('100.00'),
        created_by=admin
    )
    sale1.refresh_from_db()
    
    pattern_sale = re.match(r'^S(\d+)$', sale1.uniqueId)
    check_2 = bool(pattern_sale)
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | رقم الفاتورة: {sale1.uniqueId} (المتوقع: S000X)")
    
    # ====== [4] فحص 3: فاتورتين متتاليتين ======
    print_step(4, "فحص 3: توليد فاتورتين متتاليتين (أرقام متتالية)")
    
    purch2 = Purch.objects.create(
        purch_supplier=supplier,
        purch_currency=currency,
        purch_payment_method=cash_method,
        paid_amount=Decimal('200.00'),
        created_by=admin
    )
    purch2.refresh_from_db()
    
    num1 = int(pattern_purch.group(1))
    num2 = int(re.match(r'^P(\d+)$', purch2.uniqueId).group(1))
    
    check_3 = (num2 == num1 + 1)
    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | الفاتورة الثانية: {purch2.uniqueId} (المتوقع: {num1 + 1:04d})")
    
    # ====== [5] فحص 4: فحص static للكود ======
    print_step(5, "فحص 4: ★ فحص الكود (استخدام aggregate(Max) بدل order_by)")
    
    models_content = read_models_py()
    
    # فحص النص كاملاً بدل فحص سطر بسطر (لأن aggregate قد تكون متعددة الأسطر)
    old_pattern_found = "order_by('-_last_invoice_number').first()" in models_content or \
                        'order_by("-_last_invoice_number").first()' in models_content
    
    new_pattern_found = "aggregate(" in models_content and \
                        "Max('_last_invoice_number')" in models_content and \
                        "Max('_last_return_number')" in models_content
    
    if old_pattern_found:
        print(f"  ✗ نمط قديم موجود: order_by('-_last_invoice_number').first()")
    if new_pattern_found:
        print(f"  ✓ نمط جديد موجود: aggregate(Max('_last_invoice_number'))")
    
    check_4 = new_pattern_found and not old_pattern_found
    sign = '✓' if check_4 else '✗'
    print(f"  {sign} {'PASS' if check_4 else 'FAIL'} | استخدام aggregate(Max) بدل order_by().first()")
    
    # ====== [6] العداد النهائي ======
    print_step(6, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3, check_4]
    descriptions = [
        'توليد رقم فاتورة شراء جديد (P000X)',
        'توليد رقم فاتورة بيع جديد (S000X)',
        'توليد فاتورتين متتاليتين (أرقام متتالية)',
        '★ استخدام aggregate(Max) بدل order_by().first()',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/4")
    
    cleanup_test_data()
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 3.3 من تقرير التدقيق")
print(f"  الموضوع: توليد أرقام الفواتير (aggregate(Max))")
print(f"  المنهجية: استدعاء مباشر + فحص static للكود + 4 فحوصات × تشغيلان")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    p, checks = run_test(i)
    all_results.append((p, checks))

print_header("الخلاصة النهائية")

run1_p, run1_checks = all_results[0]
run2_p, run2_checks = all_results[1]
same_run = (run1_checks == run2_checks)

print(f"  التشغيل 1: {run1_p}/4")
print(f"  التشغيل 2: {run2_p}/4")
print(f"  متطابقة: {same_run}")
print(f"  النتيجة النهائية: {run1_p}/4")

check_4_passes = run1_checks[3]

if run1_p == 4 and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 3.3 أُغلق بدليل رقمي:")
    print(f"    - توليد أرقام الفواتير يعمل بشكل صحيح")
    print(f"    - استخدام aggregate(Max) بدل order_by().first()")
elif not check_4_passes and same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✗ الفحص 4 فشل: الكود يستخدم order_by().first() بدل aggregate(Max)")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")