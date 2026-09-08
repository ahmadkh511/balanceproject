import copy
import threading
from django.conf import settings
from django.contrib.auth.models import User # ضروري لجلب بيانات الموظف
from .models import Trial

thread_local = threading.local()

def get_current_trial_db():
    return getattr(thread_local, 'trial_db', None)

class TrialMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        thread_local.trial_db = None
        
        user_id = request.session.get('_auth_user_id')
        if user_id:
            try:
                # جلب المستخدم من القاعدة الرئيسية
                user = User.objects.using('default').get(id=user_id)
                
                # التحقق إذا كان لديه ملف شخصي مرتبط بقاعدة بيانات تجريبية
                if hasattr(user, 'profile') and user.profile.trial_db_name:
                    db_name = user.profile.trial_db_name
                    
                    if db_name not in settings.DATABASES:
                        default_db = copy.deepcopy(settings.DATABASES['default'])
                        default_db['NAME'] = db_name
                        settings.DATABASES[db_name] = default_db

                    thread_local.trial_db = db_name
                # إذا لم يكن لديه trial_db_name، نتحقق إذا كان صاحب شركة تجريبية (النظام القديم للتوافق)
                elif Trial.objects.using('default').filter(user_id=user_id, is_active=True).exists():
                    trial = Trial.objects.using('default').get(user_id=user_id, is_active=True)
                    db_name = trial.db_name
                    if db_name not in settings.DATABASES:
                        default_db = copy.deepcopy(settings.DATABASES['default'])
                        default_db['NAME'] = db_name
                        settings.DATABASES[db_name] = default_db
                    thread_local.trial_db = db_name

            except User.DoesNotExist:
                pass
        
        response = self.get_response(request)
        return response