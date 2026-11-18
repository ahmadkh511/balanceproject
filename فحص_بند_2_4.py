"""
================================================================
فحص إثبات + إغلاق — بند 2.4 من تقرير التدقيق
================================================================
الموضوع: حذف الدوال والاستيرادات المكررة في views.py

السكربت يفحص invoice/views.py ويُخرج تقريراً تفصيلياً بـ:
  1) الاستيرادات المكررة (نفس الاسم من نفس المكتبة مرتين)
  2) الاستيرادات المُغطّاة (نفس الاسم من مكتبتين، الأخيرة تُغطي الأولى)
  3) الدوال المُعرّفة مرتين في نفس الملف
  4) الاستيرادات غير المستخدمة (تحليل أساسي)

المنهجية:
  - تحليل ساكن للكود (static analysis) — لا HTTP
  - يقرأ views.py فقط
  - يُخرج تقريراً للمستخدم
  - لا يحذف شيئاً تلقائياً
  - 4 فحوصات رئيسية × تشغيلان = 8 قياسات

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_2_4.py', encoding='utf-8').read())"
================================================================
"""

import os
import re
from collections import defaultdict
from django.conf import settings

TEST_MARKER = 'فحص_2_4'
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


def parse_imports(content):
    """تحليل كل أسطر الاستيراد في الملف"""
    imports = []  # list of dicts: {line_number, line_text, module, names_imported, is_from_import}
    
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        line_num = i + 1
        
        # تخطي التعليقات والأسطر الفارغة
        if not line or line.startswith('#'):
            i += 1
            continue
        
        # استيراد بسيط: import xxx
        m = re.match(r'^import\s+([\w.]+)(\s+as\s+(\w+))?(#.*)?$', line)
        if m:
            module = m.group(1)
            alias = m.group(3) if m.group(3) else module.split('.')[-1]
            imports.append({
                'line_number': line_num,
                'line_text': line,
                'module': module,
                'names': [alias],
                'is_from_import': False,
            })
            i += 1
            continue
        
        # استيراد من: from xxx import yyy
        m = re.match(r'^from\s+([\w.]+)\s+import\s+(.+?)(#.*)?$', line)
        if m:
            module = m.group(1)
            names_part = m.group(2).strip()
            
            # معالجة الاستيراد متعدد الأسطر
            if names_part.startswith('('):
                # استيراد متعدد الأسطر داخل قوسين
                full_names = names_part
                while not full_names.rstrip().endswith(')') and i + 1 < len(lines):
                    i += 1
                    full_names += ' ' + lines[i].strip()
                # استخراج الأسماء بين القوسين
                inner = re.search(r'\(([^)]*)\)', full_names)
                if inner:
                    names_str = inner.group(1)
                else:
                    names_str = names_part[1:]  # fallback
            else:
                names_str = names_part
            
            # تقطيع الأسماء
            names = []
            for n in names_str.replace(',', ' ').split():
                n = n.strip()
                if n and not n.startswith('#'):
                    # معالجة alias: xxx as yyy
                    if ' as ' in n:
                        parts = n.split(' as ')
                        names.append(parts[1].strip())
                    else:
                        names.append(n)
            
            imports.append({
                'line_number': line_num,
                'line_text': f"from {module} import ... ({len(names)} names)",
                'module': module,
                'names': names,
                'is_from_import': True,
            })
            i += 1
            continue
        
        i += 1
    
    return imports


def parse_function_defs(content):
    """تحليل كل تعريفات الدوال في الملف"""
    funcs = []  # list of dicts: {line_number, name, args}
    
    lines = content.split('\n')
    for i, line in enumerate(lines):
        # نمط: def function_name(args):
        m = re.match(r'^def\s+(\w+)\s*\(([^)]*)\)\s*:', line)
        if m:
            funcs.append({
                'line_number': i + 1,
                'name': m.group(1),
                'args': m.group(2),
            })
    
    return funcs


def find_duplicate_imports(imports):
    """إيجاد الاستيرادات المكررة (نفس الاسم من نفس المكتبة مرتين)"""
    seen = {}  # name -> list of {line, module}
    duplicates = []
    
    for imp in imports:
        for name in imp['names']:
            key = (imp['module'], name)
            if key in seen:
                # مكرر فعلاً
                duplicates.append({
                    'name': name,
                    'module': imp['module'],
                    'first_line': seen[key],
                    'duplicate_line': imp['line_number'],
                })
            else:
                seen[key] = imp['line_number']
    
    return duplicates


