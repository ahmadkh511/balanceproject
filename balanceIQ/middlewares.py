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


#--------- حماية اسم البرنامج

import re

class ProtectFooterMiddleware:
    """
    ميدل وير لحماية حقوق الشركة (BalanceIq)
    يبحث عن كلاس الفوتر ويحقن الكود بجانبه (مستقل عن النصوص المتغيرة)
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        content_type = response.get('Content-Type', '')
        if 'text/html' not in content_type:
            return response

        if response.streaming:
            return response

        try:
            content = response.content.decode('utf-8')
        except (UnicodeDecodeError, AttributeError):
            return response

        injected = False

        # 1. كود الحقوق المندمج (بنفس لون الفوتر)
        powered_by_html = """
        <span style="margin: 0 10px; color: rgba(255, 255, 255, 0.3);">|</span>
        <a href="https://balanceiqsoft.com" target="_blank" rel="noopener noreferrer" style="color: rgba(255, 255, 255, 0.5); text-decoration: none;">
            Powered by BalanceIq
        </a>
        """

        # 2. البحث عن كلاس السطر (text-md-start mb-1 mb-md-0) وحقن الكود بعده
        # هذا الكلاس ثابت في base.html ولن يتغير بتغير رقم الإصدار
        pattern = r'(text-md-start mb-1 mb-md-0">\s*<span>.*?</span>)'
        
        if re.search(pattern, content, re.IGNORECASE):
            content = re.sub(
                pattern, 
                r'\1' + powered_by_html, 
                content, 
                flags=re.IGNORECASE, 
                count=1
            )
            injected = True

        # 3. احتياطي للصفحات التي لا تحتوي على هذا الكلاس (مثل صفحات تسجيل الدخول)
        if not injected:
            fallback_html = """
            <div style="text-align: center; padding: 15px; font-size: 0.8rem; color: #666; font-family: 'Tajawal', sans-serif;">
                <a href="https://balanceiqsoft.com" target="_blank" rel="noopener noreferrer" style="color: #0097a7; text-decoration: none; font-weight: 600;">
                    Powered by BalanceIq
                </a>
            </div>
            """
            if re.search(r'</body>', content, re.IGNORECASE):
                content = re.sub(r'</body>', fallback_html + '</body>', content, flags=re.IGNORECASE, count=1)
                injected = True

        if injected:
            response.content = content.encode('utf-8')
            if 'Content-Length' in response:
                response['Content-Length'] = len(response.content)

        return response