"""
================================================================
فحص إثبات + إغلاق — بند 3.4 من تقرير التدقيق
================================================================
الموضوع: إصلاح use_ssl في إعدادات البريد (قراءة من قاعدة البيانات)

المشكلة:
  - في invoice/utils.py، الدالة get_active_email_connection تستخدم use_ssl=False
    مُضمّن (hardcoded) دائماً.
  - هذا يمنع الاتصال بمزودات البريد التي تتطلب SSL بدل TLS.

الإصلاح المقترح:
  - إضافة حقل email_use_ssl لنموذج EmailSetting (models.py)
  - تعديل get_active_email_connection (utils.py) ليقرأ config.email_use_ssl
  - تعديل EmailSettingForm (forms.py) لعرض الحقل الجديد

المنهجية:
  - فحص static للكود (models.py, utils.py)
  - استدعاء مباشر للنموذج
  - 3 فحوصات × تشغيلان متطابقان = 6 قياسات
  - يتطلب migration بعد إضافة الحقل

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_3_4.py', encoding='utf-8').read())"
================================================================
"""

import os
from django.conf import settings
from django.contrib.auth import get_user_model

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import EmailSetting

TEST_MARKER = 'فحص_3_4'
UTILS_PY_PATH = os.path.join(settings.BASE_DIR, 'invoice', 'utils.py')
MODELS_PY_PATH = os.path.join(settings.BASE_DIR, 'invoice', 'models.py')


def read_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    
    # ====== [1] فحص 1: وجود حقل email_use_ssl في EmailSetting ======
    print_step(1, "فحص 1: ★ وجود حقل email_use_ssl في EmailSetting (models.py)")
    
    try:
        # محاولة الوصول للحقل
        es = EmailSetting.objects.first()
        if es is None:
            # إن لم يوجد سجل، نُنشئ مؤقتاً ونحذفه
            es = EmailSetting.objects.create(
                email_backend='django.core.mail.backends.locmem.EmailBackend',
                email_host='test', email_port=587, email_use_tls=False,
                email_host_user='t@t.com', email_host_password='t',
                default_from_email='t@t.com'
            )
            created_temp = True
        else:
            created_temp = False
        
        # محاولة قراءة الحقل
        try:
            ssl_value = es.email_use_ssl
            check_1 = True
            print(f"  ✓ الحقل email_use_ssl موجود. القيمة الحالية: {ssl_value}")
        except AttributeError:
            check_1 = False
            print(f"  ✗ الحقل email_use_ssl غير موجود في النموذج (يتطلب migration)")
        
        # تنظيف المؤقت
        if created_temp:
            es.delete()
            
    except Exception as e:
        check_1 = False
        print(f"  ✗ خطأ: {e}")
    
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | الحقل موجود في النموذج")
    
    # ====== [2] فحص 2: استخدام config.email_use_ssl في utils.py ======
    print_step(2, "فحص 2: ★ استخدام config.email_use_ssl في utils.py (بدل hardcoded False)")
    
    utils_content = read_file(UTILS_PY_PATH)
    
    old_pattern = "use_ssl=False"
    new_pattern = "use_ssl=config.email_use_ssl"
    
    old_found = old_pattern in utils_content
    new_found = new_pattern in utils_content
    
    if old_found:
        print(f"  ✗ نمط قديم موجود: use_ssl=False (hardcoded)")
    if new_found:
        print(f"  ✓ نمط جديد موجود: use_ssl=config.email_use_ssl (ديناميكي)")
    
    check_2 = new_found and not old_found
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | قراءة use_ssl من قاعدة البيانات")
    
    # ====== [3] فحص 3: حقل email_use_ssl معرّف في models.py ======
    print_step(3, "فحص 3: حقل email_use_ssl معرّف في models.py")
    
    models_content = read_file(MODELS_PY_PATH)
    
    field_defined = "email_use_ssl" in models_content and "models.BooleanField" in models_content
    
    # تحقق أدق: البحث عن السطر
    field_line_found = False
    for line in models_content.split('\n'):
        if 'email_use_ssl' in line and 'models.' in line:
            field_line_found = True
            print(f"  ✓ السطر: {line.strip()}")
            break
    
    check_3 = field_line_found
    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | الحقل معرّف في models.py")
    
    # ====== [4] العداد النهائي ======
    print_step(4, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3]
    descriptions = [
        '★ حقل email_use_ssl موجود في EmailSetting (يتطلب migration)',
        '★ استخدام config.email_use_ssl في utils.py (بدل hardcoded False)',
        'حقل email_use_ssl معرّف في models.py',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/3")
    
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 3.4 من تقرير التدقيق")
print(f"  الموضوع: use_ssl في إعدادات البريد")
print(f"  المنهجية: فحص static + استدعاء مباشر + 3 فحوصات × تشغيلان")
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
    print(f"  بند 3.4 أُغلق بدليل رقمي:")
    print(f"    - حقل email_use_ssl أُضيف لـ EmailSetting")
    print(f"    - get_active_email_connection يقرأ config.email_use_ssl")
    print(f"    - البريد يدعم SSL و TLS حسب إعداد المستخدم")
elif same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✗ use_ssl=False مُضمّن (hardcoded) ولا يُقرأ من قاعدة البيانات")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")