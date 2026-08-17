from django.contrib import admin
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.translation import gettext_lazy as _
from django.db.models import Count
from .models import Product, PriceType, Shipping_com_m, Status, Currency, Payment_method, Barcode, Purch,  PurchItem , CashTransaction


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'date_created')
    search_fields = ('product_name',)


@admin.register(PriceType)
class PriceTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Shipping_com_m)
class Shipping_com_mAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Payment_method)
class Payment_methodAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)





@admin.register(CashTransaction)
class CashTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_date', 'created_by')
    search_fields = ('transaction_date',)



@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    """إدارة العملات في لوحة الإدارة"""
    
    list_display = (
        'code',
        'name_ar',
        'symbol',
        'exchange_rate',
        'is_default',
        'is_active',
        # 'created_at',  # قم بتعليق هذا
    )
    
    list_filter = (
        'is_active',
        'is_default',
    )
    
    search_fields = (
        'code',
        'name',
        'name_ar',
        'symbol',
    )
    
    ordering = ('code',)
    
    fieldsets = (
        (_('المعلومات الأساسية'), {
            'fields': (
                'code',
                'symbol',
                'name',
                'name_ar',
                'is_default',
                'is_active',
            )
        }),
        (_('أسماء التحويل إلى كلمات'), {
            'fields': (
                'singular_ar',
                'dual_ar',
                'plural_ar',
                'fraction_name_ar',
                'fraction_dual_ar',
                'fraction_plural_ar',
                'decimals',
            ),
            'classes': ('collapse',),
        }),
        (_('المعلومات المالية'), {
            'fields': (
                'exchange_rate',
            ),
            'classes': ('collapse',),
        }),
        # قم بتعليق قسم التواريخ
        # (_('التواريخ'), {
        #     'fields': (
        #         'created_at',
        #         'updated_at',
        #     ),
        #     'classes': ('collapse',),
        # }),
    )
    
    # readonly_fields = ('created_at', 'updated_at')  # قم بتعليق هذا
    
    list_per_page = 20
    
    actions = ['activate_currencies', 'deactivate_currencies', 'set_as_default']
    
    def activate_currencies(self, request, queryset):
        """تفعيل العملات المحددة"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'تم تفعيل {updated} عملة.')
    
    activate_currencies.short_description = _("تفعيل العملات المحددة")
    
    def deactivate_currencies(self, request, queryset):
        """تعطيل العملات المحددة"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'تم تعطيل {updated} عملة.')
    
    deactivate_currencies.short_description = _("تعطيل العملات المحددة")
    
    def set_as_default(self, request, queryset):
        """تعيين العملة المحددة كأساسية"""
        if queryset.count() != 1:
            self.message_user(request, _("يرجى اختيار عملة واحدة فقط."), level='error')
            return
        
        currency = queryset.first()
        currency.is_default = True
        currency.save()
        self.message_user(request, f'تم تعيين {currency.name_ar} كعملة أساسية.')
    
    set_as_default.short_description = _("تعيين كعملة أساسية")