def find_shadowed_imports(imports):
    """إيجاد الاستيرادات المُغطّاة (نفس الاسم من مكتبتين)"""
    seen_names = {}  # name -> list of (module, line)
    shadowed = []
    
    for imp in imports:
        for name in imp['names']:
            if name in seen_names:
                # الاسم موجود من قبل من مكتبة أخرى
                for prev_module, prev_line in seen_names[name]:
                    if prev_module != imp['module']:
                        shadowed.append({
                            'name': name,
                            'first_module': prev_module,
                            'first_line': prev_line,
                            'second_module': imp['module'],
                            'second_line': imp['line_number'],
                        })
                seen_names[name].append((imp['module'], imp['line_number']))
            else:
                seen_names[name] = [(imp['module'], imp['line_number'])]
    
    return shadowed


def find_duplicate_functions(funcs):
    """إيجاد الدوال المُعرّفة مرتين"""
    seen = {}  # name -> list of line_numbers
    duplicates = []
    
    for f in funcs:
        if f['name'] in seen:
            seen[f['name']].append(f['line_number'])
        else:
            seen[f['name']] = [f['line_number']]
    
    for name, lines in seen.items():
        if len(lines) > 1:
            duplicates.append({
                'name': name,
                'lines': lines,
            })
    
    return duplicates


def find_unused_imports(content, imports):
    """إيجاد الاستيرادات غير المستخدمة (تحليل أساسي)"""
    # إزالة أسطر الاستيراد من المحتوى لفحص الاستخدام
    lines = content.split('\n')
    non_import_lines = []
    skip_multiline = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if skip_multiline:
            if ')' in stripped:
                skip_multiline = False
            continue
        if stripped.startswith('import ') or stripped.startswith('from '):
            if stripped.startswith('from ') and '(' in stripped and ')' not in stripped:
                skip_multiline = True
            continue
        non_import_lines.append(stripped)
    
    code_text = '\n'.join(non_import_lines)
    
    unused = []
    for imp in imports:
        for name in imp['names']:
            # فحص بسيط: هل الاسم يظهر في الكود خارج الاستيرادات؟
            # نتجاهل: الموديلات (لأنها قد تُستخدم في type hints مثلاً)
            pattern = r'\b' + re.escape(name) + r'\b'
            if not re.search(pattern, code_text):
                # استثناء: الاستيرادات الكاملة للموديلات (import xxx)
                if not imp['is_from_import'] and '.' in imp['module']:
                    # مثلاً import django.conf.settings — settings يُستخدم عادة
                    # تحقق فقط من الجزء الأخير
                    last_name = imp['module'].split('.')[-1]
                    if re.search(r'\b' + re.escape(last_name) + r'\b', code_text):
                        continue
                unused.append({
                    'name': name,
                    'module': imp['module'],
                    'line': imp['line_number'],
                })
    
    return unused


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    
    content = read_views_py()
    if not content:
        print("  ✗ تعذّر قراءة views.py")
        return None
    
    print(f"  حجم الملف: {len(content)} حرفاً، {len(content.split(chr(10)))} سطراً")
    
    # ====== [1] تحليل الاستيرادات ======
    print_step(1, "تحليل الاستيرادات")
    
    imports = parse_imports(content)
    total_imported_names = sum(len(imp['names']) for imp in imports)
    print(f"  عدد أسطر الاستيراد: {len(imports)}")
    print(f"  إجمالي الأسماء المُستوردة: {total_imported_names}")
    
    # ====== [2] فحص 1: الاستيرادات المكررة ======
    print_step(2, "فحص 1: الاستيرادات المكررة (نفس الاسم من نفس المكتبة)")
    
    duplicates = find_duplicate_imports(imports)
    if duplicates:
        print(f"  ✗ وُجدت {len(duplicates)} استيرادات مكررة:")
        for d in duplicates:
            print(f"    - {d['name']} from {d['module']}")
            print(f"      أول استيراد: سطر {d['first_line']}")
            print(f"      الاستيراد المكرر: سطر {d['duplicate_line']}")
    else:
        print(f"  ✓ لا توجد استيرادات مكررة")
    
    check_1 = (len(duplicates) == 0)
    
    # ====== [3] فحص 2: الاستيرادات المُغطّاة ======
    print_step(3, "فحص 2: الاستيرادات المُغطّاة (نفس الاسم من مكتبتين)")
    
    shadowed = find_shadowed_imports(imports)
    if shadowed:
        print(f"  ⚠️ وُجدت {len(shadowed)} استيرادات مُغطّاة (الاسم يُستورد من مكتبتين):")
        for s in shadowed:
            print(f"    - {s['name']}")
            print(f"      من '{s['first_module']}' (سطر {s['first_line']})")
            print(f"      ثم من '{s['second_module']}' (سطر {s['second_line']}) → الثاني يُغطي الأول")
    else:
        print(f"  ✓ لا توجد استيرادات مُغطّاة")
    
    check_2 = (len(shadowed) == 0)
    
    # ====== [4] فحص 3: الدوال المُعرّفة مرتين ======
    print_step(4, "فحص 3: ★ الدوال المُعرّفة مرتين في views.py")
    
    funcs = parse_function_defs(content)
    print(f"  إجمالي الدوال المُعرّفة: {len(funcs)}")
    
    duplicate_funcs = find_duplicate_functions(funcs)
    if duplicate_funcs:
        print(f"  ✗ وُجدت {len(duplicate_funcs)} دوال مُعرّفة مرتين:")
        for df in duplicate_funcs:
            print(f"    - def {df['name']}(): معرّفة في الأسطر: {df['lines']}")
    else:
        print(f"  ✓ لا توجد دوال مُعرّفة مرتين")
    
    check_3 = (len(duplicate_funcs) == 0)
    
    # ====== [5] فحص 4: الاستيرادات غير المستخدمة ======
    print_step(5, "فحص 4: الاستيرادات غير المستخدمة (تحليل أساسي)")
    
    unused = find_unused_imports(content, imports)
    if unused:
        print(f"  ⚠️ وُجدت {len(unused)} استيرادات غير مستخدمة على الأرجج:")
        for u in unused:
            print(f"    - {u['name']} from {u['module']} (سطر {u['line']})")
    else:
        print(f"  ✓ لا توجد استيرادات غير مستخدمة")
    
    check_4 = (len(unused) == 0)
    
    # ====== [6] العداد النهائي ======
    print_step(6, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3, check_4]
    descriptions = [
        'لا استيرادات مكررة (نفس الاسم من نفس المكتبة)',
        'لا استيرادات مُغطّاة (نفس الاسم من مكتبتين)',
        '★ لا دوال مُعرّفة مرتين',
        'لا استيرادات غير مستخدمة',
    ]
    passed = sum(checks)
    for desc, ok in zip(descriptions, checks):
        sign = '✓' if ok else '✗'
        print(f"  {sign} {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/4")
    
    return {
        'passed': passed,
        'total': 4,
        'checks': checks,
        'duplicates': duplicates,
        'shadowed': shadowed,
        'duplicate_funcs': duplicate_funcs,
        'unused': unused,
    }


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 2.4 من تقرير التدقيق")
print(f"  الموضوع: حذف الدوال والاستيرادات المكررة في views.py")
print(f"  المنهجية: static analysis — لا HTTP، لا حذف تلقائي")
print(f"  الفحوصات: استيرادات مكررة + مُغطّاة + دوال مكررة + غير مستخدمة")
print(f"  الملف المُختبر: {VIEWS_PY_PATH}")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    res = run_test(i)
    if res:
        all_results.append(res)

