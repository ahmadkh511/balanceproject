"""
================================================================
فحص إثبات + إغلاق — بند 2.3 من تقرير التدقيق
================================================================
الموضوع: حذف send_custom_email المكررة في views.py

المشكلة: views.py يعرّف نسخة محلية من send_custom_email تستخدم نمطاً
قديماً (auth_user/auth_password بدل connection=). النسخة المحلية
تُغطي على النسخة الصحيحة المُستوردة من utils.py.

الإصلاح: حذف التعريف المحلي من views.py، والاعتماد على النسخة
الصحيحة في utils.py فقط (مبدأ DRY).

المنهجية:
  - فحص كود (static check) + استدعاء مباشر
  - 5 فحوصات × تشغيلان متطابقان = 10 قياسات
  - يُشغَّل مرتين متتاليتين ويعطي النتيجة نفسها

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_2_3.py', encoding='utf-8').read())"
================================================================
"""

import os
from django.conf import settings
from django.core import mail
from django.contrib.auth import get_user_model

# حارسة ALLOWED_HOSTS
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.utils import send_custom_email as utils_send_custom_email
from invoice.models import EmailSetting

TEST_MARKER = 'فحص_2_3'

# حفظ الإعدادات الأصلية
_ORIGINAL_EMAIL_BACKEND = getattr(settings, 'EMAIL_BACKEND', None)

VIEWS_PY_PATH = os.path.join(settings.BASE_DIR, 'invoice', 'views.py')


