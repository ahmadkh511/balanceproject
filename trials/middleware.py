import copy
import threading
from django.conf import settings
from .models import Trial

thread_local = threading.local()

def get_current_trial_db():
    # دالة مساعدة ليقرأ منها الـ Router
    return getattr(thread_local, 'trial_db', None)

class TrialMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # تهيئة المتغير
        thread_local.trial_db = None
        
        # جلب معرف المستخدم مباشرة من الجلسة (Session)
        user_id = request.session.get('_auth_user_id')
        if user_id:
            try:
                # البحث عن اشتراك المستخدم التجريبي في القاعدة الرئيسية
                trial = Trial.objects.using('default').get(user_id=user_id, is_active=True)
                
                # تسجيل قاعدة البيانات المعزولة في إعدادات Django
                if trial.db_name not in settings.DATABASES:
                    default_db = copy.deepcopy(settings.DATABASES['default'])
                    default_db['NAME'] = trial.db_name
                    settings.DATABASES[trial.db_name] = default_db

                # تخزين اسم قاعدة البيانات للطلب الحالي
                thread_local.trial_db = trial.db_name
            except Trial.DoesNotExist:
                pass
        
        response = self.get_response(request)
        return response