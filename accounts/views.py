# ==================== مكتبات بايثون القياسية ====================
import os
import shutil
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlparse

# ==================== مكتبات خارجية ====================
import requests
from django_ratelimit.decorators import ratelimit

# ==================== إطار عمل Django الأساسي ====================
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate, get_user_model, login, update_session_auth_hash
)
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import Group, Permission, User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

# ==================== التطبيقات الأخرى ====================
from invoice.models import (
    Product, Purch, PurchaseReturn, Sale, SaleReturn, WebsiteOrder
)
from invoice.utils import get_active_email_connection

# ==================== النماذج المحلية (Models) ====================
from .models import CompanySettings, Profile

# ==================== النماذج المحلية (Forms) ====================
from .forms import (
    CompanySettingsForm, CustomPasswordResetForm, CustomUserCreationForm,
    TrialRequestForm, UserProfileUpdateForm, UserUpdateForm
)

# ==================== متغيرات عامة ====================
CustomUser = get_user_model()


# ============================================
# الصفحة الرئيسية (index)
# ============================================

def index(request):
    """
    الصفحة الرئيسية للموقع:
    - إذا كان المستخدم مسجلاً: يعرض لوحة التحكم (dashboard)
    - إذا كان غير مسجل: يعرض الصفحة التعريفية (landing page)
    """
    
    # إذا كان المستخدم مسجلاً دخوله، اعرض لوحة التحكم
    if request.user.is_authenticated:
        # ===== إعداد متغير الشاشة الحمراء (تغيير كلمة المرور الافتراضية) =====
        show_force_change = False
        if request.user.check_password('Admin@123456'):
            show_force_change = True

        # فخ تغيير كلمة المرور
        if request.session.get('force_change'):
            return redirect('accounts:force_password_change')

        # ===== الاستيرادات اللازمة =====
        from datetime import timedelta, date
        from decimal import Decimal
        from django.db.models import Sum, Q, F
        from django.urls import reverse
        from django.utils import timezone
        from invoice.models import (
            Purch, Sale, SaleReturn, PurchaseReturn,
            Product, WebsiteOrder, SaleItem, CashTransaction
        )
        from accounts.models import CompanySettings
        from invoice.utils import is_custom_password_set

        # ===== جلب إعدادات الشركة =====
        settings = CompanySettings.get_settings()

        # ===== حالة كلمة مرور التسعير =====
        pricing_pw_is_custom = is_custom_password_set()

        # ===== حساب الفترات الزمنية =====
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)
        sixty_days_ago = thirty_days_ago - timedelta(days=30)

        # دالة مساعدة لحساب الاتجاه
        def calc_trend(current, previous, reverse=False):
            if previous == 0:
                return 0 if current == 0 else (100 if not reverse else -100)
            change = ((current - previous) / previous) * 100
            if reverse:
                change = -change
            return round(change, 1)

        # ============================================
        # 1. إحصائيات فواتير الشراء
        # ============================================
        current_purch = Purch.objects.filter(purch_date__gte=thirty_days_ago).count()
        previous_purch = Purch.objects.filter(
            purch_date__gte=sixty_days_ago,
            purch_date__lt=thirty_days_ago
        ).count()
        purch_trend = calc_trend(current_purch, previous_purch)

        # ============================================
        # 2. إحصائيات فواتير البيع
        # ============================================
        current_sale = Sale.objects.filter(sale_date__gte=thirty_days_ago).count()
        previous_sale = Sale.objects.filter(
            sale_date__gte=sixty_days_ago,
            sale_date__lt=thirty_days_ago
        ).count()
        sale_trend = calc_trend(current_sale, previous_sale)

        # ============================================
        # 3. إحصائيات المرتجعات
        # ============================================
        current_return = (
            SaleReturn.objects.filter(return_date__gte=thirty_days_ago).count() +
            PurchaseReturn.objects.filter(return_date__gte=thirty_days_ago).count()
        )
        previous_return = (
            SaleReturn.objects.filter(
                return_date__gte=sixty_days_ago,
                return_date__lt=thirty_days_ago
            ).count() +
            PurchaseReturn.objects.filter(
                return_date__gte=sixty_days_ago,
                return_date__lt=thirty_days_ago
            ).count()
        )
        return_trend = calc_trend(current_return, previous_return, reverse=True)

        # ============================================
        # 4. عدد المنتجات
        # ============================================
        product_count = Product.objects.count()

        # ============================================
        # 5. طلبات المتجر الجديدة
        # ============================================
        new_orders_count = WebsiteOrder.objects.filter(status='new').count()

        # ============================================
        # 6. الرسم البياني للمبيعات (آخر 7 أيام)
        # ============================================
        chart_labels = []
        chart_values = []
        weekday_names = {
            0: 'الاثنين', 1: 'الثلاثاء', 2: 'الأربعاء',
            3: 'الخميس', 4: 'الجمعة', 5: 'السبت', 6: 'الأحد'
        }

        for i in range(6, -1, -1):
            target_date = today - timedelta(days=i)
            chart_labels.append(weekday_names.get(target_date.weekday(), str(target_date)))

            daily_total = Sale.objects.filter(sale_date=target_date).aggregate(
                total=Sum('sale_final_total')
            )['total'] or Decimal('0.00')
            chart_values.append(float(daily_total))

        # ============================================
        # 7. الرسم البياني المتكامل (آخر 30 يوماً)
        # ============================================
        def get_advanced_chart_data(days=30):
            """جلب بيانات متكاملة للرسم البياني"""
            adv_labels = []
            sales_data = []
            profit_data = []
            expenses_data = []

            for i in range(days - 1, -1, -1):
                target_date = today - timedelta(days=i)
                adv_labels.append(weekday_names.get(target_date.weekday(), str(target_date)))

                daily_sales = Sale.objects.filter(
                    sale_date=target_date
                ).aggregate(total=Sum('sale_final_total'))['total'] or Decimal('0.00')
                sales_data.append(float(daily_sales))

                daily_sale_items = SaleItem.objects.filter(
                    sale__sale_date=target_date
                ).select_related('product')

                daily_cogs = Decimal('0.00')
                for item in daily_sale_items:
                    if item.product:
                        cost_price = item.product.average_purchase_cost or item.product.purch_price or Decimal('0.00')
                        daily_cogs += item.sold_quantity * cost_price

                daily_profit = daily_sales - daily_cogs
                profit_data.append(float(daily_profit))

                daily_expenses = CashTransaction.objects.filter(
                    transaction_date__date=target_date,
                    transaction_type__in=['expense', 'withdrawal']
                ).aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')
                expenses_data.append(float(daily_expenses))

            return {
                'labels': adv_labels,
                'sales': sales_data,
                'profit': profit_data,
                'expenses': expenses_data,
            }

        advanced_chart_data = get_advanced_chart_data(days=30)

        # ============================================
        # 8. أفضل المنتجات مبيعاً (Top Products)
        # ============================================
        def get_top_products(limit=10):
            """جلب أفضل المنتجات مبيعاً من حيث الكمية والقيمة"""

            top_by_quantity = SaleItem.objects.filter(
                product__isnull=False
            ).values(
                'product__id',
                'product__product_name',
                'product__product_image'
            ).annotate(
                total_quantity=Sum('sold_quantity'),
                total_value=Sum(F('sold_quantity') * F('unit_price'))
            ).filter(
                total_quantity__gt=0
            ).order_by('-total_quantity')[:limit]

            top_by_value = SaleItem.objects.filter(
                product__isnull=False
            ).values(
                'product__id',
                'product__product_name',
                'product__product_image'
            ).annotate(
                total_value=Sum(F('sold_quantity') * F('unit_price')),
                total_quantity=Sum('sold_quantity')
            ).filter(
                total_value__gt=0
            ).order_by('-total_value')[:limit]

            def format_product(item):
                image_field = item.get('product__product_image')
                image_url = None
                if image_field:
                    if hasattr(image_field, 'url'):
                        image_url = image_field.url
                    elif isinstance(image_field, str) and image_field.strip():
                        image_url = '/media/' + image_field.lstrip('/')

                return {
                    'id': item['product__id'],
                    'name': item['product__product_name'],
                    'quantity': float(item['total_quantity']),
                    'value': float(item['total_value']),
                    'image': image_url,
                }

            return {
                'top_by_quantity': [format_product(item) for item in top_by_quantity],
                'top_by_value': [format_product(item) for item in top_by_value],
            }

        top_products = get_top_products(limit=10)

        # ============================================
        # 9. تنبيهات النظام
        # ============================================
        alerts = []

        # أ. المنتجات منخفضة المخزون
        low_stock_products = Product.objects.filter(
            current_stock_quantity__lt=5,
            current_stock_quantity__gt=0
        )[:5]

        for product in low_stock_products:
            alerts.append({
                'type': 'warning',
                'icon': 'fa-exclamation-triangle',
                'title': 'مخزون منخفض',
                'message': f'منتج "{product.product_name}" - المتبقي: {product.current_stock_quantity}',
                'link': reverse('invoice:product_detail', args=[product.slug]),
                'link_text': 'تحديث المخزون'
            })

        # ب. المنتجات المنفذة
        out_of_stock_products = Product.objects.filter(current_stock_quantity=0)[:3]
        for product in out_of_stock_products:
            alerts.append({
                'type': 'danger',
                'icon': 'fa-times-circle',
                'title': 'منتج غير متوفر',
                'message': f'منتج "{product.product_name}" نفد من المخزون',
                'link': reverse('invoice:product_detail', args=[product.slug]),
                'link_text': 'طلب شراء'
            })

        # ج. فواتير غير مدفوعة
        fifteen_days_ago = today - timedelta(days=15)
        unpaid_sales = Sale.objects.filter(
            is_paid=False,
            sale_date__lte=fifteen_days_ago
        )[:3]

        for sale in unpaid_sales:
            alerts.append({
                'type': 'danger',
                'icon': 'fa-exclamation-circle',
                'title': 'فاتورة غير مدفوعة',
                'message': f'فاتورة {sale.uniqueId} - المتبقي: {sale.balance_due}',
                'link': reverse('invoice:sale_detail', args=[sale.slug]),
                'link_text': 'متابعة التحصيل'
            })

        # د. طلبات متجر جديدة
        new_website_orders = WebsiteOrder.objects.filter(status='new')[:3]
        for order in new_website_orders:
            alerts.append({
                'type': 'info',
                'icon': 'fa-shopping-cart',
                'title': 'طلب جديد',
                'message': f'طلب #{order.id} - {order.full_name} - {order.total_amount}',
                'link': reverse('invoice:order_detail', args=[order.id]),
                'link_text': 'معالجة الطلب'
            })

        # ============================================
        # 10. تعليقات الفيسبوك
        # ============================================
        fb_comments = []
        if settings.fb_page_id and settings.fb_access_token:
            try:
                import requests
                url = f"https://graph.facebook.com/v18.0/{settings.fb_page_id}/feed"
                params = {
                    'fields': 'from{name,picture},message,created_time,permalink_url',
                    'access_token': settings.fb_access_token,
                    'limit': 5
                }
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    for post in data.get('data', []):
                        if 'message' in post:
                            fb_comments.append(post)
            except Exception as e:
                print(f"Facebook Error: {e}")

        # ============================================
        # تجهيز السياق
        # ============================================
        context = {
            'user': request.user,
            'settings': settings,
            'fb_comments': fb_comments,
            'show_force_change': show_force_change,
            'pricing_pw_is_custom': pricing_pw_is_custom,
            'purch_count': current_purch,
            'purch_trend': purch_trend,
            'sale_count': current_sale,
            'sale_trend': sale_trend,
            'return_count': current_return,
            'return_trend': return_trend,
            'product_count': product_count,
            'new_orders_count': new_orders_count,
            'chart_labels': chart_labels,
            'chart_values': chart_values,
            'advanced_chart_data': advanced_chart_data,
            'top_products': top_products,
            'alerts': alerts,
        }

        return render(request, 'accounts/dashboard.html', context)
    
    # إذا كان المستخدم غير مسجل، اعرض الصفحة التعريفية
    else:
        return render(request, 'accounts/index.html')


