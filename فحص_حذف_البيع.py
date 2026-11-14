# ============================================================
# فحص حذف فاتورة البيع — اختبار حي عبر الفيوهات نفسها
# التشغيل: python manage.py shell < "فحص_حذف_البيع.py"
# ============================================================
# فحص لائحة المبيعات مع فاتورة نقدية بلا عميل
# (هذا الفحص هو الذي كشف سطر data-customer المعلوب)
#
# التشغيل من مجلد المشروع بجانب manage.py في باورشل:
#   python manage.py shell -c "exec(open('فحص_لائحة_النقدي.py', encoding='utf-8').read())"
#
# المتوقع بعد التعديلين: 3 / 3 ناجح + سطر التنظيف
# ============================================================
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.template.loader import get_template
import invoice.models as im

# حراسة: عميل الاختبار يطلب باسم المضيف testserver — نسمح به مؤقتاً
# داخل هذه العملية فقط (نفس الحماية الموجودة في فحص_حذف_البيع.py)
if not isinstance(settings.ALLOWED_HOSTS, list):
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS)
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('testserver')

User            = get_user_model()
Sale            = im.Sale
SaleItem        = im.SaleItem
Product         = im.Product
Payment_method  = im.Payment_method
CashTransaction = im.CashTransaction

AR_PREFIX = 'فحص لائحة'
results = []

def check(name, cond, detail=''):
    results.append(bool(cond))
    print(('PASS' if cond else 'FAIL') + ' | ' + name + (' | ' + detail if detail else ''))

def cleanup():
    CashTransaction.objects.filter(sale_invoice__saleitem__item_name__startswith=AR_PREFIX).delete()
    SaleItem.objects.filter(item_name__startswith=AR_PREFIX).delete()
    Sale.objects.filter(saleitem__item_name__startswith=AR_PREFIX).delete()
    Product.objects.filter(product_name__startswith=AR_PREFIX).delete()
    Payment_method.objects.filter(name__startswith=AR_PREFIX).delete()
    User.objects.filter(username__startswith='salelist_user_').delete()

cleanup()

op_user, _ = User.objects.get_or_create(
    username='salelist_user_op',
    defaults={'is_superuser': True, 'is_staff': True}
)
if not op_user.is_superuser:
    op_user.is_superuser = True
    op_user.is_staff = True
    op_user.save()

pm, _ = Payment_method.objects.get_or_create(name=AR_PREFIX + '_نقدية', defaults={'is_cash': True})
if not pm.is_cash:
    pm.is_cash = True
    pm.save()

# فاتورة نقدية بلا عميل — الحالة التي كانت تُسقط اللائحة بالسطر المعلوب
cash_sale = Sale.objects.create(created_by=op_user, sale_payment_method=pm, paid_amount=0)
SaleItem.objects.create(sale=cash_sale, product=None, item_name=AR_PREFIX + '_بند_نقدي',
                        quantity_without_barcode=1, unit_price=5)
cash_sale.calculate_and_save_totals()
cash_sale.reconcile_cash_transactions()

client = Client()
client.force_login(op_user)

print('=' * 60)
print('فحص لائحة المبيعات مع فاتورة نقدية بلا عميل')
print('=' * 60)

# 1) القالب يُقرأ ويُترجم بلا أخطاء تركيب
try:
    get_template('invoice/sale/sale_list.html')
    check('1. قالب اللائحة يُترجم بلا أخطاء تركيب', True)
except Exception as e:
    check('1. قالب اللائحة يُترجم بلا أخطاء تركيب', False, str(e)[:120])

# 2) التصيير الحي عبر الفيو — هنا كانت صفحة الخطأ مع السطر المعلوب
crash = ''
try:
    r = client.get(reverse('invoice:sale_list'))
    status = r.status_code
    html = getattr(r, 'content', b'').decode('utf-8', 'replace')
except Exception as e:
    status, html = 0, ''
    crash = 'انهيار أثناء تصيير الصفحة: ' + str(e)[:80]
check('2. اللائحة تُصيَّر بنجاح (HTTP 200) مع فاتورة نقدية بلا عميل',
      status == 200, f'HTTP {status}' + (f' | {crash}' if crash else ''))

# 3) البديل الآمن ظاهر في الصف: «عميل نقدي» + صف حذف سليم للفاتورة
check('3. صف الفاتورة النقدية يظهر بـ«عميل نقدي» وصف الحذف سليم',
      'عميل نقدي' in html and f'data-invoice-id="{cash_sale.uniqueId}"' in html)

cleanup()
print('تم تنظيف كل بيانات الفحص من قاعدة البيانات')
print(f'النتيجة النهائية: {sum(results)} / {len(results)} ناجح')
if all(results):
    print('اللائحة سليمة مع الفواتير النقدية — التعديل مثبت ويعمل')
else:
    print('يوجد فحص فاشل — أرسل الناتج كاملاً فوراً')