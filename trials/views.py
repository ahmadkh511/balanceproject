from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from .utils import provision_trial_database

def request_trial(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')

        # تحقق بسيط من عدم وجود المستخدم مسبقاً
        if User.objects.filter(username=username).exists():
            messages.error(request, 'اسم المستخدم موجود مسبقاً، اختر اسماً آخر.')
            return redirect('trials:request_trial')

        try:
            # استدعاء الدالة التي تنشئ قاعدة البيانات والمستخدم
            user, db_name = provision_trial_database(username, email, password)
            messages.success(request, f'تم إنشاء حسابك التجريبي بنجاح! يمكنك الآن تسجيل الدخول.')
            return redirect('trials:trial_success')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء إنشاء التجربة: {str(e)}')
            return redirect('trials:request_trial')

    return render(request, 'trials/request_trial.html')

def trial_success(request):
    return render(request, 'trials/success.html')