print_header("الخلاصة النهائية")

if len(all_results) == 2:
    run1, run2 = all_results
    same_run = (run1['checks'] == run2['checks'])
    same_duplicates = (len(run1['duplicates']) == len(run2['duplicates']))
    same_funcs = (len(run1['duplicate_funcs']) == len(run2['duplicate_funcs']))
    
    print(f"  التشغيل 1: {run1['passed']}/{run1['total']}")
    print(f"  التشغيل 2: {run2['passed']}/{run2['total']}")
    print(f"  متطابقة: {same_run}")
    print(f"  النتيجة النهائية: {run1['passed']}/{run1['total']}")
    
    print(f"\n  الإحصائيات:")
    print(f"    استيرادات مكررة: {len(run1['duplicates'])}")
    print(f"    استيرادات مُغطّاة: {len(run1['shadowed'])}")
    print(f"    دوال مُعرّفة مرتين: {len(run1['duplicate_funcs'])}")
    print(f"    استيرادات غير مستخدمة: {len(run1['unused'])}")
    
    if run1['passed'] == run1['total'] and same_run:
        print(f"\n  ✅ PASS — لا توجد تكرارات في views.py")
        print(f"  بند 2.4 أُغلق: الكود نظيف من التكرارات")
    elif same_run:
        print(f"\n  ⚠️ توجد تكرارات في views.py (مثبتة بدليل رقمي)")
        print(f"  راجع التفاصيل أعلاه لتقرير ما يُحذف")
        print(f"  الإجراء التالي: حذف التكرارات يدوياً ثم إعادة التشغيل")
    else:
        print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة (راجع السجل)")
else:
    print(f"  ⚠️ فشل تشغيل الفحص")

print(f"\n{'=' * 70}")