# ============================================
# صفحة الشروط والأحكام (عرض ثابت)
# ============================================

class TermsView(TemplateView):
    """عرض صفحة الشروط والأحكام"""
    template_name = 'accounts/terms.html'


# ============================================
# رفع شعار الشركة (API endpoint)
# ============================================

@csrf_exempt
@login_required
def upload_company_logo(request):
    """
    رفع شعار الشركة - يستخدم عبر AJAX
    """
    if request.method == 'POST':
        profile = request.user.profile
        if 'logo' in request.FILES:
            profile.logo = request.FILES['logo']
            profile.save()
            return JsonResponse({'success': True, 'logo_url': profile.logo.url})
        else:
            return JsonResponse({'success': False, 'error': 'لم يتم إرسال أي صورة'})
    return JsonResponse({'success': False, 'error': 'طلب غير صالح'})


# ============================================
# تسجيل مستخدم جديد (register)
# ============================================


CustomUser = get_user_model()

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# accounts/views.py

def register_view(request):
    if request.method == 'POST':
        ip_address = get_client_ip(request)
        cache_key = f'register_ratelimit_{ip_address}'
        request_count = cache.get(cache_key, 0)

        if request_count >= 3:
            form = CustomUserCreationForm()
            form.add_error(None, 'لقد تجاوزت عدد محاولات التسجيل المسموح بها. يرجى الانتظار دقيقة.')
        else:
            form = CustomUserCreationForm(request.POST)
            if form.is_valid():
                # حفظ المستخدم
                user = form.save()
                user.is_active = False
                user.save(update_fields=['is_active'])

                # إعداد رابط التفعيل
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                current_site = get_current_site(request)
                domain = current_site.domain
                protocol = 'https' if request.is_secure() else 'http'
                
                context = {
                    'user': user,
                    'protocol': protocol,
                    'domain': domain,
                    'uid': uid,
                    'token': token,
                }
                subject = render_to_string('accounts/activation_subject.txt', context)
                subject = ''.join(subject.splitlines())
                html_message = render_to_string('accounts/activation_email.html', context)

                # إرسال الإيميل
                try:
                    from_email = 'noreply@example.com'
                    email = EmailMessage(subject, html_message, from_email, [user.email])
                    email.content_subtype = 'html'
                    email.send()
                except Exception as e:
                    print(f"Error sending email: {e}")

                cache.set(cache_key, request_count + 1, 60)
                messages.success(request, 'تم إنشاء حسابك بنجاح! يرجى التحقق من بريدك الإلكتروني لتفعيل الحساب قبل تسجيل الدخول.')
                return redirect('index')
            else:
                cache.set(cache_key, request_count + 1, 60)
    else:
        form = CustomUserCreationForm()

    context = {
        'register_form': form,  # ✅ استخدم register_form بدلاً من form
        'trial_form': TrialRequestForm(),  # ✅ أضف trial_form
        'open_register_modal': request.method == 'POST' and not form.is_valid()
    }
    return render(request, 'accounts/register.html', context)

