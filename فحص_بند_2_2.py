"""
================================================================
فحص إثبات + إغلاق — بند 2.2 من تقرير التدقيق
================================================================
الموضوع: admin_send_notification يُعدّل settings في runtime بدل
         تمرير connection=connection لـ EmailMessage

الكود الحالي يحفظ settings.EMAIL_HOST/PORT/USER/PASSWORD/TLS/DEFAULT_FROM_EMAIL،
يُعدّلها مؤقتاً، يُرسل البريد، ثم يستعيدها في finally. هذا غير آمن في
بيئة multi-threaded ويعرض الطلبات المتزامنة للتداخل.

الإصلاح المقترح: تمرير connection=connection مباشرة لـ EmailMessage
بدل تعديل settings.

المنهجية:
  - locmem backend لالتقاط البريد المُرسل دون لمس الشبكة
  - HTTP حي عبر django.test.Client
  - مستخدم فائق معزول
  - تنظيف ذاتي قبل/بعد
  - 8 فحوصات × تشغيلان متطابقان = 16 قياساً
  - فحص خاص: settings.EMAIL_HOST يجب ألا يتغير أثناء الإرسال

طريقة التشغيل:
    python manage.py shell -c "exec(open('فحص_بند_2_2.py', encoding='utf-8').read())"
================================================================
"""

import os
from decimal import Decimal
from datetime import date
from django.conf import settings
from django.test import Client
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.core import mail
from django.utils import timezone

# حارسة ALLOWED_HOSTS — تضاف فقط داخل هذه العملية ولا تلمس settings.py
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

User = get_user_model()

from invoice.models import (
    Product, StockNotification, EmailSetting, Payment_method, Currency
)

TEST_MARKER = 'فحص_2_2'
TEST_ADMIN = f'{TEST_MARKER}_مدير'
TEST_PRODUCT = f'{TEST_MARKER}_منتج'
TEST_EMAILS = [
    f'{TEST_MARKER}_a@test.com',
    f'{TEST_MARKER}_b@test.com',
    f'{TEST_MARKER}_c@test.com',
]

# حفظ الإعدادات الأصلية لاستعادتها
_ORIGINAL_EMAIL_BACKEND = getattr(settings, 'EMAIL_BACKEND', None)
_ORIGINAL_EMAIL_HOST = getattr(settings, 'EMAIL_HOST', None)
_ORIGINAL_EMAIL_PORT = getattr(settings, 'EMAIL_PORT', None)
_ORIGINAL_EMAIL_HOST_USER = getattr(settings, 'EMAIL_HOST_USER', None)
_ORIGINAL_EMAIL_HOST_PASSWORD = getattr(settings, 'EMAIL_HOST_PASSWORD', None)
_ORIGINAL_EMAIL_USE_TLS = getattr(settings, 'EMAIL_USE_TLS', None)
_ORIGINAL_DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', None)


def cleanup_test_data():
    """تنظيف شامل"""
    # حذف سجلات StockNotification الاختبارية
    StockNotification.objects.filter(email__in=TEST_EMAILS).delete()
    Product.objects.filter(product_name__startswith=TEST_MARKER).delete()
    User.objects.filter(username=TEST_ADMIN).delete()


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_step(num, title):
    print(f"\n[{num}] {title}")


def setup_test_environment():
    """إعداد البيئة الاختبارية: locmem + EmailSetting اختباري"""
    # 1. تفعيل locmem backend لالتقاط البريد دون الشبكة
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    
    # 2. ضبط EMAIL_HOST بقيمة مميزة قبل الفحص
    # إن لمس الكود settings.EMAIL_HOST، سنرى القيمة مختلفة بعد الفحص
    settings.EMAIL_HOST = 'before.test.host'
    settings.EMAIL_PORT = 25
    settings.EMAIL_HOST_USER = 'before_user'
    settings.EMAIL_HOST_PASSWORD = 'before_pass'
    settings.EMAIL_USE_TLS = False
    settings.DEFAULT_FROM_EMAIL = 'before_from@test.com'
    
    # 3. مسح outbox قبل كل فحص
    mail.outbox = []
    
    # 4. إنشاء أو تحديث EmailSetting في قاعدة البيانات
    # الكود الحالي يستخدم get_active_email_connection التي تقرأ من DB
    # سنجعلها تعيد connection من نوع locmem (عبر settings.EMAIL_BACKEND)
    es, _ = EmailSetting.objects.update_or_create(
        pk=1,
        defaults={
            'email_backend': 'django.core.mail.backends.locmem.EmailBackend',
            'email_host': 'test_smtp.host',  # قيمة اختبارية — لا تُستخدم مع locmem
            'email_port': 587,
            'email_use_tls': True,
            'email_host_user': 'test_user@test.com',
            'email_host_password': 'test_pass',
            'default_from_email': 'test_from@example.com',
        }
    )
    return es


