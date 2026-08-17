import secrets

class CustomCSPMiddleware:
    """
    سياسة أمان المحتوى (CSP) المتوافقة مع معايير A+
    تعتمد على تقنية الـ Nonce للسماح بالسكربتات الداخلية بأمان تام
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. توليد كلمة مرور عشوائية فريدة لكل طلب صفحة (Nonce)
        nonce = secrets.token_urlsafe(16)
        
        # 2. حفظها في الـ request لتصل للقوالب عبر context_processor
        request.csp_nonce = nonce
        
        # 3. تنفيذ باقي العمليات والحصول على الـ Response
        response = self.get_response(request)
        
        # 4. بناء سياسة CSP النهائية (ملاحظة: حرف f ضروري جداً قبل كل سطر)
        csp_policy = (
            f"default-src 'self'; "
            
            # السماح بالسكربتات التي تمتلك الـ Nonce الصحيح فقط + مكتبات CDN
            f"script-src 'self' 'nonce-{nonce}' "
            f"https://cdn.tailwindcss.com "
            f"https://cdn.jsdelivr.net "
            f"https://code.jquery.com "
            f"https://cdnjs.cloudflare.com "
            f"https://ajax.googleapis.com "
            f"https://use.fontawesome.com; "
            
            # السماح بالستايلات المدمجة + مكتبات CDN (CSS لا يحتاج Nonce عالمياً في هذه المرحلة)
            f"style-src 'self' 'unsafe-inline' "
            f"https://cdn.jsdelivr.net "
            f"https://cdnjs.cloudflare.com "
            f"https://fonts.googleapis.com "
            f"https://cdn.tailwindcss.com "
            f"https://use.fontawesome.com; "
            
            # السماح بالخطوط
            f"font-src 'self' "
            f"https://fonts.gstatic.com "
            f"https://cdnjs.cloudflare.com "
            f"https://use.fontawesome.com; "
            
            # السماح بالصور (data: ضرورية للصور المصغرة base64)
            f"img-src 'self' data: https:; "
            
            # السماح بطلبات AJAX/Fetch + تحميل ملفات CDN ديناميكياً
            f"connect-src 'self' https://wa.me https://api.whatsapp.com "
            f"https://cdn.jsdelivr.net https://cdn.tailwindcss.com "
            f"https://code.jquery.com https://cdnjs.cloudflare.com "
            f"https://ajax.googleapis.com; "
            
            # منع تضمين الموقع في إطارات (حماية من Clickjacking)
            f"frame-ancestors 'none'; "
            
            # تحديد صريح لمنع المكونات المدمجة القديمة (مثل Flash)
            f"object-src 'none';"
        )
        
        # 5. إضافة الهيدر للـ Response (نقوم بتنظيف المسافات الزائدة ليكون الهيدر نظيفاً)
        response['Content-Security-Policy'] = " ".join(csp_policy.split())
        
        return response