# admin.py - استمرار
@admin.register(Purch)
class PurchAdmin(admin.ModelAdmin):
    """إدارة فواتير الشراء في لوحة الإدارة"""
    
    list_display = (
        'uniqueId',
        'purch_supplier',
        'purch_date',
        'purch_currency',
        'purch_final_total',
        'paid_amount',
        'balance_due',
        'is_paid',
        'purch_status',
        'created_by',
        'date_created',
    )
    
    list_filter = (
        'purch_status',
        'is_paid',
        'purch_currency',
        'purch_date',
        'purch_type',
    )
    
    search_fields = (
        'uniqueId',
        'supplier_invoice_number',
        'purch_supplier__username',
        'purch_supplier__first_name',
        'purch_supplier__last_name',
        'purch_notes',
    )
    
    readonly_fields = (
        'date_created',
        'last_updated',
        'uniqueId',
        'slug',
        'purch_subtotal',
        'purch_tax_amount',
        'purch_final_total',
        'balance_due',
        'created_by',
    )
    
    fieldsets = (
        (_('المعلومات الأساسية'), {
            'fields': (
                'uniqueId',
                'slug',
                'purch_supplier',
                'purch_date',
                'purch_invoice_date',
                'purch_due_date',
            )
        }),
        (_('معلومات المورد'), {
            'fields': (
                'purch_supplier_phone',
                'purch_address',
                'supplier_invoice_number',
            )
        }),
        (_('المعلومات الإدارية'), {
            'fields': (
                'purch_type',
                'purch_status',
                'purch_currency',
                'purch_payment_method',
                'created_by',
            )
        }),
        (_('معلومات الشحن'), {
            'fields': (
                'purch_delivery_method',
                'purch_shipping_company',
                'purch_shipping_num',
                'purch_delivery_tracking_number',
            ),
            'classes': ('collapse',),
        }),
        (_('الحسابات المالية'), {
            'fields': (
                'purch_tax_percentage',
                'purch_tax_amount',
                'purch_discount',
                'purch_addition',
                'purch_subtotal',
                'purch_final_total',
                'paid_amount',
                'balance_due',
                'is_paid',
            )
        }),
        (_('ملاحظات ومرفقات'), {
            'fields': (
                'purch_notes',
                'purch_image',
            ),
            'classes': ('collapse',),
        }),
        (_('معلومات النظام'), {
            'fields': (
                'date_created',
                'last_updated',
            ),
            'classes': ('collapse',),
        }),
    )
    
    ordering = ('-date_created',)
    list_per_page = 20
    date_hierarchy = 'purch_date'
    
    # إضافة زر لعرض الإجمالي المكتوب
    actions = ['show_total_in_words']
    
    def show_total_in_words(self, request, queryset):
        """عرض الإجمالي مكتوباً للفواتير المحددة"""
        messages = []
        for purchase in queryset:
            if purchase.purch_final_total:
                total_words = purchase.total_in_words
                messages.append(f"{purchase.uniqueId}: {total_words}")
        
        if messages:
            self.message_user(request, "\n".join(messages))
        else:
            self.message_user(request, _("لا توجد فواتير بالإجمالي المحدد."))
    
    show_total_in_words.short_description = _("عرض الإجمالي مكتوباً")
    
    # تخصيص العرض في القائمة
    def get_currency_display(self, obj):
        """تنسيق عرض العملة"""
        if obj.purch_currency:
            return f"{obj.purch_currency.symbol} ({obj.purch_currency.code})"
        return "-"
    
    get_currency_display.short_description = _("العملة")
    
    def get_final_total_display(self, obj):
        """تنسيق عرض الإجمالي النهائي"""
        if obj.purch_currency:
            return f"{obj.purch_final_total:,.2f} {obj.purch_currency.symbol}"
        return f"{obj.purch_final_total:,.2f}"
    
    get_final_total_display.short_description = _("الإجمالي")
    
    # إضافة الإجمالي المكتوب في صفحة التفاصيل
    def get_readonly_fields(self, request, obj=None):
        """إضافة الحقول للقراءة فقط"""
        fields = list(self.readonly_fields)
        
        if obj and obj.pk:
            # إضافة حقل الإجمالي المكتوب
            fields.append('total_in_words_display')
        
        return fields
    
    def total_in_words_display(self, obj):
        """عرض الإجمالي مكتوباً في صفحة التفاصيل"""
        if obj.purch_final_total:
            return f"<div style='background:#f8f9fa; padding:15px; border-radius:8px; border:2px solid #3498db;'><strong>الإجمالي مكتوباً:</strong><br>{obj.total_in_words}</div>"
        return "-"
    
    total_in_words_display.short_description = _("الإجمالي كتابة")
    total_in_words_display.allow_tags = True
    
    # إضافة حقول حسابية في القائمة
    def get_queryset(self, request):
        """تحسين الاستعلام"""
        qs = super().get_queryset(request)
        return qs.select_related(
            'purch_supplier',
            'purch_currency',
            'purch_status',
            'purch_payment_method',
            'created_by'
        ).prefetch_related('purchitem_set')
    
    # إعداد الحقول المستبعدة عند الإنشاء
    def get_exclude(self, request, obj=None):
        """تحديد الحقول المستبعدة"""
        exclude = []
        
        if not obj:
            # عند الإنشاء، إخفاء الحقول المحسوبة
            exclude.extend([
                'purch_subtotal',
                'purch_tax_amount',
                'purch_final_total',
                'balance_due',
            ])
        
        return exclude
    
    # حفظ الكائن
    def save_model(self, request, obj, form, change):
        """تجاوز حفظ النموذج"""
        if not change:
            # عند الإنشاء
            if not obj.created_by:
                obj.created_by = request.user
            
            if not obj.uniqueId:
                last_invoice = Purch.objects.order_by('-_last_invoice_number').first()
                last_number = last_invoice._last_invoice_number if last_invoice else 0
                new_number = last_number + 1
                
                obj._last_invoice_number = new_number
                obj.uniqueId = f"P{new_number:04d}"
        
        super().save_model(request, obj, form, change)


