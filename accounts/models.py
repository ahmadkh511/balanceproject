from django.db import models
from django.contrib.auth.models import User

from django.db import models
from django.contrib.auth.models import User

from django.db import models


# ==========================================
# الخيارات المتكررة (توضع خارج الكلاس لتكون أنظف)
# ==========================================

GENDER_CHOICES = [
    ('M', 'ذكر'),
    ('F', 'أنثى'),
    ('O', 'آخر'),
]

EDUCATION_LEVEL_CHOICES = [
    ('HS', 'ثانوي'),
    ('DIP', 'دبلوم'),
    ('BAC', 'بكالوريوس'),
    ('MAS', 'ماجستير'),
    ('PHD', 'دكتوراه'),
    ('OTH', 'أخرى'),
]


class Profile(models.Model):
    # ==========================================
    # 1. العلاقة الأساسية ونوع المستخدم
    # ==========================================
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        verbose_name="المستخدم",
        related_name="profile" # يسهل الوصول من خلال user.profile
    )
    
    is_customer = models.BooleanField(default=True, verbose_name="زبون")
    is_supplier = models.BooleanField(default=False, verbose_name="مورد")

    # ==========================================
    # 2. الصور والشعارات
    # ==========================================
    logo = models.ImageField(
        upload_to='company_logos/', 
        blank=True, 
        null=True, 
        verbose_name="شعار الشركة"
    )
    
    profile_picture = models.ImageField(
        upload_to='profile_pics/', 
        blank=True, 
        null=True, 
        verbose_name="صورة الملف الشخصي"
    )

    # ==========================================
    # 3. المعلومات الشخصية الأساسية
    # ==========================================
    phone_number = models.CharField(
        max_length=20, 
        blank=True, 
        verbose_name="رقم الهاتف"
    )
    
    birth_date = models.DateField(
        null=True, 
        blank=True, 
        verbose_name="تاريخ الميلاد"
    )
    
    gender = models.CharField(
        max_length=1, 
        choices=GENDER_CHOICES, 
        blank=True, 
        verbose_name="الجنس"
    )
    
    bio = models.TextField(
        max_length=500, 
        blank=True, 
        verbose_name="نبذة شخصية"
    )

    # ==========================================
    # 4. معلومات الاتصال والعنوان
    # ==========================================
    address = models.TextField(
        blank=True, 
        verbose_name="العنوان"
    )
    
    city = models.CharField(
        max_length=50, 
        blank=True, 
        verbose_name="المدينة"
    )
    
    country = models.CharField(
        max_length=50, 
        blank=True, 
        verbose_name="البلد"
    )
    
    postal_code = models.CharField(
        max_length=20, 
        blank=True, 
        verbose_name="الرمز البريدي"
    )
    
    website = models.URLField(
        blank=True, 
        verbose_name="الموقع الإلكتروني"
    )

    # ==========================================
    # 5. حسابات التواصل الاجتماعي
    # ==========================================
    facebook = models.URLField(blank=True, verbose_name="فيسبوك")
    twitter = models.URLField(blank=True, verbose_name="تويتر")
    instagram = models.URLField(blank=True, verbose_name="انستغرام")
    linkedin = models.URLField(blank=True, verbose_name="لينكدإن")

    # ==========================================
    # 6. معلومات العمل والتعليم
    # ==========================================
    job_title = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name="الوظيفة"
    )
    
    company = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name="الشركة"
    )
    
    skills = models.CharField(
        max_length=200, 
        blank=True, 
        verbose_name="المهارات"
    )
    
    experience_years = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        verbose_name="سنوات الخبرة"
    )
    
    education_level = models.CharField(
        max_length=3, 
        choices=EDUCATION_LEVEL_CHOICES, 
        blank=True, 
        verbose_name="مستوى التعليم"
    )
    
    university_major = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name="التخصص الجامعي"
    )
    
    languages = models.CharField(
        max_length=200, 
        blank=True, 
        verbose_name="اللغات"
    )

    # ==========================================
    # 7. الإعدادات
    # ==========================================
    is_public = models.BooleanField(
        default=True, 
        verbose_name="هل الملف الشخصي عام؟"
    )
    
    email_notifications = models.BooleanField(
        default=True, 
        verbose_name="تلقي إشعارات البريد الإلكتروني"
    )

    # ==========================================
    # 8. التواريخ التلقائية
    # ==========================================
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="تاريخ الإنشاء"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True, 
        verbose_name="تاريخ التحديث"
    )

    # ==========================================
    # الدوال والتحويلات النصية
    # ==========================================
    def __str__(self):
        return f'ملف {self.user.username} الشخصي'

    class Meta:
        verbose_name = "الملف الشخصي"
        verbose_name_plural = "الملفات الشخصية"


