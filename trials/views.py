from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import HttpResponseForbidden
from .utils import provision_trial_database
from .models import Trial

# دالة مساعدة لجلب الـ IP الحقيقي للمستخدم
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# ===== صفحة طلب الفترة التجريبية =====
def request_trial(request):
    if request.method == 'POST':
        ip_address = get_client_ip(request)
        cache_key = f'trial_ratelimit_{ip_address}'
        request_count = cache.get(cache_key, 0)

        if request_count >= 3:
            messages.error(request, 'لقد تجاوزت عدد محاولات الإرسال المسموح بها. يرجى الانتظار دقيقة ثم المحاولة.')
            return redirect('trials:request_trial')

        email = request.POST.get('email')
        if User.objects.filter(username=email).exists():
            messages.error(request, 'البريد الإلكتروني مستخدم مسبقاً.')
            return redirect('trials:request_trial')

        try:
            form_data = {
                'company_name': request.POST.get('company_name'),
                'full_name': request.POST.get('full_name'),
                'email': email,
                'phone_number': request.POST.get('phone_number'),
                'is_whatsapp': request.POST.get('is_whatsapp') == 'on',
                'subscribe_whatsapp': request.POST.get('subscribe_whatsapp') == 'on',
                'subscribe_email': request.POST.get('subscribe_email') == 'on',
                'notes': request.POST.get('notes'),
            }

            user, generated_password, db_name = provision_trial_database(form_data)
            
            request.session['trial_credentials'] = {
                'username': user.username,
                'password': generated_password
            }

            cache.set(cache_key, request_count + 1, 60)
            return redirect('trials:trial_success')
            
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء إنشاء التجربة: {str(e)}')
            cache.set(cache_key, request_count + 1, 60)
            return redirect('trials:request_trial')

    return render(request, 'trials/request_trial.html')

# ===== صفحة نجاح التسجيل =====
def trial_success(request):
    credentials = request.session.pop('trial_credentials', None)
    return render(request, 'trials/success.html', {'credentials': credentials})


# ======================================
# ===== دوال الإدارة (الواجهة الأمامية) =====
# ==========================================

# دالة مساعدة للتحقق من الصلاحيات (تمنع العملاء التجريبيين وتسمح للمدير)
def check_admin_access(request):
    # 1. منع العميل التجريبي من الدخول (حتى لو كان سوبر يوزر في قاعدته)
    if Trial.objects.filter(user_id=request.user.id).exists():
        return False
    # 2. السماح فقط للمدير الأساسي الذي يملك is_staff
    return request.user.is_staff

# ===== صفحة إدارة التجارب =====
@login_required
def manage_trials(request):
    if not check_admin_access(request):
        return HttpResponseForbidden("ليس لديك صلاحية للوصول إلى هذه الصفحة.")
        
    all_trials = Trial.objects.all().order_by('-start_date')
    
    active_trials = all_trials.filter(is_active=True, expiry_date__gte=timezone.now())
    expired_trials = all_trials.filter(is_active=True, expiry_date__lt=timezone.now())
    stopped_trials = all_trials.filter(is_active=False)

    context = {
        'active_trials': active_trials,
        'expired_trials': expired_trials,
        'stopped_trials': stopped_trials,
    }
    return render(request, 'trials/manage_trials.html', context)

# ===== إيقاف تجربة يدوياً =====
@login_required
def stop_trial(request, trial_id):
    if not check_admin_access(request):
        return HttpResponseForbidden("ليس لديك صلاحية.")
        
    if request.method == 'POST':
        trial = get_object_or_404(Trial, id=trial_id)
        if trial.is_active:
            trial.is_active = False
            trial.save()
            
            user = trial.user
            user.is_active = False
            user.save()
            
            messages.success(request, f'تم إيقاف التجربة للمستخدم {trial.full_name} بنجاح.')
    return redirect('trials:manage_trials')

# ===== حذف قاعدة بيانات تجربة نهائياً =====
@login_required
def delete_trial(request, trial_id):
    if not check_admin_access(request):
        return HttpResponseForbidden("ليس لديك صلاحية.")
        
    if request.method == 'POST':
        trial = get_object_or_404(Trial, id=trial_id)
        
        # حماية: لا يمكن حذف قاعدة بيانات عميل لا تزال فترته نشطة
        if trial.expiry_date > timezone.now() and trial.is_active:
            messages.error(request, 'لا يمكن حذف قاعدة بيانات عميل لا تزال فترته التجريبية نشطة!')
            return redirect('trials:manage_trials')
        
        db_name = trial.db_name
        try:
            # 1. حذف قاعدة البيانات المعزولة من MySQL
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{db_name}`;")
            
            # 2. تعطيل المستخدم في القاعدة الرئيسية
            user = trial.user
            user.is_active = False
            user.save()
            
            # 3. حذف سجل التجربة من جدول Trials
            trial.delete()
            messages.success(request, f'تم حذف قاعدة البيانات {db_name} والعميل {trial.full_name} نهائياً.')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء الحذف: {str(e)}')
            
    return redirect('trials:manage_trials')