from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import connection
from trials.models import Trial

class Command(BaseCommand):
    help = 'يقوم بحذف قواعد بيانات المستخدمين التجريبيين الذين انتهت فترتهم وتعطيل حساباتهم.'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        
        # البحث عن جميع التجارب المنتهية وغير المحذوفة
        expired_trials = Trial.objects.filter(expiry_date__lt=now, is_active=True)

        if not expired_trials.exists():
            self.stdout.write(self.style.SUCCESS('لا يوجد فترات تجريبية منتهية حالياً. كل شيء بخير.'))
            return

        count = 0
        for trial in expired_trials:
            db_name = trial.db_name
            try:
                # 1. حذف قاعدة البيانات المعزولة من MySQL
                with connection.cursor() as cursor:
                    cursor.execute(f"DROP DATABASE IF EXISTS `{db_name}`;")
                
                # 2. تعطيل المستخدم في القاعدة الرئيسية (لكي لا يستطيع الدخول مرة أخرى)
                user = trial.user
                user.is_active = False
                user.save()

                # 3. تحديث حالة التجربة إلى "غير نشطة" في جدول التجارب
                trial.is_active = False
                trial.save()

                self.stdout.write(self.style.WARNING(f'تم حذف قاعدة البيانات: {db_name} وتعطيل المستخدم: {user.username}'))
                count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'حدث خطأ أثناء حذف {db_name}: {str(e)}'))

        self.stdout.write(self.style.SUCCESS(f'اكتمل التنظيف. تم حذف {count} قاعدة بيانات تجريبية منتهية.'))