# === دالة التفعيل مع أوامر التشخيص ===
def activate_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
        print(f"=== ACTIVATE DEBUG | User found: {user.username} | Is Active: {user.is_active} ===")
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist) as e:
        user = None
        print(f"=== ACTIVATE DEBUG | User NOT found or Error: {e} ===")

    if user is not None:
        token_valid = default_token_generator.check_token(user, token)
        print(f"=== ACTIVATE DEBUG | Token Valid: {token_valid} ===")
        
        if token_valid:
            user.is_active = True
            user.save()
            print(f"=== ACTIVATE DEBUG | Account Activated! ===")
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'تم تفعيل حسابك بنجاح! مرحباً بك في نظام الأزوردي.')
            return redirect('index')
    
    # إذا كان الرابط خاطئاً أو منتهي الصلاحية
    print("=== ACTIVATE DEBUG | Activation Failed! ===")
    messages.error(request, 'رابط التفعيل غير صالح أو منتهي الصلاحية.')
    return redirect('accounts:login')


# === نموذج تسجيل دخول مخصص لعرض رسالة واضحة للحسابات غير المفعلة ===


class CustomLoginForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise ValidationError(
                "حسابك غير مفعل. يرجى التحقق من بريدك الإلكتروني لتفعيله قبل تسجيل الدخول.",
                code='inactive',
            )
        super().confirm_login_allowed(user)






