"""
================================================================
فحص إثبات + إغلاق — بند 4.2 من تقرير التدقيق
================================================================
الموضوع: حذف CashTransactionForm المكرر في forms.py

المشكلة:
  - في invoice/forms.py، تم تعريف CashTransactionForm مرتين.
  - التعريف الثاني يفتقد دالة clean() المهمة، و Python تأخذ الأخير.
  - هذا يعطل التحقق من المدخلات (مثل منع إدخال مبلغين معاً).

الإصلاح المقترح:
  - حذف التعريف المكرر والاحتفاظ بالذي يحوي دالة clean().

المنهجية:
  - فحص static للكود (AST) لاستخراج تعريفات الكلاسات
  - 3 فحوصات × تشغيلان متطابقان = 6 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_4_2.py', encoding='utf-8').read())"
================================================================
"""

import os
import ast
from django.conf import settings

TEST_MARKER = 'فحص_4_2'
FORMS_PY_PATH = os.path.join(settings.BASE_DIR, 'invoice', 'forms.py')


def read_forms_py():
    with open(FORMS_PY_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def get_class_info(filepath, class_name):
    """استخراج معلومات كلاس معين من ملف باستخدام AST"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    tree = ast.parse(content)
    definitions = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            has_clean = False
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == 'clean':
                    has_clean = True
            
            definitions.append({
                'line': node.lineno,
                'has_clean': has_clean
            })
    return definitions


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    
    # ====== [1] فحص 1: تكرار CashTransactionForm ======
    print_step(1, "فحص 1: ★ تكرار CashTransactionForm في forms.py")
    
    try:
        definitions = get_class_info(FORMS_PY_PATH, 'CashTransactionForm')
        count = len(definitions)
        
        if count > 1:
            print(f"  ✗ التكرار موجود: تم تعريف CashTransactionForm {count} مرات")
            for d in definitions:
                print(f"    - سطر {d['line']} (يحوي clean: {d['has_clean']})")
            check_1 = False
        elif count == 1:
            print(f"  ✓ لا يوجد تكرار: تم تعريف CashTransactionForm {count} مرة")
            check_1 = True
        else:
            print(f"  ⚠️ تعذّر العثور على CashTransactionForm")
            check_1 = False
            
    except Exception as e:
        print(f"  ✗ خطأ في تحليل الملف: {e}")
        return 0, [False, False, False]
    
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | CashTransactionForm معرّفة مرة واحدة")
    
    # ====== [2] فحص 2: وجود دالة clean() ======
    print_step(2, "فحص 2: ★ وجود دالة clean() في CashTransactionForm")
    
    has_clean = any(d['has_clean'] for d in definitions)
    check_2 = has_clean
    
    if has_clean:
        print(f"  ✓ دالة clean() موجودة في التعريف المتبقي")
    else:
        print(f"  ✗ دالة clean() مفقودة! التحقق من المدخلات لا يعمل.")
        
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | دالة clean() موجودة")
    
    # ====== [3] فحص 3: إجمالي التكرارات ======
    print_step(3, "فحص 3: إجمالي التكرارات = 0")
    
    total_dups = count - 1 if count > 1 else 0
    check_3 = (total_dups == 0)
    
    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | إجمالي التكرارات = {total_dups}")
    
    # ====== [4] العداد النهائي ======
    print_step(4, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3]
    descriptions = [
        '★ CashTransactionForm معرّفة مرة واحدة فقط',
        '★ دالة clean() موجودة للتحقق من المدخلات',
        'إجمالي التكرارات = 0',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/3")
    
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 4.2 من تقرير التدقيق")
print(f"  الموضوع: حذف CashTransactionForm المكرر في forms.py")
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
    print(f"  بند 4.2 أُغلق بدليل رقمي:")
    print(f"    - CashTransactionForm معرّفة مرة واحدة فقط وتحوي clean()")
elif same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")