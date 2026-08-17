# balanceIQ/context_processors.py
import secrets
import hashlib
import time
from django.utils.crypto import get_random_string


def csp_nonce(request):
    """
    تمرير الـ Nonce الخاص بأمان CSP إلى جميع قوالب HTML
    """
    # محاولة جلب nonce من الطلب (إذا تم تعيينه مسبقاً)
    nonce = getattr(request, 'csp_nonce', None)
    
    # إذا لم يكن موجوداً، قم بإنشاء nonce جديد
    if not nonce:
        # طريقة آمنة لإنشاء nonce
        nonce = secrets.token_urlsafe(32)  # 32 بايت = 256 بت
        
        # تخزينه في الطلب لاستخدامه لاحقاً
        request.csp_nonce = nonce
    
    return {'csp_nonce': nonce}


def csp_nonce_secure(request):
    """
    تمرير Nonce آمن مع توقيت لتحديثه تلقائياً
    """
    # جلب nonce من الجلسة أو إنشاء جديد
    nonce = request.session.get('csp_nonce')
    nonce_created = request.session.get('csp_nonce_created', 0)
    
    # تجديد nonce كل ساعة (لزيادة الأمان)
    if not nonce or (time.time() - nonce_created) > 3600:
        # إنشاء nonce جديد باستخدام hashlib و secrets
        random_bytes = secrets.token_bytes(32)
        nonce = hashlib.sha256(random_bytes).hexdigest()[:32]
        
        # تخزين في الجلسة
        request.session['csp_nonce'] = nonce
        request.session['csp_nonce_created'] = int(time.time())
    
    return {'csp_nonce': nonce}


# ✅ اختر الدالة المناسبة:
# - csp_nonce: بسيطة وآمنة (موصى بها)
# - csp_nonce_secure: أكثر أماناً مع تجديد تلقائي