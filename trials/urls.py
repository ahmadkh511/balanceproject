from django.urls import path
from . import views

app_name = 'trials'

urlpatterns = [
    path('request/', views.request_trial, name='request_trial'),
    path('success/', views.trial_success, name='trial_success'),
]