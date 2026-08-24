import uuid
import copy
from django.conf import settings
from django.db import connection
from django.contrib.auth.models import User
from django.core.management import call_command
from .models import Trial

def provision_trial_database(username, email, password):
    """
    هذه الدالة تقوم بإنشاء قاعدة بيانات معزولة للمستخدم التجريبي
    """
    # 1. توليد اسم عشوائي وفريد لقاعدة البيانات
    db_name = f"trial_{uuid.uuid4().hex[:10]}"
    
    # 2. إنشاء قاعدة البيانات في MySQL
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;")
    
    # 3. نسخ إعدادات قاعدة البيانات الرئيسية وتغيير الاسم فقط
    if db_name not in settings.DATABASES:
        default_db = copy.deepcopy(settings.DATABASES['default'])
        default_db['NAME'] = db_name
        settings.DATABASES[db_name] = default_db
    
    # 4. إنشاء الجداول داخل قاعدة البيانات الجديدة
    call_command('migrate', database=db_name, interactive=False)
    
    # 5. إنشاء المستخدم في القاعدة الرئيسية (ليتمكن من تسجيل الدخول)
    user = User.objects.create_user(username=username, email=email, password=password)
    
    # 6. إنشاء نفس المستخدم في قاعدة البيانات المعزولة بنفس الـ ID
    trial_user = User(id=user.id, username=user.username, email=user.email, password=user.password, is_staff=True, is_superuser=True)
    trial_user.save(using=db_name)
    
    # 7. تسجيل المستخدم في جدول التجارب في القاعدة الرئيسية
    Trial.objects.using('default').create(user=user, db_name=db_name)
    
    return user, db_name