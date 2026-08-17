# من اجل الصلاحيات 

# ============================================
# accounts/utils.py
# حارس البيانات المركزي (Data Guard)
# ============================================

from django.core.exceptions import PermissionDenied


def get_user_scoped_queryset(queryset, request):
    """
    تخصيص نطاق البيانات (Data Scoping) للقوائم (Lists).
    
    مهمته:
    - إذا كان المستخدم "سوبر يوزر": يرجع كل البيانات كما هي (بدون فلترة).
    - إذا كان المستخدم عادياً: يفلتر البيانات ليعرض بياناته هو فقط (التي أنشأها).
    
    كيفية الاستخدام داخل فيوهات invoice:
        # بدلاً من: queryset = Sale.objects.all()
        # ستكتب:   queryset = get_user_scoped_queryset(Sale.objects.all(), request)
    """
    if request.user.is_superuser:
        return queryset
    
    # التأكد من أن الموديل يمتلك حقل created_by قبل تنفيذ الفلتر
    if hasattr(queryset.model, 'created_by'):
        return queryset.filter(created_by=request.user)
        
    return queryset


def check_object_owner(obj, request):
    """
    فحص ملكية العنصر (Object Ownership Check) للتفاصيل والتعديل والحذف.
    
    مهمته:
    - إذا كان المستخدم "سوبر يوزر": يسمح له بالمرور فوراً.
    - إذا كان المستخدم عادياً: يتحقق مما إذا كان هو من أنشأ هذا العنصر.
    - إذا لم يكن هو من أنشأه: يرمي خطأ 403 (PermissionDenied) فوراً.
    
    كيفية الاستخدام داخل فيوهات invoice:
        # بدلاً من:
        # if obj.created_by and obj.created_by != request.user and not request.user.is_superuser:
        #     raise PermissionDenied(...)
        # ستكتب بسطر واحد:
        # check_object_owner(obj, request)
    """
    if request.user.is_superuser:
        return True
        
    # التحقق من أن الكائن يمتلك الحقل، وأن الحقل ليس فارغاً، وأنه يطابق المستخدم
    if hasattr(obj, 'created_by') and obj.created_by is not None:
        if obj.created_by == request.user:
            return True
            
    # إذا وصلنا هنا، فهو مستخدم عادي يحاول الوصول لبيانات غيره
    raise PermissionDenied("ليس لديك صلاحية للوصول إلى هذا العنصر.")