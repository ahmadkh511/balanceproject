from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

class Trial(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    db_name = models.CharField(max_length=100, unique=True)
    start_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    # الحقول الجديدة من النموذج القديم
    company_name = models.CharField(max_length=200, verbose_name="اسم الشركة")
    full_name = models.CharField(max_length=200, verbose_name="الاسم الكامل")
    email = models.EmailField(verbose_name="البريد الإلكتروني")
    phone_number = models.CharField(max_length=20, verbose_name="رقم الهاتف")
    is_whatsapp = models.BooleanField(default=False, verbose_name="هل الرقم واتساب")
    subscribe_whatsapp = models.BooleanField(default=False, verbose_name="اشتراك واتساب")
    subscribe_email = models.BooleanField(default=False, verbose_name="اشتراك بريدي")
    notes = models.TextField(blank=True, null=True, verbose_name="ملاحظات")

    def __str__(self):
        return f"{self.full_name} - {self.company_name}"
    
    def save(self, *args, **kwargs):
        if not self.pk:
            self.expiry_date = timezone.now() + timedelta(days=settings.TRIAL_DAYS)
        super().save(*args, **kwargs)