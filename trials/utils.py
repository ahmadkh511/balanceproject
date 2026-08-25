import uuid
import copy
import secrets
import re
from django.conf import settings
from django.db import connection
from django.contrib.auth.models import User
from django.core.management import call_command
from .models import Trial

def provision_trial_database(form_data):
    """
    تقوم بإنشاء قاعدة بيانات معزولة ومستخدم تجريبي بناءً على بيانات النموذج
    """
    # 1. توليد اسم قاعدة البيانات بناءً على اسم المستخدم (البريد)
    base_name = form_data['email'].split('@')[0]
    # إزالة أي رموز غير مسموح بها في اسم قاعدة البيانات وتحويلها لاحرف صغيرة
    clean_name = re.sub(r'[^a-zA-Z0-9_]', '', base_name).lower()
    db_name = f"trial_{clean_name}_{uuid.uuid4().hex[:4]}"  # مثال: trial_ahmed_a1b2
    generated_password = secrets.token_urlsafe(8)
    
    # 2. إنشاء قاعدة البيانات في MySQL
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;")
    
    # 3. نسخ إعدادات قاعدة البيانات الرئيسية
    if db_name not in settings.DATABASES:
        default_db = copy.deepcopy(settings.DATABASES['default'])
        default_db['NAME'] = db_name
        settings.DATABASES[db_name] = default_db
    
    # 4. إنشاء الجداول داخل قاعدة البيانات الجديدة
    call_command('migrate', database=db_name, interactive=False)
    
    # 5. إنشاء المستخدم في القاعدة الرئيسية (ليتمكن من تسجيل الدخول للموقع)
    user = User.objects.create_user(
        username=form_data['email'], 
        email=form_data['email'], 
        password=generated_password
    )
    
    # 6. إدخال المستخدم في قاعدة البيانات المعزولة كـ Superuser بنفس الـ ID
    # نستخدم bulk_create لتسجيله مباشرة وتجنب أي مشاكل في الإشارات (Signals)
    trial_user = User(
        id=user.id,
        username=user.username,
        email=user.email,
        password=user.password, # كلمة المرور مشفرة بالفعل من القاعدة الرئيسية
        is_staff=True,
        is_superuser=True,
        is_active=True,
        date_joined=user.date_joined
    )
    User.objects.using(db_name).bulk_create([trial_user])
    
    # 7. إنشاء الملف الشخصي (Profile) وإعدادات الشركة (CompanySettings) في القاعدة المعزولة
    # هذا مهم جداً لكي لا ينهار النظام (خطأ 500) عند بحث القوالب عن user.profile
    try:
        from accounts.models import Profile, CompanySettings
        Profile.objects.using(db_name).create(user_id=user.id)
        CompanySettings.objects.using(db_name).create(company_name=form_data['company_name'])
    except Exception as e:
        print(f"Trial Setup Warning (Profile/CompanySettings): {e}")

    # 8. تسجيل بيانات التجربة في القاعدة الرئيسية
    Trial.objects.using('default').create(
        user=user,
        db_name=db_name,
        company_name=form_data['company_name'],
        full_name=form_data['full_name'],
        email=form_data['email'],
        phone_number=form_data['phone_number'],
        is_whatsapp=form_data.get('is_whatsapp', False),
        subscribe_whatsapp=form_data.get('subscribe_whatsapp', False),
        subscribe_email=form_data.get('subscribe_email', False),
        notes=form_data.get('notes', '')
    )
    
    return user, generated_password, db_name