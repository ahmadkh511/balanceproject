from django.contrib import admin
from django.urls import path, include
from accounts import views as accounts_views

import os
from django.core.management import call_command

import os
from django.core.management import call_command
from django.contrib.auth import get_user_model


from accounts.views import user_manual # استدعاء الدالة من تطبيق accounts

from django.views.static import serve
from django.conf import settings
import os


# إنشاء الجداول والمستخدم تلقائياً على السيرفر
if os.environ.get('RENDER'):
    if not os.path.exists('db.sqlite3'):
        call_command('migrate', '--run-syncdb')
        
        # إنشاء المستخدم مع كلمة مرور صريحة
        User = get_user_model()
        if not User.objects.filter(username='admin').exists():
            user = User.objects.create_superuser(username='admin', email='admin@admin.com', password='Admin@123456')






urlpatterns = [

    # لفتح الصفحة الرئيسية للدليل
    path('docs/', serve, {
        'path': 'index.html', 
        'document_root': os.path.join(settings.BASE_DIR, 'site'),
    }),
    # لفتح باقي الصفحات والملفات (CSS/JS)
    path('docs/<path:path>', serve, {
        'document_root': os.path.join(settings.BASE_DIR, 'site'),
    }),




    path('admin/', admin.site.urls),
    path('', accounts_views.index, name='index'),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('invoice/', include('invoice.urls')),

    path('docs/', user_manual, name='user_manual'),
    path('trials/', include('trials.urls')),
]

# 🔥 التعديل النهائي - الطريقة الموصى بها
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=None)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)