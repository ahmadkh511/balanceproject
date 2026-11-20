"""
================================================================
فحص إثبات + إغلاق — بند 3.8 من تقرير التدقيق
================================================================
الموضوع: إصلاح SSRF في purch_create و sale_create

المشكلة:
  - استخدام requests.get(image_url) يجلب صوراً من الإنترنت بناءً على مدخلات المستخدم.
  - هذا يُعرف بـ SSRF (Server-Side Request Forgery).
  - المهاجم يمكنه إرسال URL خبيث (مثل http://169.254.169.254/) لكشف بيانات داخلية.

الإصلاح المقترح:
  - استبدال requests.get بنسخ الصورة من default_storage (تخزين النظام المحلي).
  - هذا آمن 100% لأننا لا نجلب من الإنترنت، بل ننسخ ملفاً محلياً.

السيناريوهات:
  1) sale_create لا يحوي requests.get (مُصلح بالفعل)
  2) purch_create لا يحوي requests.get (يحتاج إصلاح)
  3) sale_create يستخدم default_storage (مُصلح بالفعل)
  4) purch_create يستخدم default_storage (يحتاج إصلاح)

المنهجية:
  - فحص static للكود (views.py)
  - 4 فحوصات × تشغيلان متطابقان = 8 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_3_8.py', encoding='utf-8').read())"
================================================================
"""

import os
from django.conf import settings

TEST_MARKER = 'فحص_3_8'
VIEWS_PY_PATH = os.path.join(settings.BASE_DIR, 'invoice', 'views.py')


def read_views_py():
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
    
    content = read_views_py()
    
    # ====== [1] فحص 1: sale_create خالٍ من requests.get ======
    print_step(1, "فحص 1: ★ sale_create خالٍ من requests.get (SSRF Fix)")
    
    # استخراج جسم دالة sale_create
    import re
    sale_match = re.search(r'def sale_create\(.*?\):(.*?)(?=\n@|\ndef |\Z)', content, re.DOTALL)
    if sale_match:
        sale_body = sale_match.group(1)
        has_requests_get = "requests.get(" in sale_body
        check_1 = not has_requests_get
        if check_1:
            print(f"  ✓ sale_create لا يستخدم requests.get")
        else:
            print(f"  ✗ sale_create يستخدم requests.get — ثغرة SSRF موجودة")
    else:
        print(f"  ✗ تعذّر العثور على دالة sale_create")
        check_1 = False
        
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | sale_create خالٍ من requests.get")
    
    # ====== [2] فحص 2: purch_create خالٍ من requests.get ======
    print_step(2, "فحص 2: ★ purch_create خالٍ من requests.get (SSRF Fix)")
    
    purch_match = re.search(r'def purch_create\(.*?\):(.*?)(?=\n@|\ndef |\Z)', content, re.DOTALL)
    if purch_match:
        purch_body = purch_match.group(1)
        has_requests_get = "requests.get(" in purch_body
        check_2 = not has_requests_get
        if check_2:
            print(f"  ✓ purch_create لا يستخدم requests.get")
        else:
            print(f"  ✗ purch_create يستخدم requests.get — ثغرة SSRF موجودة")
    else:
        print(f"  ✗ تعذّر العثور على دالة purch_create")
        check_2 = False
        
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | purch_create خالٍ من requests.get")
    
    # ====== [3] فحص 3: sale_create يستخدم default_storage ======
    print_step(3, "فحص 3: sale_create يستخدم default_storage (النسخ الآمن)")
    
    if sale_match:
        has_default_storage = "default_storage" in sale_body
        check_3 = has_default_storage
        if check_3:
            print(f"  ✓ sale_create يستخدم default_storage للنسخ المحلي الآمن")
        else:
            print(f"  ✗ sale_create لا يستخدم default_storage")
    else:
        check_3 = False
        
    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | sale_create يستخدم default_storage")
    
    # ====== [4] فحص 4: purch_create يستخدم default_storage ======
    print_step(4, "فحص 4: purch_create يستخدم default_storage (النسخ الآمن)")
    
    if purch_match:
        has_default_storage = "default_storage" in purch_body
        check_4 = has_default_storage
        if check_4:
            print(f"  ✓ purch_create يستخدم default_storage للنسخ المحلي الآمن")
        else:
            print(f"  ✗ purch_create لا يستخدم default_storage")
    else:
        check_4 = False
        
    sign = '✓' if check_4 else '✗'
    print(f"  {sign} {'PASS' if check_4 else 'FAIL'} | purch_create يستخدم default_storage")
    
    # ====== [5] العداد النهائي ======
    print_step(5, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3, check_4]
    descriptions = [
        'sale_create خالٍ من requests.get',
        '★ purch_create خالٍ من requests.get',
        'sale_create يستخدم default_storage',
        '★ purch_create يستخدم default_storage',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/4")
    
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 3.8 من تقرير التدقيق")
print(f"  الموضوع: إصلاح SSRF في purch_create و sale_create")
print(f"  المنهجية: فحص static للكود + 4 فحوصات × تشغيلان")
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

if run1_p == 4 and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 3.8 أُغلق بدليل رقمي:")
    print(f"    - sale_create و purch_create لا يستخدمان requests.get")
    print(f"    - النسخ التلقائي للصور يتم عبر default_storage (محلي وآمن)")
elif same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")