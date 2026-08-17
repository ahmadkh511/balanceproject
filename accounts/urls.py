from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views
from django.views.generic import CreateView 
from .forms import CustomUserCreationForm, CustomPasswordResetForm
from django.conf import settings

from . import views
from .views import CustomLoginForm



app_name = 'accounts' 
urlpatterns = [
    

        # تعديل مسار الدخول لدعم النموذج المخصص
        

    path('login/', auth_views.LoginView.as_view(
        template_name='accounts/login.html',
        redirect_authenticated_user=True,
        form_class=CustomLoginForm # <--- إضافة هذا السطر
    ), name='login'),
    


    # إضافة مسار التفعيل الجديد
    path('activate/<uidb64>/<token>/', views.activate_view, name='activate'),


    path('logout/', auth_views.LogoutView.as_view(
        next_page='index'
    ), name='logout'),



    path('register/', views.register_view, name='register'),
    

    # مسارات استعادة كلمة المرور
    path('password_reset/', 
         views.CustomPasswordResetView.as_view(
             template_name='accounts/password_reset_form.html',
             email_template_name='accounts/password_reset_email.html',
             subject_template_name='accounts/password_reset_subject.txt',
             success_url=reverse_lazy('accounts:password_reset_done'),
             html_email_template_name='accounts/password_reset_email.html',
             from_email=settings.DEFAULT_FROM_EMAIL,
             form_class=CustomPasswordResetForm
         ), 
         name='password_reset'),

    path('password_reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='accounts/password_reset_done.html'
         ), 
         name='password_reset_done'),

    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='accounts/password_reset_confirm.html',
             success_url=reverse_lazy('accounts:password_reset_complete'),
             post_reset_login=True,
         ), 
         name='password_reset_confirm'),

    path('reset/done/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='accounts/password_reset_complete.html'
         ), 
         name='password_reset_complete'),

    path('upload-logo/', views.upload_company_logo, name='upload_company_logo'),


    path('terms/', views.TermsView.as_view(), name='terms'),

    path('profile/', views.profile_view, name='profile'),


    

    path('logs/', views.system_logs_view, name='system_logs'),

    path('profile/', views.profile_view, name='profile'),
    
    
    # === مسارات تغيير كلمة المرور (الأسلوب الموصى به) ===
    path('change-password/', 
         auth_views.PasswordChangeView.as_view(
             template_name='accounts/change_password.html',
             success_url=reverse_lazy('accounts:change_password_done')
         ), 
         name='change_password'),

    path('change-password/done/', 
         auth_views.PasswordChangeDoneView.as_view(
             template_name='accounts/change_password_done.html'
         ), 
         name='change_password_done'),



    path('users/', views.user_list_view, name='user_list'),
    path('users/<int:pk>/edit/', views.user_edit_view, name='user_edit'),
    path('permissions/', views.permissions_view, name='permissions'),
    path('api/group-permissions/<int:group_id>/', views.group_permissions_api, name='group_permissions_api'),  # <-- أضف هذا السطر

    path('company-settings/', views.company_settings_view, name='company_settings'),


    path('trial-request/', views.trial_request_view, name='trial_request'),

    


]