#======================للحذف ===========================
# دالة مساعدة لجلب الـ IP الحقيقي للمستخدم

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# accounts/views.py

def trial_request_view(request):
    if request.method == 'POST':
        ip_address = get_client_ip(request)
        cache_key = f'trial_ratelimit_{ip_address}'
        request_count = cache.get(cache_key, 0)

        if request_count >= 3:
            form = TrialRequestForm(request.POST)
            form.add_error(None, 'لقد تجاوزت عدد محاولات إرسال الطلبات المسموح بها. يرجى الانتظار دقيقة ثم المحاولة.')
        else:
            form = TrialRequestForm(request.POST)
            if form.is_valid():
                trial_request = form.save()
                messages.success(request, 'تم إرسال طلبك بنجاح! سيقوم فريقنا بمراجعته والتواصل معك قريباً.')
                cache.set(cache_key, request_count + 1, 60)
                return redirect('index')
            else:
                cache.set(cache_key, request_count + 1, 60)
    else:
        form = TrialRequestForm()

    context = {
        'form': form,  # ✅ استخدم 'form' لأن القالب يستخدم 'form'
    }
    return render(request, 'accounts/Trial Request Page.html', context)

#======================للحذف ===========================

# ============================================
# استعادة كلمة المرور (Password Reset)
# ============================================


