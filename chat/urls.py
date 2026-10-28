from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_room, name='chat_room'),

    path('inbox/', views.staff_inbox, name='staff_inbox'),
    path('staff/<int:conv_id>/', views.staff_chat, name='staff_chat'),

    # زر "بدء" — لا ينشئ شيئًا، يفتح موجودة أو يحوّل لغرفة المسودة
    path('start/<int:user_id>/', views.start_internal_conversation, name='start_internal_conversation'),

    # غرفة المسودة + إرسال أول رسالة (لحظة إنشاء المحادثة الفعلية)
    path('new/<int:user_id>/', views.staff_new_chat, name='staff_new_chat'),
    path('new/<int:user_id>/send/', views.send_first_message, name='send_first_message'),

    path('<int:conv_id>/messages/', views.get_messages, name='get_messages'),
    path('<int:conv_id>/send/', views.send_message, name='send_message'),
    path('<int:conv_id>/delete/', views.delete_conversation, name='delete_conversation'),

    path('unread-count/', views.unread_count_api, name='unread_count_api'),
    path('debug/', views.debug_conversations, name='debug_conversations'),
    path('broadcast/', views.broadcast, name='broadcast'),
    path('share/', views.share_qr_view, name='share_qr'),

    # ===== Web Push + PWA (المرحلة 2) =====
    # تسجيل / إلغاء اشتراك الإشعارات من كل جهاز
    path('push/subscribe/', views.push_subscribe, name='push_subscribe'),
    path('push/unsubscribe/', views.push_unsubscribe, name='push_unsubscribe'),

    # Service Worker — يُخدم من /chat/sw.js وترويسته تجعل نطاقه كامل الموقع
    path('sw.js', views.service_worker, name='service_worker'),

    # PWA — مانيفست + بداية ذكية + أيقونات
    path('manifest.webmanifest', views.manifest_view, name='manifest'),
    path('pwa-start/', views.pwa_start, name='pwa_start'),
    path('icon.svg', views.icon_svg, name='icon_svg'),
    path('icon-<int:size>.png', views.icon_png, name='icon_png'),
]