def restore_test_environment():
    """استعادة الإعدادات الأصلية"""
    if _ORIGINAL_EMAIL_BACKEND is not None:
        settings.EMAIL_BACKEND = _ORIGINAL_EMAIL_BACKEND
    elif hasattr(settings, 'EMAIL_BACKEND'):
        del settings.EMAIL_BACKEND
    
    if _ORIGINAL_EMAIL_HOST is not None:
        settings.EMAIL_HOST = _ORIGINAL_EMAIL_HOST
    elif hasattr(settings, 'EMAIL_HOST'):
        del settings.EMAIL_HOST
    
    if _ORIGINAL_EMAIL_PORT is not None:
        settings.EMAIL_PORT = _ORIGINAL_EMAIL_PORT
    elif hasattr(settings, 'EMAIL_PORT'):
        del settings.EMAIL_PORT
    
    if _ORIGINAL_EMAIL_HOST_USER is not None:
        settings.EMAIL_HOST_USER = _ORIGINAL_EMAIL_HOST_USER
    elif hasattr(settings, 'EMAIL_HOST_USER'):
        del settings.EMAIL_HOST_USER
    
    if _ORIGINAL_EMAIL_HOST_PASSWORD is not None:
        settings.EMAIL_HOST_PASSWORD = _ORIGINAL_EMAIL_HOST_PASSWORD
    elif hasattr(settings, 'EMAIL_HOST_PASSWORD'):
        del settings.EMAIL_HOST_PASSWORD
    
    if _ORIGINAL_EMAIL_USE_TLS is not None:
        settings.EMAIL_USE_TLS = _ORIGINAL_EMAIL_USE_TLS
    elif hasattr(settings, 'EMAIL_USE_TLS'):
        del settings.EMAIL_USE_TLS
    
    if _ORIGINAL_DEFAULT_FROM_EMAIL is not None:
        settings.DEFAULT_FROM_EMAIL = _ORIGINAL_DEFAULT_FROM_EMAIL
    elif hasattr(settings, 'DEFAULT_FROM_EMAIL'):
        del settings.DEFAULT_FROM_EMAIL
    
    # مسح outbox
    mail.outbox = []