class CustomPasswordResetView(SuccessMessageMixin, PasswordResetView):
    """تخصيص عملية استعادة كلمة المرور لاستخدام إعدادات البريد من قاعدة البيانات"""
    template_name = 'accounts/password_reset_form.html'
    email_template_name = 'accounts/password_reset_email.html'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = '/accounts/password_reset/done/'
    html_email_template_name = 'accounts/password_reset_email.html'
    success_message = "تم إرسال رابط استعادة كلمة المرور إلى بريدك الإلكتروني."
    form_class = CustomPasswordResetForm

    def form_valid(self, form):
        """تعديل إعدادات البريد مؤقتاً لاستخدام إعدادات قاعدة البيانات"""
        connection, from_email = get_active_email_connection()
        
        if connection and from_email:
            # حفظ الإعدادات الحالية
            old_host = getattr(settings, 'EMAIL_HOST', None)
            old_port = getattr(settings, 'EMAIL_PORT', None)
            old_user = getattr(settings, 'EMAIL_HOST_USER', None)
            old_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', None)
            old_tls = getattr(settings, 'EMAIL_USE_TLS', None)
            old_from = getattr(settings, 'DEFAULT_FROM_EMAIL', None)

            try:
                # تحديث الإعدادات مؤقتاً
                settings.EMAIL_HOST = connection.host
                settings.EMAIL_PORT = connection.port
                settings.EMAIL_HOST_USER = connection.username
                settings.EMAIL_HOST_PASSWORD = connection.password
                settings.EMAIL_USE_TLS = connection.use_tls
                settings.DEFAULT_FROM_EMAIL = from_email
                return super().form_valid(form)
            finally:
                # استعادة الإعدادات الأصلية
                settings.EMAIL_HOST = old_host
                settings.EMAIL_PORT = old_port
                settings.EMAIL_HOST_USER = old_user
                settings.EMAIL_HOST_PASSWORD = old_pass
                settings.EMAIL_USE_TLS = old_tls
                settings.DEFAULT_FROM_EMAIL = old_from
        else:
            return super().form_valid(form)




# ============================================
# الملف الشخصي (profile)
# ============================================



