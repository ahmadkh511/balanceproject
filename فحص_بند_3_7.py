"""
================================================================
فحص إثبات + إغلاق — بند 3.7 من تقرير التدقيق
================================================================
الموضوع: إضافة update_fields لكل product.save()

المشكلة:
  - استدعاء product.save() بدون update_fields يُحدّث كل أعمدة الجدول.
  - أداء منخفض + تضييع البيانات عند التزامن (Race Condition).
  - تحديث حقول كبيرة (صور، CKEditor) بلا داعٍ.

الإصلاح المقترح:
  - تمرير update_fields=['field1', 'field2'] لكل product.save() في models.py و views.py.

المنهجية:
  - فحص static للكود (regex) يبحث عن .save() بدون update_fields
  - 3 فحوصات × تشغيلان متطابقان = 6 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_3_7.py', encoding='utf-8').read())"
================================================================
"""

import os
import re
from django.conf import settings

TEST_MARKER = 'فحص_3_7'
MODELS_PY_PATH = os.path.join(settings.BASE_DIR, 'invoice', 'models.py')
VIEWS_PY_PATH = os.path.join(settings.BASE_DIR, 'invoice', 'views.py')


def read_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def find_unoptimized_saves(content, file_name):
    """البحث عن .save() بدون update_fields لمتغيرات تمثل المنتجات"""
    lines = content.split('\n')
    matches = []
    
    # نمط: أي كائن يحوي 'product' أو 'p' ينتهي بـ .save()
    # مثلاً: product.save() أو self.product.save() أو p.save()
    # نتجاهل super().save() و instance.save() و model.save()
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        # تخطي التعليقات
        if stripped.startswith('#'):
            continue
            
        # البحث عن .save()
        save_match = re.search(r'(\b\w+\.save\(\s*\))', stripped)
        if save_match:
            full_call = save_match.group(1)
            var_name = save_match.group(1).split('.save')[0]
            
            # هل المتغير يمثل منتج؟ (product, self.product, p, prod)
            is_product = False
            if 'product' in var_name.lower() or var_name == 'p' or var_name == 'prod':
                is_product = True
            
            # هل هي super().save() أو model.save()؟
            if 'super()' in var_name or 'instance' in var_name or 'model' in var_name:
                is_product = False
            
            if is_product:
                # التحقق هل يحوي update_fields في نفس السطر
                if 'update_fields' not in stripped:
                    matches.append({
                        'line_number': i + 1,
                        'line_text': stripped,
                        'file': file_name
                    })
                    
    return matches


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    
    # ====== [1] فحص models.py ======
    print_step(1, "فحص 1: ★ فحص models.py لـ product.save() بدون update_fields")
    
    models_content = read_file(MODELS_PY_PATH)
    models_matches = find_unoptimized_saves(models_content, 'models.py')
    
    if models_matches:
        print(f"  ✗ وُجدت {len(models_matches)} استدعاءات save() بدون update_fields في models.py:")
        for m in models_matches[:5]: # عرض أول 5
            print(f"    - سطر {m['line_number']}: {m['line_text']}")
    else:
        print(f"  ✓ لا توجد استدعاءات save() بدون update_fields في models.py")
        
    check_1 = (len(models_matches) == 0)
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | models.py نظيف")
    
    # ====== [2] فحص views.py ======
    print_step(2, "فحص 2: ★ فحص views.py لـ product.save() بدون update_fields")
    
    views_content = read_file(VIEWS_PY_PATH)
    views_matches = find_unoptimized_saves(views_content, 'views.py')
    
    if views_matches:
        print(f"  ✗ وُجدت {len(views_matches)} استدعاءات save() بدون update_fields في views.py:")
        for m in views_matches[:5]:
            print(f"    - سطر {m['line_number']}: {m['line_text']}")
    else:
        print(f"  ✓ لا توجد استدعاءات save() بدون update_fields في views.py")
        
    check_2 = (len(views_matches) == 0)
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | views.py نظيف")
    
    # ====== [3] فحص 3: إجمالي النتائج ======
    print_step(3, "فحص 3: إجمالي استدعاءات save() غير المُحسّنة في كامل المشروع")
    
    total_matches = len(models_matches) + len(views_matches)
    check_3 = (total_matches == 0)
    
    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | إجمالي الاستدعاءات غير المُحسّنة = {total_matches}")
    
    # ====== [4] العداد النهائي ======
    print_step(4, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3]
    descriptions = [
        'models.py خالٍ من product.save() بدون update_fields',
        'views.py خالٍ من product.save() بدون update_fields',
        'إجمالي الاستدعاءات غير المُحسّنة = 0',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/3")
    
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 3.7 من تقرير التدقيق")
print(f"  الموضوع: إضافة update_fields لكل product.save()")
print(f"  المنهجية: فحص static للكود (models.py, views.py) + 3 فحوصات × تشغيلان")
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
    print(f"  بند 3.7 أُغلق بدليل رقمي:")
    print(f"    - جميع استدعاءات product.save() تستخدم update_fields")
elif same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")