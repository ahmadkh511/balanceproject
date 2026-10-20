from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_room, name='chat_room'),
    path('<int:conv_id>/messages/', views.get_messages, name='get_messages'),
    path('<int:conv_id>/send/', views.send_message, name='send_message'),
    path('inbox/', views.staff_inbox, name='staff_inbox'),
    path('staff/<int:conv_id>/', views.staff_chat, name='staff_chat'),
    path('<int:conv_id>/delete/', views.delete_conversation, name='delete_conversation'),
    # ✅ جديد: بدء محادثة داخلية
    path('start/<int:user_id>/', views.start_internal_conversation, name='start_internal_conversation'),

    path('unread-count/', views.unread_count_api, name='unread_count_api'),



    path('debug/', views.debug_conversations, name='debug_conversations'),

    path('broadcast/', views.broadcast, name='broadcast'),
]