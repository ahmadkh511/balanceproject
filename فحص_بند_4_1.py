"""
================================================================
فحص إثبات + إغلاق — بند 4.1 من تقرير التدقيق
================================================================
الموضوع: حذف المسارات المكررة في urls.py

المشكلة:
  - في invoice/urls.py، توجد مسارات مكررة (نفس نص الرابط).
  - Django يطابق المسارات من الأعلى للأسفل، فالمسار المكرر الثاني لا يُستدعى أبداً.
  - هذا يُسبب لبساً للمطور وينتهك مبدأ DRY.

الإصلاح المقترح:
  - حذف المسارات المكررة والاحتفاظ بنسخة واحدة لكل مسار.

المنهجية:
  - فحص static للكود (AST) لاستخراج مسارات `path()`
  - 3 فحوصات × تشغيلان متطابقان = 6 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_4_1.py', encoding='utf-8').read())"
================================================================
"""

import os
import ast
from collections import Counter
from django.conf import settings

TEST_MARKER = 'فحص_4_1'
URLS_PY_PATH = os.path.join(settings.BASE_DIR, 'invoice', 'urls.py')


def read_urls_py():
    with open(URLS_PY_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def get_path_patterns(filepath):
    """استخراج جميع مسارات path() من ملف urls.py باستخدام AST"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    tree = ast.parse(content)
    patterns = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'path':
                if node.args and isinstance(node.args[0], ast.Constant):
                    patterns.append(node.args[0].value)
    return patterns


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    
    # ====== [1] فحص 1: استخراج المسارات ======
    print_step(1, "تحليل مسارات urls.py")
    
    try:
        patterns = get_path_patterns(URLS_PY_PATH)
        print(f"  عدد المسارات الإجمالي: {len(patterns)}")
    except Exception as e:
        print(f"  ✗ خطأ في تحليل الملف: {e}")
        return 0, [False, False, False]
    
    # ====== [2] فحص 2: البحث عن مسارات مكررة ======
    print_step(2, "فحص 2: ★ البحث عن مسارات مكررة (نفس نص الرابط)")
    
    pattern_counts = Counter(patterns)
    duplicates = {k: v for k, v in pattern_counts.items() if v > 1}
    
    if duplicates:
        print(f"  ✗ وُجدت {len(duplicates)} مسارات مكررة:")
        for p, count in duplicates.items():
            print(f"    - '{p}' مكرر {count} مرات")
        check_2 = False
    else:
        print(f"  ✓ لا توجد مسارات مكررة في urls.py")
        check_2 = True
    
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | urls.py خالٍ من المسارات المكررة")
    
    # ====== [3] فحص 3: التحقق من عدم وجود dead code ======
    print_step(3, "فحص 3: إجمالي التكرارات = 0 (لا يوجد dead code)")
    
    total_dups = sum(v - 1 for v in pattern_counts.values() if v > 1)
    check_3 = (total_dups == 0)
    
    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | إجمالي التكرارات = {total_dups}")
    
    # ====== [4] العداد النهائي ======
    print_step(4, "نتيجة فحوصات التشغيل")
    checks = [check_2, check_3, True] # الفحص 1 دائماً ناجح (تحليل)
    descriptions = [
        '★ urls.py خالٍ من المسارات المكررة',
        'إجمالي التكرارات = 0 (لا dead code)',
        'تحليل AST ناجح',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/3")
    
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 4.1 من تقرير التدقيق")
print(f"  الموضوع: حذف المسارات المكررة في urls.py")
print(f"  المنهجية: فحص static للكود (AST) + 3 فحوصات × تشغيلان")
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
    print(f"  بند 4.1 أُغلق بدليل رقمي:")
    print(f"    - urls.py خالٍ من المسارات المكررة")
elif same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")