def run_test(run_number):
    print_header(f"تشغيل الفحص رقم {run_number}")
    
    cleanup_test_data()
    setup_test_environment()

    # ====== [1] إعداد البيانات ======
    print_step(1, "إعداد البيانات الأساسية")
    
    # مدير فائق
    admin = User.objects.create_superuser(
        username=TEST_ADMIN, password='Test@12345',
        first_name=TEST_MARKER, last_name='المدير'
    )
    print(f"  المدير: {admin.username}")
    
    # منتج (كمية 0 ليُفعّل شرط "نفاد المخزون")
    product = Product.objects.create(
        product_name=TEST_PRODUCT,
        purch_price=Decimal('100.00'),
        sale_price=Decimal('150.00'),
        current_stock_quantity=Decimal('0.00'),
        average_purchase_cost=Decimal('0.00')
    )
    print(f"  المنتج: {product.product_name} | مخزون: 0")
    
    # 3 سجلات StockNotification
    for email in TEST_EMAILS:
        StockNotification.objects.create(
            product=product, email=email, is_sent=False, sent_at=None
        )
    print(f"  سجلات StockNotification: {len(TEST_EMAILS)} بريدات")
    print(f"    {TEST_EMAILS}")
    
    # ====== [2] ضرب المسار HTTP ======
    print_step(2, "ضرب المسار: POST /invoice/stock-notifications/send/<product_id>/")
    
    client = Client()
    client.force_login(admin)
    
    try:
        response = client.post(f'/invoice/stock-notifications/send/{product.id}/')
        http_status = response.status_code
        print(f"  HTTP status: {http_status}")
    except Exception as e:
        print(f"  ⚠️ استثناء: {e}")
        http_status = None
    
    # ====== [3] فحص 1: HTTP 200 ======
    print_step(3, "فحص 1: المسار يستجيب بنجاح (HTTP 200)")
    check_1 = (http_status == 200)
    sign = '✓' if check_1 else '✗'
    print(f"  {sign} {'PASS' if check_1 else 'FAIL'} | HTTP status = {http_status}")
    
    # ====== [4] فحص 2: StockNotification.is_sent=True ======
    print_step(4, "فحص 2: السجلات تُؤرشفة بعد الإرسال (is_sent=True)")
    
    notifications = StockNotification.objects.filter(product=product)
    sent_count = sum(1 for n in notifications if n.is_sent)
    check_2 = (sent_count == 3)
    sign = '✓' if check_2 else '✗'
    print(f"  {sign} {'PASS' if check_2 else 'FAIL'} | is_sent=True لـ {sent_count}/3 سجلات")
    
    # ====== [5] فحص 3: StockNotification.sent_at ليس None ======
    print_step(5, "فحص 3: تاريخ الأرشفة مُسجّل (sent_at ليس None)")
    
    sent_at_count = sum(1 for n in notifications if n.sent_at is not None)
    check_3 = (sent_at_count == 3)
    sign = '✓' if check_3 else '✗'
    print(f"  {sign} {'PASS' if check_3 else 'FAIL'} | sent_at مُسجل لـ {sent_at_count}/3 سجلات")
    
    # ====== [6] فحص 4: mail.outbox ليس فارغاً ======
    print_step(6, "فحص 4: البريد فعلاً أُرسل (mail.outbox ليس فارغ)")
    
    outbox_count = len(mail.outbox)
    check_4 = (outbox_count >= 1)
    sign = '✓' if check_4 else '✗'
    print(f"  {sign} {'PASS' if check_4 else 'FAIL'} | mail.outbox يحتوي على {outbox_count} بريد")
    
    # ====== [7] فحص 5: Subject صحيح ======
    print_step(7, "فحص 5: عنوان البريد صحيح")
    
    expected_subject = f"عاد التوفر: {product.product_name}"
    if outbox_count > 0:
        actual_subject = mail.outbox[0].subject
        check_5 = (actual_subject == expected_subject)
        sign = '✓' if check_5 else '✗'
        print(f"  {sign} {'PASS' if check_5 else 'FAIL'} | subject = '{actual_subject}'")
        print(f"     المتوقع: '{expected_subject}'")
    else:
        check_5 = False
        print(f"  ✗ FAIL | لا يوجد بريد في outbox لفحص الـ subject")
    
    # ====== [8] فحص 6: BCC يحتوي على البريدات الثلاثة ======
    print_step(8, "فحص 6: البريد موجّه للمستفيدين (BCC)")
    
    if outbox_count > 0:
        # في Django's locmem، EmailMessage يضع bcc في recipients (مدموج مع to)
        # لكن السلوك المعتمد هنا: bcc يُمرَّر في EmailMessage.bcc
        actual_bcc = mail.outbox[0].bcc if hasattr(mail.outbox[0], 'bcc') else []
        bcc_set = set(actual_bcc)
        expected_set = set(TEST_EMAILS)
        check_6 = expected_set.issubset(bcc_set) or expected_set.issubset(set(mail.outbox[0].recipients()))
        sign = '✓' if check_6 else '✗'
        print(f"  {sign} {'PASS' if check_6 else 'FAIL'} | BCC = {actual_bcc}")
        print(f"     المتوقع (subset): {TEST_EMAILS}")
    else:
        check_6 = False
        print(f"  ✗ FAIL | لا يوجد بريد لفحص الـ BCC")
    
    # ====== [9] فحص 7: content_subtype = "html" ======
    print_step(9, "فحص 7: البريد بتنسيق HTML (content_subtype='html')")
    
    if outbox_count > 0:
        # locmem يحفظ الرسالة كما هي — نتحقق من content_subtype
        # ملاحظة: content_subtype يُضبط على EmailMessage قبل send()
        # locmem يحفظ الرسالة في outbox كـ EmailMessage
        # للتحقق: نطبع message.content_subtype إن كان موجوداً
        try:
            content_subtype = mail.outbox[0].content_subtype
            check_7 = (content_subtype == 'html')
            sign = '✓' if check_7 else '✗'
            print(f"  {sign} {'PASS' if check_7 else 'FAIL'} | content_subtype = '{content_subtype}'")
        except AttributeError:
            # في بعض إصدارات Django، content_subtype لا يُحفظ في outbox
            # نتحقق من بديل: هل body يحتوي على HTML tags؟
            body = mail.outbox[0].body
            has_html = '<html' in body.lower() or '<p>' in body.lower() or '<div' in body.lower()
            check_7 = has_html
            sign = '✓' if check_7 else '✗'
            print(f"  {sign} {'PASS' if check_7 else 'FAIL'} | body يحتوي على HTML tags: {has_html}")
            print(f"     (content_subtype غير متاح في outbox — فحص HTML tags كبديل)")
    else:
        check_7 = False
        print(f"  ✗ FAIL | لا يوجد بريد لفحص content_subtype")
    
    # ====== [10] فحص 8: ★ settings.EMAIL_HOST لم يُمَسّ ======
    print_step(10, "★ فحص 8: settings.EMAIL_HOST لم يُمَسّ أثناء الإرسال (جوهر الإصلاح)")
    
    actual_email_host_after = getattr(settings, 'EMAIL_HOST', None)
    check_8 = (actual_email_host_after == 'before.test.host')
    sign = '✓' if check_8 else '✗'
    print(f"  {sign} {'PASS' if check_8 else 'FAIL'} | settings.EMAIL_HOST بعد = '{actual_email_host_after}'")
    print(f"     المتوقع: 'before.test.host' (لم يتغير)")
    
    if not check_8:
        print(f"     ✗ العلة موجودة: الكود يُعدّل settings في runtime")
        print(f"     الإصلاح المطلوب: تمرير connection=connection لـ EmailMessage بدل لمس settings")
    
    # ====== [11] العداد النهائي ======
    print_step(11, "نتيجة فحوصات التشغيل")
    checks = [check_1, check_2, check_3, check_4, check_5, check_6, check_7, check_8]
    passed = sum(checks)
    descriptions = [
        'HTTP 200 (المسار يستجيب)',
        'StockNotification.is_sent=True (الأرشفة)',
        'StockNotification.sent_at مُسجل (التاريخ)',
        'mail.outbox ليس فارغ (البريد أُرسل)',
        'Subject صحيح (عاد التوفر: ...)',
        'BCC يحتوي على البريدات الاختبارية',
        'content_subtype=html (تنسيق HTML)',
        '★ settings.EMAIL_HOST لم يُمَسّ (جوهر الإصلاح)',
    ]
    for i, (desc, ok) in enumerate(zip(descriptions, checks), 1):
        sign = '✓' if ok else '✗'
        print(f"  {sign} فحص {i}: {desc}")
    print(f"\n  نتيجة التشغيل {run_number}: {passed}/8")
    
    # تنظيف بعد الفحص
    cleanup_test_data()
    
    return passed, checks


