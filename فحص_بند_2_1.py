"""
================================================================
فحص إثبات + إغلاق — بند 2.1 من تقرير التدقيق
================================================================
الموضوع: ثغرة verify_pricing_password — تقبل أي كلمة مرور إن لم توجد كلمة معرّفة

السيناريوهات:
  أ) لا توجد كلمة مرور معرّفة (PricingSetting.pricing_password فارغ)
     - "أي شيء" → يجب أن يُرفض (مع الإصلاح)
     - قبل الإصلاح: يُقبل (الثغرة)
     - بعد الإصلاح: يُرفض (Fail-Secure)

  ب) توجد كلمة مرور معرّفة (Test@12345)
     - "Test@12345" → يجب أن يُقبل
     - "خاطئة" → يجب أن يُرفض
     - "" (فارغة) → يجب أن يُرفض
     - None → يجب أن يُرفض

المنهجية:
  - استدعاء مباشر لـ verify_pricing_password و is_pricing_password_set
  - إنشاء PricingSetting اختباري بحالة محكومة (مع/بدون كلمة مرور)
  - استعادة الحالة الأصلية بعد كل سيناريو
  - 8 فحوصات إجمالاً
  - يُشغَّل مرتين متتاليتين ويعطي النتيجة نفسها

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_2_1.py', encoding='utf-8').read())"
================================================================
"""

from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model

if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import PricingSetting
from invoice.utils import verify_pricing_password, is_pricing_password_set
from django.contrib.auth.hashers import make_password


TEST_MARKER = 'فحص_2_1'
TEST_PASSWORD_PLAIN = 'فحص_2_1_Test@12345'  # كلمة مرور اختبارية واضحة
TEST_PASSWORD_HASHED = make_password(TEST_PASSWORD_PLAIN)


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def backup_pricing_settings():
    """حفظ الحالة الأصلية لـ PricingSetting"""
    s = PricingSetting.get_settings()
    return {
        'pricing_password': s.pricing_password,
        'conversion_factor': s.conversion_factor,
        'profit_margin': s.profit_margin,
    }


def restore_pricing_settings(backup):
    """استعادة الحالة الأصلية"""
    s = PricingSetting.get_settings()
    s.pricing_password = backup['pricing_password']
    s.conversion_factor = backup['conversion_factor']
    s.profit_margin = backup['profit_margin']
    s.save()


def set_no_password():
    """ضبط PricingSetting بدون كلمة مرور"""
    s = PricingSetting.get_settings()
    s.pricing_password = ''
    s.save()


def set_test_password():
    """ضبط PricingSetting بكلمة مرور اختبارية"""
    s = PricingSetting.get_settings()
    s.pricing_password = TEST_PASSWORD_HASHED
    s.save()


def run_scenario_a():
    """سيناريو أ: لا توجد كلمة مرور معرّفة"""
    print_header("السيناريو أ: لا توجد كلمة مرور معرّفة")
    print("  التوقع مع الإصلاح: كل الإدخالات تُرفض (Fail-Secure)")
    print("  التوقع قبل الإصلاح: أي إدخال غير فارغ يُقبل (الثغرة)")

    set_no_password()

    print_step(1, "حالة النظام")
    print(f"  is_pricing_password_set() = {is_pricing_password_set()} (متوقع: False)")

    checks = []

    print_step(2, "فحص 1: كلمة مرور صحيحة افتراضية ('admin')")
    # في الواقع لا توجد "كلمة صحيحة" لأنه لا توجد كلمة معرّفة
    # لكن المستخدم المهاجم قد يجرّب كلمات شائعة
    result = verify_pricing_password('admin')
    expected = False  # مع الإصلاح: يجب أن يُرفض
    ok = (result == expected)
    checks.append(('فحص 1: كلمة "admin" تُرفض عند غياب كلمة معرّفة', ok, result, expected))
    print(f"  verify_pricing_password('admin') = {result} (متوقع: {expected}) → {ok}")

    print_step(3, "فحص 2: كلمة مرور عشوائية ('anything')")
    result = verify_pricing_password('anything')
    expected = False
    ok = (result == expected)
    checks.append(('فحص 2: كلمة "anything" تُرفض عند غياب كلمة معرّفة', ok, result, expected))
    print(f"  verify_pricing_password('anything') = {result} (متوقع: {expected}) → {ok}")

    print_step(4, "فحص 3: كلمة مرور فارغة ('')")
    result = verify_pricing_password('')
    expected = False
    ok = (result == expected)
    checks.append(('فحص 3: كلمة فارغة تُرفض', ok, result, expected))
    print(f"  verify_pricing_password('') = {result} (متوقع: {expected}) → {ok}")

    print_step(5, "فحص 4: كلمة مرور None")
    result = verify_pricing_password(None)
    expected = False
    ok = (result == expected)
    checks.append(('فحص 4: None تُرفض', ok, result, expected))
    print(f"  verify_pricing_password(None) = {result} (متوقع: {expected}) → {ok}")

    return checks


