from .middleware import get_current_trial_db

class TrialRouter:
    """
    موجه قواعد البيانات: يوجه استعلامات المستخدم التجريبي لقاعدة بياناته.
    """
    def db_for_read(self, model, **hints):
        trial_db = get_current_trial_db()
        if trial_db:
            # جلسات الدخول (Sessions) وجدول التجارب (Trials) تُقرأ دائماً من القاعدة الرئيسية
            if model._meta.app_label in ['sessions', 'trials']:
                return 'default'
            # باقي الجداول (بما فيها auth.User) تُقرأ من قاعدة بيانات المستخدم المعزولة
            return trial_db
        return 'default'

    def db_for_write(self, model, **hints):
        trial_db = get_current_trial_db()
        if trial_db:
            if model._meta.app_label in ['sessions', 'trials']:
                return 'default'
            return trial_db
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        # السماح بالعلاقات بين الجداول
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True