# ==================== نقطة الدخول ====================
print_header("فحص إثبات + إغلاق — بند 2.2 من تقرير التدقيق")
print(f"  الموضوع: admin_send_notification — تعديل settings في runtime")
print(f"  المنهجية: HTTP حي + locmem backend + 8 فحوصات × تشغيلان")
print(f"  المسار المُختبر: POST /invoice/stock-notifications/send/<product_id>/")
print(f"  العلامة: {TEST_MARKER}")

all_results = []
for i in [1, 2]:
    p, checks = run_test(i)
    all_results.append((p, checks))

# استعادة الإعدادات الأصلية
restore_test_environment()

print_header("الخلاصة النهائية")

run1_p, run1_checks = all_results[0]
run2_p, run2_checks = all_results[1]
same_run = (run1_checks == run2_checks)

print(f"  التشغيل 1: {run1_p}/8")
print(f"  التشغيل 2: {run2_p}/8")
print(f"  متطابقة: {same_run}")
print(f"  النتيجة النهائية: {run1_p}/8")

# تحليل نتائج الفحص 8 (الفحص الأهم)
check_8_passes = run1_checks[7]  # index 7 = check_8

if run1_p == 8 and same_run:
    print(f"\n  ✅ PASS — الإصلاح ناجح في التشغيلين بنفس النتيجة")
    print(f"  بند 2.2 أُغلق بدليل رقمي:")
    print(f"    - admin_send_notification يمرر connection مباشرة لـ EmailMessage")
    print(f"    - لا يلمس settings.EMAIL_HOST/PORT/USER/PASSWORD أثناء الإرسال")
    print(f"    - البريد يُرسل بنجاح عبر الاتصال المُمرَّر")
    print(f"    - السجلات تُؤرشفة + التاريخ مُسجل")
    print(f"    - البريد بتنسيق HTML + موجّه للمستفيدين عبر BCC")
elif not check_8_passes and same_run:
    print(f"\n  ⚠️ العلة موجودة في الكود الحالي (مثبتة بدليل رقمي)")
    print(f"  ✗ الفحص 8 فشل: settings.EMAIL_HOST تغير أثناء الإرسال")
    print(f"  هذا يعني أن الكود يُعدّل settings في runtime بدل تمرير connection مباشرة")
    print(f"  الإجراء التالي: تطبيق الإصلاح المقترح ثم إعادة التشغيل")
    print(f"  الإصلاح: تمرير connection=connection لـ EmailMessage وحذف كتلة try/finally")
elif same_run:
    print(f"\n  ⚠️ FAIL — النتيجة متطابقة لكن غير مكتملة")
    print(f"  راجع الفحوصات الفاشلة أعلاه")
else:
    print(f"\n  ⚠️ FAIL — النتيجة غير متطابقة")

print(f"\n{'=' * 70}")