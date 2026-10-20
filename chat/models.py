from django.db import models
from django.conf import settings


class Conversation(models.Model):
    KIND_CHOICES = [
        ('customer', 'عميل'),
        ('internal', 'داخلي'),
    ]

    # الطرف "الخارجي" في المحادثة:
    # - في نوع customer: العميل
    # - في نوع internal: الموظف المستقبِل للرسالة (الطرف الآخر)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations_as_customer',
    )
    # الموظف الذي بدأ المحادثة (فقط للنوع internal)
    initiator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='conversations_as_initiator',
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='customer')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_kind_display()}] {self.customer.username}"

class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    content = models.TextField(blank=True, default='')
    attachment = models.FileField(
        upload_to='chat/attachments/%Y/%m/', blank=True, null=True
    )
    attachment_type = models.CharField(max_length=10, blank=True, default='')
    attachment_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        preview = self.content[:30] if self.content else '(مرفق)'
        return f"{self.sender.username}: {preview}"  


class MessageRead(models.Model):
    """
    يسجّل قراءة كل مستخدم لكل رسالة.
    - في محادثات العملاء: كل موظف يفتح المحادثة يُسجَّل هنا
    - في المحادثات الداخلية: كل طرف يسجّل عند فتحه
    - is_read لم يعد حقلاً على Message — بل يُحسب من هذا الجدول لكل مستخدم
    """
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name='read_by'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user')
        ordering = ['-read_at']

    def __str__(self):
        return f"{self.user.username} قرأ رسالة #{self.message_id}"




class BroadcastLog(models.Model):
    """
    سجل الرسائل الجماعية المرسلة من superuser.
    - sender: من أرسل
    - target: الفئة (staff / customers / all)
    - content: نص الرسالة
    - recipients_count: عدد من استلمها
    - conversations_created: عدد المحادثات الجديدة التي أُنشئت
    - created_at: وقت الإرسال
    """
    TARGET_CHOICES = [
        ('staff', 'الموظفون'),
        ('customers', 'العملاء'),
        ('all', 'الجميع'),
    ]

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='broadcast_sent',
    )
    target = models.CharField(max_length=20, choices=TARGET_CHOICES)
    content = models.TextField()
    recipients_count = models.PositiveIntegerField(default=0)
    conversations_created = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return "[{}] {} → {}".format(
            self.get_target_display(),
            self.sender.username,
            self.content[:30],
        )