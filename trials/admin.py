from django.contrib import admin
from django.utils import timezone
from .models import Trial

@admin.register(Trial)
class TrialAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 
        'company_name', 
        'email', 
        'db_name', 
        'start_date', 
        'expiry_date', 
        'days_remaining',
        'is_active',
        'is_expired'
    )
    list_filter = ('is_active', 'expiry_date')
    search_fields = ('full_name', 'company_name', 'email', 'db_name')
    readonly_fields = ('db_name', 'start_date', 'days_remaining', 'is_expired')
    
    fieldsets = (
        ('معلومات العميل', {
            'fields': ('user', 'full_name', 'company_name', 'email', 'phone_number')
        }),
        ('حالة التجربة', {
            'fields': ('is_active', 'start_date', 'expiry_date', 'days_remaining', 'is_expired')
        }),
        ('قاعدة البيانات المعزولة', {
            'fields': ('db_name',),
            'description': 'اسم قاعدة البيانات الخاصة بهذا العميل (يُستخدم للدعم الفني)'
        }),
        ('تفضيلات العميل', {
            'fields': ('is_whatsapp', 'subscribe_whatsapp', 'subscribe_email', 'notes'),
            'classes': ('collapse',) # يمكن طيها وفتحها
        }),
    )

    def days_remaining(self, obj):
        if obj.expiry_date > timezone.now():
            delta = obj.expiry_date - timezone.now()
            return f"{delta.days} يوم و {delta.seconds // 3600} ساعة"
        return "انتهت"
    days_remaining.short_description = "الوقت المتبقي"

    def is_expired(self, obj):
        return obj.expiry_date < timezone.now()
    is_expired.boolean = True
    is_expired.short_description = "منتهي؟"