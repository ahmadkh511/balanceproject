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

    def __str__(self):
        return f"{self.user.username} - {self.db_name}"
    
    def save(self, *args, **kwargs):
        if not self.pk:
            self.expiry_date = timezone.now() + timedelta(days=settings.TRIAL_DAYS)
        super().save(*args, **kwargs)