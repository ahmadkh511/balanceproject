"""
================================================================
فحص إثبات + إغلاق — بند 3.6 من تقرير التدقيق
================================================================
الموضوع: نقل get_or_create من clean() لـ save() في CashTransaction

المشكلة:
  - في invoice/models.py، CashTransaction.clean() تستخدم get_or_create
    لتعيين طريقة الدفع النقدية تلقائياً.
  - clean() مُصمم للتحقق (validation)، لا لتعديل البيانات أو إنشاء سجلات.
  - هذا قد يُسبب آثاراً جانبية غير متوقعة (مثل IntegrityError أو تكرار غير مرغوب).

الإصلاح المقترح:
  - نقل منطق get_or_create من clean() إلى save() (المكان الصحيح لتعديل البيانات).
  - clean() تبقى للتحقق فقط.

السيناريوهات:
  1) إنشاء CashTransaction بنوع 'withdrawal' بدون payment_method → يجب أن يُعيّن تلقائياً في save()
  2) فحص static للكود: clean() لا يحوي get_or_create
  3) فحص static للكود: save() يحوي get_or_create

المنهجية:
  - استدعاء مباشر للنموذج + فحص static للكود
  - 3 فحوصات × تشغيلان متطابقان = 6 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_3_6.py', encoding='utf-8').read())"
================================================================
"""

import os
import re
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import CashTransaction, Payment_method

TEST_MARKER = 'فحص_3_6'
TEST_ADMIN = f'{TEST_MARKER}_مدير'

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
    test_user_ids = list(User.objects.filter(username=TEST_ADMIN).values_list('id', flat=True))
    CashTransaction.objects.filter(created_by_id__in=test_user_ids).delete()
    User.objects.filter(username=TEST_ADMIN).delete()
    
    # تنظيف طريقة الدفع الاختبارية إن وُجدت (لا نحذف 'نقداً' لأنها قد تكون مستخدمة)
    # Payment_method.objects.filter(name='نقداً').delete()  # نتركها


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    cleanup_test_data()
    
    admin = User.objects.create_superuser(
        username=TEST_ADMIN, password='Test@12345', first_name=TEST_MARKER, last_name='المدير'
    )
    
    # ====== [1] فحص 1: السلوك الحي (تعيين payment_method تلقائياً) ======
    print_step(1, "فحص 1: إنشاء CashTransaction بنوع 'withdrawal' بدون payment_method")
    
    try:
        tx = CashTransaction.objects.create(
            transaction_type='withdrawal',
            amount_in=Decimal('0.00'),
            amount_out=Decimal('50.00'),
            created_by=admin
        )
        tx.refresh_from_db()
        
        # التحقق من تعيين payment_method
        check_1 = (tx.payment_method is not None and tx.payment_method.name == 'نقداً')
        sign = '✓' if check_1 else '✗'
        print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | payment_method = {tx.payment_method} (متوقع: نقداً)")
    except Exception as e:
        print(f"  ✗ خطأ: {e}")
        check_1 = False
    
    # ====== [2] فحص static للكود ======
    print_step(2, "فحص static للكود (نقل get_or_create من clean() لـ save())")
    
    models_content = read_models_py()
    
    # استخراج جسم كلاس CashTransaction
    class_match = re.search(r'class CashTransaction\(models\.Model\):(.*?)(?=\nclass |\Z)', models_content, re.DOTALL)
    if class_match:
        class_body = class_match.group(1)
        
        # استخراج جسم دالة clean
        clean_match = re.search(r'def clean\(.*?\):(.*?)(?=\n    def |\n    class |\Z)', class_body, re.DOTALL)
        clean_body = clean_match.group(1) if clean_match else ""
        
        # استخراج جسم دالة save
        save_match = re.search(r'def save\(.*?\):(.*?)(?=\n    def |\n    class |\Z)', class_body, re.DOTALL)
        save_body = save_match.group(1) if save_match else ""
        
        # فحص 2: clean() لا يحوي get_or_create
        print_step(3, "فحص 2: ★ clean() لا يحوي get_or_create (للتحقق فقط)")
        check_2 = ("get_or_create" not in clean_body)
        sign = '✓' if check_2 else '✗'
        print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | clean() خالية من get_or_create")
        if not check_2:
            print(f"     ✗ العلة: clean() ما زالت تعدل البيانات بدل التحقق فقط")
        
        # فحص 3: save() يحوي get_or_create
        print_step(4, "فحص 3: ★ save() يحوي get_or_create (المكان الصحيح)")
        check_3 = ("get_or_create" in save_body)
        sign = '✓' if check_3 else '✗'
        print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | save() تحتوي على get_or_create")
        if not check_3:
            print(f"     ✗ العلة: save() لا تقوم بتعيين payment_method تلقائياً")
    else:
        print(f"  ✗ تعذّر العثور على كلاس CashTransaction")
        check_2 = False
        check_3 = False
    
    # ====== [5] العداد النهائي ======
    print_step(5, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3]
    descriptions = [
        'إنشاء CashTransaction يُعيّن payment_method تلقائياً',
        '★ clean() لا يحوي get_or_create (للتحقق فقط)',
        '★ save() يحوي get_or_create (المكان الصحيح)',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/3")
    
    cleanup_test_data()
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 3.6 من تقرير التدقيق")
print(f"  الموضوع: نقل get_or_create من clean() لـ save() في CashTransaction")
print(f"  المنهجية: استدعاء مباشر + فحص static للكود + 3 فحوصات × تشغيلان")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    p, checks = run_test(i)
    all_results.append((p, checks))

print_header("الخلاصة النهائية")

run1_p, run1_checks = all_results[0]
run2_p, run2_checks = all_results[1]
same_run = (run1_checks == run2_checks)

print(f"  التشغيل 1: {run1_p}/3")
print(f"  التشغيل 2: {run2_p}/3")
print(f"  متطابقة: {same_run}")
print(f"  النتيجة النهائية: {run1_p}/3")

if run1_p == 3 and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 3.6 أُغلق بدليل رقمي:")
    print(f"    - get_or_create نُقلت من clean() إلى save()")
    print(f"    - السلوك الحي يعمل بشكل صحيح (payment_method يُعيّن تلقائياً)")
elif same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")