from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Profile

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'has_logo', 'profile_picture')
    list_filter = ('user',)
    search_fields = ('user__username',)
    
   
    def has_logo(self, obj):
        return "✅" if obj.logo else "❌"
    has_logo.short_description = "يوجد شعار"
    
  
    fieldsets = (
        ('معلومات المستخدم', {
            'fields': ('user', 'profile_picture')
        }),
    )
    
  
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
       
            fieldsets = list(fieldsets)
            fieldsets.append(('شعار الشركة', {
                'fields': ('logo',),
                'classes': ('collapse',),
                'description': 'هذا الحقل متاح فقط للمشرفين الرئيسيين'
            }))
        return tuple(fieldsets)
    
    
    def save_model(self, request, obj, form, change):
     
        if not request.user.is_superuser and 'logo' in form.changed_data:
        
            if obj.pk:
                original = Profile.objects.get(pk=obj.pk)
                obj.logo = original.logo
        super().save_model(request, obj, form, change)


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'الملف الشخصي'
    extra = 0  
    
    def get_fields(self, request, obj=None):
        
        fields = ['profile_picture']
        if request.user.is_superuser:
            fields.append('logo')
        return fields

class CustomUserAdmin(UserAdmin):
    inlines = (ProfileInline,)


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