def read_views_py():
    """قراءة محتوى views.py"""
    with open(VIEWS_PY_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")

    # ====== [1] فحص 1: send_custom_email موجودة في utils.py ======
    print_step(1, "فحص 1: send_custom_email موجودة في utils.py")

    try:
        from invoice.utils import send_custom_email
        check_1 = callable(send_custom_email)
        print(f"  send_custom_email موجودة في utils.py: {check_1}")
    except ImportError:
        check_1 = False
        print(f"  ✗ send_custom_email غير موجودة في utils.py")

    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | 1. send_custom_email في utils.py")

    # ====== [2] فحص 2: send_custom_email مُستوردة في views.py ======
    print_step(2, "فحص 2: send_custom_email مُستوردة في views.py")

    views_content = read_views_py()
    import_found = False
    for line in views_content.split('\n'):
        stripped = line.strip()
        if 'import' in stripped and 'send_custom_email' in stripped:
            import_found = True
            print(f"  سطر الاستيراد: {stripped}")
            break

    check_2 = import_found
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | 2. send_custom_email مُستوردة في views.py")

    # ====== [3] فحص 3: send_custom_email محذوفة من views.py ======
    print_step(3, "فحص 3: ★ send_custom_email محذوفة من views.py (لا يوجد تعريف محلي)")

    local_def_found = False
    local_def_line = ''
    for line in views_content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('def send_custom_email'):
            local_def_found = True
            local_def_line = stripped
            break

    check_3 = not local_def_found
    if local_def_found:
        print(f"  ✗ تعريف محلي موجود: {local_def_line}")
    else:
        print(f"  ✓ لا يوجد تعريف محلي لـ send_custom_email في views.py")

    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | 3. لا يوجد تعريف محلي في views.py")

    # ====== [4] فحص 4: send_custom_email من utils.py تعمل عبر locmem ======
    print_step(4, "فحص 4: send_custom_email من utils.py تعمل عبر locmem (تُرجع tuple)")

    # حفظ EmailSetting الأصلية
    original_es = EmailSetting.objects.filter(pk=1).first()
    original_es_data = None
    if original_es:
        original_es_data = {
            'email_backend': original_es.email_backend,
            'email_host': original_es.email_host,
            'email_port': original_es.email_port,
            'email_use_tls': original_es.email_use_tls,
            'email_host_user': original_es.email_host_user,
            'email_host_password': original_es.email_host_password,
            'default_from_email': original_es.default_from_email,
        }

    # ضبط locmem backend
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    mail.outbox = []

    # تحديث EmailSetting بقيم locmem
    EmailSetting.objects.update_or_create(
        pk=1,
        defaults={
            'email_backend': 'django.core.mail.backends.locmem.EmailBackend',
            'email_host': 'test.host',
            'email_port': 587,
            'email_use_tls': True,
            'email_host_user': 'test@test.com',
            'email_host_password': 'test_pass',
            'default_from_email': 'test_from@test.com',
        }
    )

    try:
        result = utils_send_custom_email(
            f'{TEST_MARKER} موضوع اختبار',
            f'{TEST_MARKER} رسالة اختبار',
            [f'{TEST_MARKER}@test.com']
        )

        outbox_count = len(mail.outbox)
        print(f"  نتيجة الاستدعاء: {result}")
        print(f"  mail.outbox: {outbox_count} بريد")

        # النسخة في utils.py تُرجع tuple (bool, str)
        check_4 = (
            outbox_count >= 1 and
            isinstance(result, tuple) and
            result[0] == True
        )
    except Exception as e:
        print(f"  ⚠️ استثناء: {e}")
        check_4 = False

    # استعادة EmailSetting
    if original_es_data:
        EmailSetting.objects.filter(pk=1).update(**original_es_data)

    sign = '✓' if check_4 else '✗'
    print(f"  {sign} {'PASS' if check_4 else 'FAIL'} | 4. utils.py تعمل (tuple، outbox ليس فارغ)")

    # ====== [5] فحص 5: النمط القديم (auth_user/auth_password) محذوف ======
    print_step(5, "فحص 5: ★ النمط القديم (auth_user/auth_password) محذوف من views.py")

    old_pattern_found = False
    old_pattern_line = ''
    for line in views_content.split('\n'):
        stripped = line.strip()
        if ('auth_user' in stripped or 'auth_password' in stripped) and not stripped.startswith('#'):
            old_pattern_found = True
            old_pattern_line = stripped
            break

    check_5 = not old_pattern_found
    if old_pattern_found:
        print(f"  ✗ نمط قديم موجود: {old_pattern_line}")
    else:
        print(f"  ✓ النمط القديم (auth_user/auth_password) غير موجود في views.py")

    sign = '✓' if check_5 else '✗'
    print(f"  {sign} {'PASS' if check_5 else 'FAIL'} | 5. النمط القديم محذوف من views.py")

    # ====== [6] استعادة الإعدادات ======
    if _ORIGINAL_EMAIL_BACKEND is not None:
        settings.EMAIL_BACKEND = _ORIGINAL_EMAIL_BACKEND
    mail.outbox = []

    # ====== [7] العداد النهائي ======
    print_step(7, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3, check_4, check_5]
    descriptions = [
        'send_custom_email موجودة في utils.py',
        'send_custom_email مُستوردة في views.py',
        '★ send_custom_email محذوفة من views.py (لا تعريف محلي)',
        'send_custom_email من utils.py تعمل عبر locmem (تُرجع tuple)',
        '★ النمط القديم (auth_user/auth_password) محذوف من views.py',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/5")
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 2.3 من تقرير التدقيق")
print(f"  الموضوع: حذف send_custom_email المكررة في views.py")
print(f"  المنهجية: static check + استدعاء مباشر + 5 فحوصات × تشغيلان")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    p, checks = run_test(i)
    all_results.append((p, checks))

# استعادة EMAIL_BACKEND
if _ORIGINAL_EMAIL_BACKEND is not None:
    settings.EMAIL_BACKEND = _ORIGINAL_EMAIL_BACKEND

print_header("الخلاصة النهائية")

run1_p, run1_checks = all_results[0]
run2_p, run2_checks = all_results[1]
same_run = (run1_checks == run2_checks)

print(f"  التشغيل 1: {run1_p}/5")
print(f"  التشغيل 2: {run2_p}/5")
print(f"  متطابقة: {same_run}")
print(f"  النتيجة النهائية: {run1_p}/5")

check_3_passes = run1_checks[2]
check_5_passes = run1_checks[4]

if run1_p == 5 and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 2.3 أُغلق بدليل رقمي:")
    print(f"    - send_custom_email المكررة محذوفة من views.py")
    print(f"    - النمط القديم (auth_user/auth_password) محذوف")
    print(f"    - send_custom_email من utils.py تعمل بشكل صحيح")
    print(f"    - الكود يتبع مبدأ DRY (لا تكرار)")
elif not check_3_passes and same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✗ الفحص 3 فشل: send_custom_email ما زالت معرّفة محلياً في views.py")
    print(f"  الإجراء التالي: حذف التعريف المحلي من views.py")
elif not check_5_passes and same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✗ الفحص 5 فشل: النمط القديم (auth_user/auth_password) ما زال موجوداً")
    print(f"  الإجراء التالي: حذف التعريف المحلي من views.py")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
    print(f"  راجع الفحوصات الفاشلة أعلاه")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")