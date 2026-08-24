import threading

thread_local = threading.local()

def get_current_trial_db():
    # قراءة قاعدة البيانات المخزنة من الميدلوير
    return getattr(thread_local, 'trial_db', None)

class TrialRouter:
    """
    موجه قواعد البيانات: يوجه استعلامات المستخدم التجريبي لقاعدة بياناته.
    """
    def db_for_read(self, model, **hints):
        trial_db = get_current_trial_db()
        # إذا كان المستخدم تجريبياً، الجلسات (Sessions) تُقرأ من القاعدة الرئيسية
        if trial_db:
            if model._meta.app_label in ['sessions', 'trials', 'admin']:
                return 'default'
            return trial_db
        return 'default'

    def db_for_write(self, model, **hints):
        trial_db = get_current_trial_db()
        if trial_db:
            if model._meta.app_label in ['sessions', 'trials', 'admin']:
                return 'default'
            return trial_db
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        # السماح بالعلاقات بين الجداول
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True