@login_required
def profile_view(request):
    """
    عرض وتعديل الملف الشخصي للمستخدم
    """
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث ملفك الشخصي بنجاح!')
            return redirect('accounts:profile')
    else:
        form = UserProfileUpdateForm(instance=profile)
    
    context = {
        'form': form,
        'profile': profile
    }
    return render(request, 'accounts/profile.html', context)



# ============================================
# سجلات النظام (system logs)
# ============================================




def is_admin_or_support(user):
    """التحقق من أن المستخدم مدير أو دعم فني"""
    return user.is_superuser or user.is_staff





@login_required
@user_passes_test(is_admin_or_support, login_url='accounts:login')
def system_logs_view(request):
    """عرض سجلات النظام مع إمكانية التصفية والبحث والحذف"""
    
    # معالجة طلب الحذف
    if request.method == 'POST' and request.user.is_superuser:
        log_type_to_clear = request.POST.get('log_type_to_clear')
        if log_type_to_clear in ['debug', 'errors', 'info']:
            log_file_path = os.path.join(settings.BASE_DIR, 'logs', f'{log_type_to_clear}.log')
            try:
                # فتح الملف بصيغة الكتابة يمسح محتواه فوراً
                with open(log_file_path, 'w') as f:
                    pass 
                messages.success(request, f'تم مسح سجلات {log_type_to_clear} بنجاح.')
                # العودة لنفس الصفحة مع الحفاظ على الفلاتر
                current_level = request.GET.get('level', 'ALL')
                current_q = request.GET.get('q', '')
                return redirect(f"{request.path}?log_type={log_type_to_clear}&level={current_level}&q={current_q}")
            except Exception as e:
                messages.error(request, f'حدث خطأ أثناء مسح السجلات: {str(e)}')

    # جلب الفلاتر من الرابط
    log_type = request.GET.get('log_type', 'info')
    if log_type not in ['debug', 'errors', 'info']:
        log_type = 'info'
    
    current_level = request.GET.get('level', 'ALL')
    search_query = request.GET.get('q', '').lower()
    
    log_file_path = os.path.join(settings.BASE_DIR, 'logs', f'{log_type}.log')
    
    # حساب حجم الملف
    file_size_mb = 0
    if os.path.exists(log_file_path):
        file_size_mb = round(os.path.getsize(log_file_path) / (1024 * 1024), 2)
    
    if not os.path.exists(log_file_path):
        return render(request, 'accounts/system_logs.html', {
            'error': f'ملف السجل غير موجود. المسار المتوقع: {log_file_path}',
            'page_obj': [],
            'log_levels': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            'current_level': current_level,
            'current_log_type': log_type,
            'log_types': ['debug', 'errors', 'info'],
            'search_query': search_query,
            'file_size_mb': file_size_mb,
        })
    
    # قراءة وتحليل السجلات
    logs = []
    log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    
    try:
        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            lines.reverse()  # عرض الأحدث أولاً

        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # تطبيق البحث أولاً (لأنه الأسرع)
            if search_query and search_query not in line.lower():
                continue

            try:
                parts = line.split(' ', 3)
                if len(parts) < 4:
                    logs.append({'timestamp': '', 'level': 'RAW', 'message': line, 'level_class': 'raw'})
                    continue
                
                date_str, time_str, level_str, message = parts[0], parts[1], parts[2], ' '.join(parts[3:])
                
                # تطبيق فلتر المستوى
                if current_level != 'ALL' and level_str != current_level:
                    continue
                
                logs.append({
                    'timestamp': f"{date_str} {time_str}",
                    'level': level_str,
                    'message': message,
                    'level_class': level_str.lower()
                })
            except Exception:
                logs.append({'timestamp': '', 'level': 'RAW', 'message': line, 'level_class': 'raw'})
                
    except Exception as e:
        logs.append({'timestamp': '', 'level': 'ERROR', 'message': f'حدث خطأ أثناء قراءة ملف السجل: {str(e)}', 'level_class': 'error'})
    
    # تقسيم النتائج إلى صفحات
    paginator = Paginator(logs, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'log_levels': log_levels,
        'current_level': current_level,
        'current_log_type': log_type,
        'log_types': ['debug', 'errors', 'info'],
        'is_superuser': request.user.is_superuser,
        'search_query': search_query,
        'file_size_mb': file_size_mb,
    }
    return render(request, 'accounts/system_logs.html', context)



