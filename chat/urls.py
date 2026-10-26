from django.urls import path
from . import views
urlpatterns = [
    path('', views.chat_room, name='chat_room'),

    path('inbox/', views.staff_inbox, name='staff_inbox'),
    path('staff/<int:conv_id>/', views.staff_chat, name='staff_chat'),

    # زر "بدء" — لا ينشئ شيئًا، يفتح موجودة أو يحوّل لغرفة المسودة
    path('start/<int:user_id>/', views.start_internal_conversation, name='start_internal_conversation'),

    # ✅ جديد: غرفة المسودة + إرسال أول رسالة (لحظة إنشاء المحادثة الفعلية)
    path('new/<int:user_id>/', views.staff_new_chat, name='staff_new_chat'),
    path('new/<int:user_id>/send/', views.send_first_message, name='send_first_message'),

    path('<int:conv_id>/messages/', views.get_messages, name='get_messages'),
    path('<int:conv_id>/send/', views.send_message, name='send_message'),
    path('<int:conv_id>/delete/', views.delete_conversation, name='delete_conversation'),

    path('unread-count/', views.unread_count_api, name='unread_count_api'),
    path('debug/', views.debug_conversations, name='debug_conversations'),
    path('broadcast/', views.broadcast, name='broadcast'),
    path('share/', views.share_qr_view, name='share_qr'),
]