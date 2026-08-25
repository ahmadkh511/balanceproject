from django.urls import path
from . import views

app_name = 'trials'

urlpatterns = [
    path('request/', views.request_trial, name='request_trial'),
    path('success/', views.trial_success, name='trial_success'),
    path('manage/', views.manage_trials, name='manage_trials'),
    path('manage/stop/<int:trial_id>/', views.stop_trial, name='stop_trial'),
    path('manage/delete/<int:trial_id>/', views.delete_trial, name='delete_trial'),
]