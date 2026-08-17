# accounts/signals.py

from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import Profile

@receiver(post_save, sender=User)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    """
    ينشئ ملفاً شخصياً عند إنشاء مستخدم جديد، أو يحفظ الملف الشخصي الموجود.
    هذه الدالة آمنة وتستخدم get_or_create لمنع الأخطاء.
    """
  
    profile, created = Profile.objects.get_or_create(user=instance)