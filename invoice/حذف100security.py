# من اجل كلمة سر نظام التسعير 

import hashlib
import os
import logging

from django.conf import settings as django_settings

logger = logging.getLogger(__name__)


def hash_pricing_password(password):
    """تشفير كلمة مرور التسعير بـ SHA-256"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def get_stored_pricing_password_hash():
    """
    جلب الهاش المخزن لكلمة مرور التسعير
    الأولوية: قاعدة البيانات ← ثم .env
    """
    from invoice.models import PricingSetting
    
    settings_obj = PricingSetting.get_settings()
    
    # إذا كانت هناك كلمة مرور مخصصة في قاعدة البيانات
    if settings_obj.pricing_password:
        return settings_obj.pricing_password
    
    # ارجع لتشفير القيمة من .env
    env_password = getattr(django_settings, 'PRICING_PASSWORD', '')
    if env_password:
        return hash_pricing_password(env_password)
    
    return None


def verify_pricing_password(password):
    """التحقق من كلمة مرور التسعير"""
    stored_hash = get_stored_pricing_password_hash()
    
    if not stored_hash:
        logger.error("كلمة مرور التسعير غير معرّفة! لا يوجد في قاعدة البيانات ولا في .env")
        return False
    
    return hash_pricing_password(password) == stored_hash


def is_custom_password_set():
    """هل تم تعيين كلمة مرور مخصصة في قاعدة البيانات؟"""
    from invoice.models import PricingSetting
    return bool(PricingSetting.get_settings().pricing_password)