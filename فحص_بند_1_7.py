"""
================================================================
فحص إثبات + إغلاق — بند 1.7 من تقرير التدقيق
================================================================
الموضوع: حذف تكرار default_sale_price و best_price في Product

المشكلة:
  - في invoice/models.py، كلاس Product يحوي تعريفين لـ default_sale_price.
  - كذلك يحوي تعريفين لـ best_price و best_available_price.
  - هذا التكرار ينتهك مبدأ DRY ويسبب تضليل المطورين.

الإصلاح المقترح:
  - حذف التعريفات المكررة والاحتفاظ بواحد فقط لكل خاصية.

المنهجية:
  - فحص static للكود (models.py) باستخدام AST (Abstract Syntax Tree)
  - 3 فحوصات × تشغيلان متطابقان = 6 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_1_7.py', encoding='utf-8').read())"
================================================================
"""

import os
import ast
from django.conf import settings

TEST_MARKER = 'فحص_1_7'
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


def count_property_defs(class_node, prop_name):
    """عدّ كم مرة تم تعريف خاصية معينة داخل كلاس"""
    count = 0
    for node in ast.walk(class_node):
        if isinstance(node, ast.FunctionDef):
            # هل هي property؟
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == 'property':
                    if node.name == prop_name:
                        count += 1
    return count


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    
    content = read_models_py()
    
    # تحليل الكود باستخدام AST
    tree = ast.parse(content)
    
    # البحث عن كلاس Product
    product_class = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'Product':
            product_class = node
            break
    
    if not product_class:
        print("  ✗ تعذّر العثور على كلاس Product في models.py")
        return 0, [False, False, False]
    
    # ====== [1] فحص 1: تكرار default_sale_price ======
    print_step(1, "فحص 1: ★ عدم تكرار default_sale_price في Product")
    
    count_default = count_property_defs(product_class, 'default_sale_price')
    check_1 = (count_default == 1)
    
    if count_default > 1:
        print(f"  ✗ التكرار موجود: تم تعريف default_sale_price {count_default} مرات (يجب 1)")
    else:
        print(f"  ✓ لا يوجد تكرار: تم تعريف default_sale_price {count_default} مرة")
    
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | default_sale_price معرّفة مرة واحدة")
    
    # ====== [2] فحص 2: تكرار best_price / best_available_price ======
    print_step(2, "فحص 2: ★ عدم تكرار best_price / best_available_price في Product")
    
    count_best_price = count_property_defs(product_class, 'best_price')
    count_best_available = count_property_defs(product_class, 'best_available_price')
    
    # نسمح بوجود best_price أو best_available_price أو كليهما، لكن ليس تكراراً لأحدهما
    check_2 = (count_best_price <= 1 and count_best_available <= 1)
    
    if count_best_price > 1:
        print(f"  ✗ التكرار موجود: تم تعريف best_price {count_best_price} مرات")
    elif count_best_available > 1:
        print(f"  ✗ التكرار موجود: تم تعريف best_available_price {count_best_available} مرات")
    else:
        print(f"  ✓ لا يوجد تكرار: best_price={count_best_price}, best_available_price={count_best_available}")
    
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | خصائص الأسعار بدون تكرار")
    
    # ====== [3] فحص 3: إجمالي التكرارات ======
    print_step(3, "فحص 3: إجمالي التكرارات في كلاس Product = 0")
    
    total_dups = (count_default - 1 if count_default > 1 else 0) + \
                 (count_best_price - 1 if count_best_price > 1 else 0) + \
                 (count_best_available - 1 if count_best_available > 1 else 0)
    
    check_3 = (total_dups == 0)
    
    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | إجمالي التكرارات = {total_dups}")
    
    # ====== [4] العداد النهائي ======
    print_step(4, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3]
    descriptions = [
        '★ default_sale_price معرّفة مرة واحدة فقط',
        '★ best_price / best_available_price بدون تكرار',
        'إجمالي التكرارات في كلاس Product = 0',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/3")
    
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 1.7 من تقرير التدقيق")
print(f"  الموضوع: حذف تكرار default_sale_price و best_price في Product")
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
    print(f"  بند 1.7 أُغلق بدليل رقمي:")
    print(f"    - default_sale_price معرّفة مرة واحدة فقط")
    print(f"    - best_price / best_available_price بدون تكرار")
elif same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")