class CompanySettings(models.Model):
    # ========== الحقول الأساسية ==========
    company_name = models.CharField(max_length=255, default= "أدخل أسم شركتك  ", verbose_name="اسم الشركة")
    company_logo = models.ImageField(upload_to='company_logos/', blank=True, null=True, verbose_name="شعار الشركة")
    
    # ========== معلومات الاتصال ==========
    contact_email = models.EmailField(default="info@example.com", verbose_name="البريد الإلكتروني")
    contact_phone = models.CharField(max_length=20, default="+966 12 345 6789", verbose_name="رقم الهاتف")
    contact_address = models.CharField(max_length=255, default="المملكة العربية السعودية", verbose_name="العنوان")
    
    # ========== روابط التواصل الاجتماعي ==========
    social_facebook = models.URLField(blank=True, null=True, verbose_name="فيسبوك")
    social_twitter = models.URLField(blank=True, null=True, verbose_name="تويتر")
    social_instagram = models.URLField(blank=True, null=True, verbose_name="انستغرام")
    social_linkedin = models.URLField(blank=True, null=True, verbose_name="لينكد إن")
    
    # ========== عناوين أقسام التذييل ==========
    footer_quick_links_title = models.CharField(max_length=100, default="روابط سريعة", verbose_name="عنوان روابط سريعة")
    footer_features_title = models.CharField(max_length=100, default="المميزات", verbose_name="عنوان المميزات")
    footer_contact_title = models.CharField(max_length=100, default="تواصل معنا", verbose_name="عنوان التواصل")
    footer_copyright_text = models.CharField(max_length=255, default="جميع الحقوق محفوظة", verbose_name="نص حقوق النشر")
    
    # ========== روابط سريعة ==========
    quick_link_support = models.URLField(blank=True, null=True, verbose_name="رابط الدعم الفني")
    quick_link_guide = models.URLField(blank=True, null=True, verbose_name="رابط دليل الاستخدام")
    quick_link_faq = models.URLField(blank=True, null=True, verbose_name="رابط الأسئلة الشائعة")
    
    # ========== روابط المميزات ==========
    feature_invoices = models.URLField(blank=True, null=True, verbose_name="رابط إدارة الفواتير")
    feature_inventory = models.URLField(blank=True, null=True, verbose_name="رابط إدارة المخزون")
    feature_reports = models.URLField(blank=True, null=True, verbose_name="رابط التقارير الذكية")
    
    # ==========  إعدادات الواتس أب ==========
    whatsapp_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="رقم الواتساب (مع رمز الدولة، مثال: 966501234567)")
    whatsapp_message = models.CharField(max_length=255, blank=True, null=True, default="مرحباً، أتواصل معكم من المتجر، كيف يمكنكم مساعدتي؟", verbose_name="رسالة واتساب التلقائية")



    # ==========================================
    # إعدادات دمج الفيسبوك (Facebook Integration)
    # ==========================================
    fb_page_id = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        verbose_name="معرف صفحة الفيسبوك (Page ID)",
        help_text="أدخل رقم المعرف الخاص بصفحتك على فيسبوك فقط."
    )
    
    fb_access_token = models.CharField(
        max_length=500, 
        blank=True, 
        null=True, 
        verbose_name="رمز الوصول الدائم (Access Token)",
        help_text="أدخل الرمز الذي تحصل عليه من موقع مطوري فيسبوك (Developers Facebook). تنبيه: هذا الرمز سري، لا تشاركه مع أحد."
    )

    # ========== حقول إضافية ==========
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    
    class Meta:
        verbose_name = "إعدادات الشركة"
        verbose_name_plural = "إعدادات الشركة"

    def __str__(self):
        return f"إعدادات الشركة - آخر تحديث: {self.updated_at}"

    def save(self, *args, **kwargs):
        """تجاوز دالة الحفظ لمسح الكاش قبل الحفظ مباشرة"""
        from django.core.cache import cache
        cache.delete('company_settings')
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        """جلب إعدادات الشركة مع الكاش لتحسين الأداء"""
        from django.core.cache import cache
        settings = cache.get('company_settings')
        if not settings:
            settings, created = cls.objects.get_or_create(id=1)
            cache.set('company_settings', settings, 60 * 60)
        return settings





class TrialRequest(models.Model):
    # خيارات حالة الطلب
    STATUS_CHOICES = (
        ('new', 'طلب جديد'),
        ('contacted', 'تم التواصل'),
        ('activated', 'مُفعّل'),
        ('rejected', 'مرفوض'),
    )

    full_name = models.CharField(max_length=100, verbose_name="الاسم الكامل")
    company_name = models.CharField(max_length=200, verbose_name="اسم الشركة")
    phone_number = models.CharField(max_length=20, verbose_name="رقم الموبايل")
    is_whatsapp = models.BooleanField(default=False, verbose_name="هل الرقم واتساب؟")
    email = models.EmailField(verbose_name="البريد الإلكتروني")
    subscribe_whatsapp = models.BooleanField(default=False, verbose_name="الاشتراك بنشرة الواتساب")
    subscribe_email = models.BooleanField(default=False, verbose_name="الاشتراك بنشرة الإيميل")
    
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='new', 
        verbose_name="حالة الطلب"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الطلب")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    notes = models.TextField(blank=True, null=True)  

    class Meta:
        verbose_name = "طلب تجريبي"
        verbose_name_plural = "الطلبات التجريبية"
        ordering = ['-created_at'] # ترتيب الأحدث أولاً

    def __str__(self):
        return f"{self.full_name} - {self.company_name} ({self.get_status_display()})"
    

