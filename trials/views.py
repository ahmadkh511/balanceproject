from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.cache import cache
from .utils import provision_trial_database

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def request_trial(request):
    if request.method == 'POST':
        ip_address = get_client_ip(request)
        cache_key = f'trial_ratelimit_{ip_address}'
        request_count = cache.get(cache_key, 0)

        if request_count >= 3:
            messages.error(request, 'لقد تجاوزت عدد محاولات الإرسال المسموح بها. يرجى الانتظار دقيقة ثم المحاولة.')
            return redirect('trials:request_trial')

        # التحقق من عدم وجود البريد مسبقاً
        email = request.POST.get('email')
        if User.objects.filter(username=email).exists():
            messages.error(request, 'البريد الإلكتروني مستخدم مسبقاً.')
            return redirect('trials:request_trial')

        try:
            # تجهيز البيانات من الطلب
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

            # إنشاء قاعدة البيانات والمستخدم
            user, generated_password, db_name = provision_trial_database(form_data)
            
            # تخزين كلمة المرور في الجلسة مؤقتاً لعرضها في صفحة النجاح
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

def trial_success(request):
    # جلب بيانات الدخول من الجلسة
    credentials = request.session.pop('trial_credentials', None)
    return render(request, 'trials/success.html', {'credentials': credentials})