# admin.py - استمرار
class PurchItemInline(admin.TabularInline):
    """بنود الفاتورة داخل صفحة الفاتورة"""
    model = PurchItem
    extra = 1
    fields = (
        'product',
        'item_name',
        'purchased_quantity',
        'unit_price',
        'purch_total',
        'notes',
    )
    readonly_fields = ('purch_total',)
    
    # إضافة CSS مخصص
    class Media:
        css = {
            'all': ('admin/css/purch-items.css',)
        }
    
    def get_formset(self, request, obj=None, **kwargs):
        """تخصيص نموذج البنود"""
        formset = super().get_formset(request, obj, **kwargs)
        
        # إضافة حقول للفلترة
        form = formset.form
        form.base_fields['product'].widget.can_add_related = True
        form.base_fields['product'].widget.can_change_related = True
        form.base_fields['product'].widget.can_delete_related = True
        
        return formset

# إضافة Inline إلى PurchAdmin
PurchAdmin.inlines = [PurchItemInline]



# admin.py - استمرار
@admin.register(PurchItem)
class PurchItemAdmin(admin.ModelAdmin):
    """إدارة بنود فواتير الشراء"""
    
    list_display = (
        'purch',
        'product',
        'item_name',
        'purchased_quantity',
        'unit_price',
        'purch_total',
        'date_created',
    )
    
    list_filter = (
        'purch__purch_currency',
        'date_created',
    )
    
    search_fields = (
        'item_name',
        'product__product_name',
        'purch__uniqueId',
        'notes',
    )
    
    readonly_fields = (
        'purch_total',
        'date_created',
        'last_updated',
    )
    
    fieldsets = (
        (_('المعلومات الأساسية'), {
            'fields': (
                'purch',
                'product',
                'item_name',
            )
        }),
        (_('الكميات والأسعار'), {
            'fields': (
                'purchased_quantity',
                'unit_price',
                'purch_total',
            )
        }),
        (_('معلومات إضافية'), {
            'fields': (
                'notes',
                'purch_item_image',
                'purch_currency',
                'exchange_rate_at_purchase',
                'unit_price_base_currency',
            ),
            'classes': ('collapse',),
        }),
        (_('معلومات النظام'), {
            'fields': (
                'date_created',
                'last_updated',
            ),
            'classes': ('collapse',),
        }),
    )
    
    ordering = ('-date_created',)
    list_per_page = 20
    
    # الروابط السريعة
    list_display_links = ('purch', 'product', 'item_name')
    
    # تخصيص العروض
    def get_purch_display(self, obj):
        """تنسيق عرض الفاتورة"""
        return f"{obj.purch.uniqueId} - {obj.purch.purch_date}"
    
    get_purch_display.short_description = _("الفاتورة")
    
    def get_total_display(self, obj):
        """تنسيق عرض الإجمالي"""
        if obj.purch.purch_currency:
            return f"{obj.purch_total:,.2f} {obj.purch.purch_currency.symbol}"
        return f"{obj.purch_total:,.2f}"
    
    get_total_display.short_description = _("الإجمالي")
