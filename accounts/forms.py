# ==================== مكتبات بايثون القياسية ====================
import re
from urllib.parse import urlparse

# ==================== إطار عمل Django الأساسي ====================
from django import forms
from django.contrib.auth.forms import PasswordResetForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError

# ==================== النماذج المحلية (Models) ====================
from .models import Profile


from django import forms
from .models import TrialRequest



from django import forms
from django.contrib.auth.models import User
from urllib.parse import urlparse
from django.core.exceptions import ValidationError
from .models import Profile



from django import forms
from django.contrib.auth.models import User
from urllib.parse import urlparse
from django.core.exceptions import ValidationError
from .models import Profile


from .models import CompanySettings






class CustomUserCreationForm(UserCreationForm):
    # إضافة حقل الاسم الكامل
    full_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'auth-input',
            'placeholder': 'أدخل اسمك الكامل'
        })
    )
    
    username = forms.CharField(
        max_length=150,
        required=True,
        validators=[UnicodeUsernameValidator()], # السماح بالأحرف العربية
        widget=forms.TextInput(attrs={
            'class': 'auth-input',
            'placeholder': 'اسم المستخدم (يسمح بالعربية والإنجليزية)'
        }),
        help_text="مطلوب. 150 حرفاً أو أقل. أحرف، أرقام، و @/./+/-/_ فقط."
    )

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'auth-input',
            'placeholder': 'البريد الإلكتروني'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'full_name', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget = forms.PasswordInput(attrs={
            'class': 'auth-input',
            'placeholder': 'كلمة المرور',
            'style': 'padding-left: 2.8rem;'
        })
        self.fields['password2'].widget = forms.PasswordInput(attrs={
            'class': 'auth-input',
            'placeholder': 'تأكيد كلمة المرور',
            'style': 'padding-left: 2.8rem;'
        })

    def clean_username(self):
        username = self.cleaned_data.get('username')
        # منع المسافات في اسم المستخدم (لأنها تسبب مشاكل في تسجيل الدخول)
        if ' ' in username:
            raise forms.ValidationError("اسم المستخدم لا يمكن أن يحتوي على مسافات.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("هذا البريد الإلكتروني مسجل بالفعل. يرجى استخدام بريد إلكتروني آخر.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data.get('full_name')
        user.first_name = full_name # حفظ الاسم الكامل في first_name
        if commit:
            user.save()
        return user




class TrialRequestForm(forms.ModelForm):
    # حقول الشروط (Checkboxes)
    is_whatsapp = forms.BooleanField(
        required=False, 
        label="هل هذا الرقم واتساب؟",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    subscribe_whatsapp = forms.BooleanField(
        required=False, 
        label="أوافق على الاشتراك بنشرة الواتساب",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    subscribe_email = forms.BooleanField(
        required=False, 
        label="أوافق على الاشتراك بنشرة البريد الإلكتروني",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = TrialRequest
        fields = ['full_name', 'company_name', 'phone_number', 'is_whatsapp', 'email', 'subscribe_whatsapp', 'subscribe_email' , 'notes']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'auth-input', 
                'placeholder': 'أدخل اسمك الكامل',
                'id': 'trial_fullname'
            }),
            'company_name': forms.TextInput(attrs={
                'class': 'auth-input', 
                'placeholder': 'أدخل اسم الشركة',
                'id': 'trial_company'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'auth-input', 
                'placeholder': 'رقم الموبايل مع كود الدولة',
                'id': 'trial_phone' # هذا الـ ID سنتعامل معه لاحقاً بمكتبة الأعلام
            }),
            'email': forms.EmailInput(attrs={
                'class': 'auth-input', 
                'placeholder': 'أدخل بريدك الإلكتروني',
                'id': 'trial_email'
            }),
        }

    # تحقق إضافي: منع تسجيل طلب تجريبي متكرر بنفس الإيميل وهو بحالة "جديد"
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if TrialRequest.objects.filter(email__iexact=email, status='new').exists():
            raise forms.ValidationError("لديك طلب تجريبي قيد المراجعة بالفعل على هذا البريد الإلكتروني.")
        return email




# ==========================================
# 1. نموذج تحديث بيانات Django User المدمج
# (يُستخدم من قبل الموظفين Admin لتعديل بيانات الحساب والصلاحيات)
# ==========================================
class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الأول'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الأخير'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'username': 'اسم المستخدم',
            'email': 'البريد الإلكتروني',
            'first_name': 'الاسم الأول',
            'last_name': 'الاسم الأخير',
            'is_active': 'حساب نشط',
            'is_staff': 'موظف (صلاحيات إدارية)',
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        username = self.cleaned_data.get('username')
        if email and User.objects.filter(email__iexact=email).exclude(username=username).exists():
            raise forms.ValidationError("هذا البريد الإلكتروني مستخدم من قبل مستخدم آخر.")
        return email


# ==========================================
# 2. نموذج تحديث بيانات Profile
# (يُستخدم للمستخدم العادي لتعديل بريفاه، والموظف لتعديل بقية البيانات)
# ==========================================
class UserProfileUpdateForm(forms.ModelForm):
    # --- حقول إضافية من نموذج User (لأننا أزلنا full_name من Profile) ---
    first_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الأول'}),
        label='الاسم الأول'
    )
    last_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الأخير'}),
        label='الاسم الأخير'
    )

    # --- حقل وهمي لمعالجة الرابط ---
    website_display = forms.CharField(
        label="الموقع الإلكتروني",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'مثال: google.com أو city.com'
        })
    )

    class Meta:
        model = Profile
        fields = [
            # تم إزالة full_name و user_type
            'is_customer', 'is_supplier', 'profile_picture', 'phone_number', 'birth_date', 'gender',
            'address', 'city', 'country', 'postal_code', 'bio', 
            'facebook', 'twitter', 'instagram', 'linkedin', 'skills', 
            'job_title', 'company', 'experience_years', 'education_level',
            'university_major', 'languages', 'is_public', 'email_notifications',
        ]
        widgets = {
            'is_customer': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_supplier': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الهاتف'}),
            'birth_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'العنوان'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'المدينة'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'البلد'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الرمز البريدي'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'نبذة شخصية'}),
            'facebook': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'رابط فيسبوك'}),
            'twitter': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'رابط تويتر'}),
            'instagram': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'رابط انستغرام'}),
            'linkedin': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'رابط لينكدإن'}),
            'skills': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'المهارات (افصل بينها بفاصلة)'}),
            'job_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الوظيفة'}),
            'company': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الشركة'}),
            'experience_years': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': 'سنوات الخبرة'}),
            'education_level': forms.Select(attrs={'class': 'form-select'}),
            'university_major': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'التخصص الجامعي'}),
            'languages': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اللغات (افصل بينها بفاصلة)'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email_notifications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, is_admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        
        # ==========================================
        # ذكاء الفورم: تعديل الحقول بناءً على من يفتح الصفحة
        # ==========================================
        if not is_admin:
            # إذا كان المستخدم العادي: إخفاء خيارات (زبون/مورد)
            self.fields.pop('is_customer', None)
            self.fields.pop('is_supplier', None)
        else:
            # إذا كان الادمن: إخفاء حقول الاسم (لأنها موجودة في UserUpdateForm لتجنب التضارب)
            self.fields.pop('first_name', None)
            self.fields.pop('last_name', None)

        if self.instance and self.instance.pk:
            # تعبئة حقول الاسم من نموذج User المرتبط بالبروفايل
            if self.instance.user and 'first_name' in self.fields:
                self.fields['first_name'].initial = self.instance.user.first_name
                self.fields['last_name'].initial = self.instance.user.last_name
            
            # تعبئة حقل الموقع الإلكتروني المخصص (بعد إزالة https://)
            if self.instance.website:
                self.fields['website_display'].initial = self.instance.website.replace('https://', '').replace('http://', '')

    def clean_website_display(self):
        """التحقق من صحة الرابط المدخل"""
        website = self.cleaned_data.get('website_display', '').strip()
        if not website:
            return ''
        
        test_url = 'https://' + website if not website.startswith(('http://', 'https://')) else website
        try:
            parsed = urlparse(test_url)
            if not parsed.netloc or ' ' in website:
                raise ValidationError('الرجاء إدخال رابط موقع إلكتروني صالح، مثل example.com')
        except ValueError:
            raise ValidationError('الرجاء إدخال رابط موقع إلكتروني صالح.')
        return website

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # 1. تحديث الاسم في نموذج User المدمج (فقط إذا كانت الحقول موجودة، أي للمستخدم العادي)
        if 'first_name' in self.fields:
            user = instance.user
            user.first_name = self.cleaned_data.get('first_name', '')
            user.last_name = self.cleaned_data.get('last_name', '')
            if commit:
                user.save()
        
        # 2. معالجة الرابط وحفظه في نموذج Profile
        website_val = self.cleaned_data.get('website_display', '').strip()
        if website_val:
            instance.website = 'https://' + website_val if not website_val.startswith('http') else website_val
        else:
            instance.website = ''
        
        # 3. الحفظ النهائي
        if commit:
            instance.save()
            
        return instance








class CustomPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        label="البريد الإلكتروني",
        max_length=254,
        widget=forms.EmailInput(attrs={
            'autocomplete': 'email',
            'class': 'form-control',
            'placeholder': 'البريد الإلكتروني'
        })
    )
    
    def clean_email(self):
        email = self.cleaned_data['email']
        if not User.objects.filter(email__iexact=email, is_active=True).exists():
            raise ValidationError("لا يوجد حساب مسجل بهذا البريد الإلكتروني.")
        return email

        







class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = '__all__'
        widgets = {
            # الحقول الموجودة سابقاً
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'company_logo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_address': forms.TextInput(attrs={'class': 'form-control'}),
            'social_facebook': forms.URLInput(attrs={'class': 'form-control'}),
            'social_twitter': forms.URLInput(attrs={'class': 'form-control'}),
            'social_instagram': forms.URLInput(attrs={'class': 'form-control'}),
            'social_linkedin': forms.URLInput(attrs={'class': 'form-control'}),
            'footer_quick_links_title': forms.TextInput(attrs={'class': 'form-control'}),
            'footer_features_title': forms.TextInput(attrs={'class': 'form-control'}),
            'footer_contact_title': forms.TextInput(attrs={'class': 'form-control'}),
            'footer_copyright_text': forms.TextInput(attrs={'class': 'form-control'}),
            
            # ========== الحقول الجديدة (روابط سريعة) ==========
            'quick_link_support': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/support'}),
            'quick_link_guide': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/guide'}),
            'quick_link_faq': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/faq'}),
            
            # ========== الحقول الجديدة (روابط المميزات) ==========
            'feature_invoices': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/invoices'}),
            'feature_inventory': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/inventory'}),
            'feature_reports': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/reports'}),
            
            # ========== الحقول الجديدة (واتساب الدعم الفني) ==========
            'whatsapp_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '966501234567'}),
            'whatsapp_message': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مرحباً، أتواصل معكم من المتجر، كيف يمكنكم مساعدتي؟'}),
            
            # ========== الحقول الجديدة (دمج الفيسبوك) ==========
            'fb_page_id': forms.TextInput(attrs={'class': 'form-control', 'dir': 'ltr', 'placeholder': 'مثال: 123456789012345'}),
            'fb_access_token': forms.TextInput(attrs={'class': 'form-control', 'dir': 'ltr', 'placeholder': 'مثال: EAAxxxxxxxxxxxxx...'}),
        }
        labels = {
            # الحقول الموجودة سابقاً
            'company_name': 'اسم الشركة',
            'company_logo': 'شعار الشركة',
            'contact_email': 'البريد الإلكتروني',
            'contact_phone': 'رقم الهاتف',
            'contact_address': 'العنوان',
            'social_facebook': 'فيسبوك',
            'social_twitter': 'تويتر',
            'social_instagram': 'انستغرام',
            'social_linkedin': 'لينكد إن',
            'footer_quick_links_title': 'عنوان روابط سريعة',
            'footer_features_title': 'عنوان المميزات',
            'footer_contact_title': 'عنوان التواصل',
            'footer_copyright_text': 'نص حقوق النشر',
            
            # الحقول الجديدة (روابط)
            'quick_link_support': 'رابط الدعم الفني',
            'quick_link_guide': 'رابط دليل الاستخدام',
            'quick_link_faq': 'رابط الأسئلة الشائعة',
            'feature_invoices': 'رابط إدارة الفواتير',
            'feature_inventory': 'رابط إدارة المخزون',
            'feature_reports': 'رابط التقارير الذكية',
            
            # الحقول الجديدة (واتساب)
            'whatsapp_number': 'رقم الواتساب (مع رمز الدولة)',
            'whatsapp_message': 'رسالة واتساب التلقائية',
            
            # الحقول الجديدة (فيسبوك)
            'fb_page_id': 'معرف صفحة الفيسبوك (Page ID)',
            'fb_access_token': 'رمز الوصول لفيسبوك (Access Token)',
        }