def run_scenario_b():
    """سيناريو ب: توجد كلمة مرور معرّفة"""
    print_header("السيناريو ب: توجد كلمة مرور معرّفة")
    print(f"  كلمة المرور الاختبارية: '{TEST_PASSWORD_PLAIN}'")
    print("  التوقع: الكلمة الصحيحة تُقبل، الخاطئة والفارغة و None تُرفض")

    set_test_password()

    print_step(1, "حالة النظام")
    print(f"  is_pricing_password_set() = {is_pricing_password_set()} (متوقع: True)")

    checks = []

    print_step(2, "فحص 5: كلمة مرور صحيحة")
    result = verify_pricing_password(TEST_PASSWORD_PLAIN)
    expected = True
    ok = (result == expected)
    checks.append(('فحص 5: الكلمة الصحيحة تُقبل', ok, result, expected))
    print(f"  verify_pricing_password('{TEST_PASSWORD_PLAIN}') = {result} (متوقع: {expected}) → {ok}")

    print_step(3, "فحص 6: كلمة مرور خاطئة")
    result = verify_pricing_password('wrong_password')
    expected = False
    ok = (result == expected)
    checks.append(('فحص 6: كلمة خاطئة تُرفض', ok, result, expected))
    print(f"  verify_pricing_password('wrong_password') = {result} (متوقع: {expected}) → {ok}")

    print_step(4, "فحص 7: كلمة مرور فارغة")
    result = verify_pricing_password('')
    expected = False
    ok = (result == expected)
    checks.append(('فحص 7: كلمة فارغة تُرفض', ok, result, expected))
    print(f"  verify_pricing_password('') = {result} (متوقع: {expected}) → {ok}")

    print_step(5, "فحص 8: كلمة مرور None")
    result = verify_pricing_password(None)
    expected = False
    ok = (result == expected)
    checks.append(('فحص 8: None تُرفض', ok, result, expected))
    print(f"  verify_pricing_password(None) = {result} (متوقع: {expected}) → {ok}")

    return checks


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")

    backup = backup_pricing_settings()
    print(f"  الحالة الأصلية: pricing_password محفوظ = {bool(backup['pricing_password'])}")

    try:
        checks_a = run_scenario_a()
        checks_b = run_scenario_b()
    finally:
        # ★ استعادة الحالة الأصلية دائماً (حتى لو فشل الفحص)
        restore_pricing_settings(backup)
        restored = PricingSetting.get_settings()
        print(f"\n  ✓ تم استعادة كلمة المرور الأصلية: {bool(restored.pricing_password)}")

    all_checks = checks_a + checks_b

    print_step(6, "نتيجة فحوصات التشغيل")
    passed = 0
    for desc, ok, result, expected in all_checks:
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
        if ok:
            passed += 1
    total = len(all_checks)
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/{total}")
    return passed, total, all_checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 2.1 من تقرير التدقيق")
print(f"  الموضوع: ثغرة verify_pricing_password")
print(f"  المنهجية: سيناريوهان (غياب/وجود كلمة مرور) × 4 فحوصات لكل = 8 فحوصات")
print(f"  الدوال المُختبرَة:")
print(f"    - invoice.utils.verify_pricing_password")
print(f"    - invoice.utils.is_pricing_password_set")
print(f"  العلامة: {TEST_MARKER}")

results = []
for i in [1, 2]:
    p, t, checks = run_test(i)
    results.append((p, t, checks))

print_header("الخلاصة النهائية")

run1_p, run1_t, run1_checks = results[0]
run2_p, run2_t, run2_checks = results[1]

same_run = all(run1_checks[j][1] == run2_checks[j][1] for j in range(len(run1_checks)))

print(f"  التشغيل 1: {run1_p}/{run1_t}")
print(f"  التشغيل 2: {run2_p}/{run2_t}")
print(f"  متطابقة: {same_run}")
print(f"  النتيجة النهائية: {run1_p}/{run1_t}")

if run1_p == run1_t and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 2.1 أُغلق بدليل رقمي:")
    print(f"    - لا توجد كلمة مرور معرّفة → كل المحاولات تُرفض (Fail-Secure)")
    print(f"    - توجد كلمة مرور → الكلمة الصحيحة تُقبل والخاطئة تُرفض")
    print(f"    - is_pricing_password_set يميّز بين الحالتين بوضوح")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
    print(f"  راجع الفحوصات الفاشلة:")
    for desc, ok, result, expected in run1_checks:
        if not ok:
            print(f"    ✗ {desc} (فعلي: {result}, متوقع: {expected})")
    print(f"\n  الاحتمالات:")
    print(f"    - إن فشل فحص 1 أو 2 فقط: الثغرة ما زالت موجودة (return True بدل False)")
    print(f"    - إن فشلت فحوصات السيناريو ب: كلمة المرور الاختبارية لم تُحفظ بشكل صحيح")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")