# ============================================
# إدارة المستخدمين (user list)
# ============================================

def is_staff_user(user):
    """التحقق من أن المستخدم موظف"""
    return user.is_staff



@login_required
@user_passes_test(is_staff_user)
def user_list_view(request):
    """عرض قائمة بجميع المستخدمين في النظام"""
    users = User.objects.all().order_by('-date_joined')
    context = {
        'users': users,
        'title': 'قائمة المستخدمين'
    }
    return render(request, 'accounts/user_list.html', context)




@login_required
@user_passes_test(is_staff_user)
def user_edit_view(request, pk):
    """تحرير بيانات مستخدم معين"""
    user = get_object_or_404(User, pk=pk)
    profile, created = Profile.objects.get_or_create(user=user)

    # تحضير المجموعات المتاحة
    available_groups = Group.objects.all().order_by('name')

    # تحديد المجموعة الحالية للمستخدم (أول مجموعة إن وُجدت)
    current_group = user.groups.first()
    current_group_id = current_group.id if current_group else None
    current_group_permissions = []
    if current_group:
        current_group_permissions = current_group.permissions.select_related('content_type').all()

    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=user)
        profile_form = UserProfileUpdateForm(
            request.POST, request.FILES, instance=profile, is_admin=True
        )

        if form.is_valid() and profile_form.is_valid():
            form.save()
            profile_form.save()

            # === حفظ المجموعة ===
            group_id = request.POST.get('group_id', '')
            user.groups.clear()  # إزالة جميع المجموعات الحالية
            if group_id:
                try:
                    group = Group.objects.get(id=group_id)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    pass

            messages.success(
                request,
                f'تم تحديث بيانات المستخدم "{user.username}" بنجاح.'
            )
            return redirect('accounts:user_list')
    else:
        form = UserUpdateForm(instance=user)
        profile_form = UserProfileUpdateForm(instance=profile, is_admin=True)

    context = {
        'form': form,
        'profile_form': profile_form,
        'user_to_edit': user,
        'profile': profile,
        'title': f'تحرير المستخدم: {user.username}',
        # متغيرات المجموعات
        'available_groups': available_groups,
        'current_group': current_group,
        'current_group_id': current_group_id,
        'current_group_permissions': current_group_permissions,
    }
    return render(request, 'accounts/user_edit.html', context)


@login_required
@user_passes_test(is_staff_user)
def group_permissions_api(request, group_id):
    """عرض صلاحيات مجموعة معينة (JSON) — يُستخدم عبر AJAX"""
    try:
        group = Group.objects.get(id=group_id)
        permissions = group.permissions.select_related('content_type').all()
        perms_list = [perm.name for perm in permissions]
        return JsonResponse({
            'group_name': group.name,
            'permissions': perms_list,
        })
    except Group.DoesNotExist:
        return JsonResponse({'error': 'المجموعة غير موجودة'}, status=404)


# ============================================
# إدارة الصلاحيات (permissions)
# ============================================

@login_required
@user_passes_test(is_staff_user)
def permissions_view(request):
    """
    صفحة لإدارة الصلاحيات والأدوار (المجموعات)
    """
    groups = Group.objects.all().prefetch_related('permissions')
    all_permissions = Permission.objects.select_related('content_type').order_by('content_type__app_label', 'codename')
    
    # تنظيم الصلاحيات حسب النموذج
    permissions_by_model = {}
    for perm in all_permissions:
        model_name = perm.content_type.model_class().__name__ if perm.content_type.model_class() else perm.content_type.model
        if model_name not in permissions_by_model:
            permissions_by_model[model_name] = []
        permissions_by_model[model_name].append(perm)
    
    # إنشاء مجموعة جديدة
    if request.method == 'POST' and 'create_group' in request.POST:
        group_name = request.POST.get('group_name')
        if group_name:
            if Group.objects.filter(name=group_name).exists():
                messages.error(request, f'المجموعة "{group_name}" موجودة بالفعل.')
            else:
                new_group = Group.objects.create(name=group_name)
                selected_permissions = request.POST.getlist('permissions')
                new_group.permissions.set(selected_permissions)
                messages.success(request, f'تم إنشاء المجموعة "{group_name}" بنجاح.')
                return redirect('accounts:permissions')
        else:
            messages.error(request, 'اسم المجموعة لا يمكن أن يكون فارغًا.')
    
    # تحرير مجموعة
    if request.method == 'POST' and 'edit_group' in request.POST:
        group_id = request.POST.get('group_id')
        group_to_edit = get_object_or_404(Group, pk=group_id)
        selected_permissions = request.POST.getlist('permissions')
        group_to_edit.permissions.set(selected_permissions)
        messages.success(request, f'تم تحديث صلاحيات المجموعة "{group_to_edit.name}" بنجاح.')
        return redirect('accounts:permissions')
    
    # حذف مجموعة
    if request.method == 'POST' and 'delete_group' in request.POST:
        group_id = request.POST.get('group_id')
        group_to_delete = get_object_or_404(Group, pk=group_id)
        group_name = group_to_delete.name
        group_to_delete.delete()
        messages.success(request, f'تم حذف المجموعة "{group_name}" بنجاح.')
        return redirect('accounts:permissions')
    
    context = {
        'title': 'الصلاحيات والأدوار',
        'groups': groups,
        'permissions_by_model': permissions_by_model,
    }
    return render(request, 'accounts/permissions.html', context)





@login_required
@user_passes_test(lambda u: u.is_superuser)
def company_settings_view(request):
    """
    صفحة تعديل إعدادات الشركة والفوتر
    - فقط المدير (Superuser) يمكنه الوصول
    - تعرض نموذج تعديل جميع إعدادات الشركة
    - تمسح الكاش بعد كل حفظ لضمان ظهور البيانات الجديدة فوراً
    """
    # جلب الإعدادات الحالية
    settings = CompanySettings.get_settings()
    
    if request.method == 'POST':
        # تمرير البيانات والملفات إلى النموذج مع ربطها بالكائن الحالي
        form = CompanySettingsForm(request.POST, request.FILES, instance=settings)
        
        if form.is_valid():
            # حفظ النموذج (دالة save المخصصة ستمسح الكاش تلقائياً)
            form.save()
            
            # مسح الكاش مرة أخرى للتأكد (احتياطي)
            cache.delete('company_settings')
            
            messages.success(request, 'تم حفظ إعدادات الشركة بنجاح!')
            
            # إعادة التوجيه لمنع إعادة إرسال النموذج عند التحديث
            return redirect('accounts:company_settings')
        else:
            # عرض أخطاء النموذج
            messages.error(request, 'حدث خطأ في حفظ البيانات. يرجى التحقق من المدخلات.')
            
            # طباعة الأخطاء في الكونسول للتصحيح (يمكن حذفه لاحقاً)
            for field, errors in form.errors.items():
                for error in errors:
                    print(f"خطأ في الحقل {field}: {error}")
    else:
        # عرض النموذج فارغ في حالة GET مع تعبئته بالبيانات الحالية
        form = CompanySettingsForm(instance=settings)
    
    # تمرير السياق للقالب
    context = {
        'form': form,
        'settings': settings,
        'title': 'إعدادات الشركة والفوتـر'
    }
    
    return render(request, 'accounts/company_settings.html', context)


#من اجل دليل المستخدم




def user_manual(request):
    # تحديد مسار ملف الدليل
    manual_path = os.path.join(settings.BASE_DIR, 'docs', 'index.md')
    
    try:
        # قراءة محتوى الملف
        with open(manual_path, 'r', encoding='utf-8') as f:
            manual_content = f.read()
    except FileNotFoundError:
        manual_content = "عذراً، ملف الدليل (index.md) غير موجود في مجلد docs."

    return render(request, 'accounts/user_manual.html', {
        'manual_content': manual_content
    })


    