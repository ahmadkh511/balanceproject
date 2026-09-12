# ==================== مكتبات بايثون القياسية ====================
import logging
from decimal import Decimal

# ==================== إطار عمل Django Forms ====================
from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum

# ==================== النماذج المحلية (Models) ====================
from .models import (
    Barcode,
    CashTransaction,
    Currency,
    EmailSetting,
    Payment_method,
    PriceType,
    Product,
    Purch,
    PurchItem,
    PurchItemBarcode,
    PurchaseReturn,
    PurchaseReturnItem,
    PurchaseReturnItemBarcode,
    Sale,
    SaleItem,
    SaleItemBarcode,
    SaleReturn,
    SaleReturnItem,
    SaleReturnItemBarcode,
    Shipping_com_m,
    Status,
)

from decimal import Decimal
from django.utils.translation import gettext_lazy as _



from decimal import Decimal, InvalidOperation
from django import forms
from .models import Sale, SaleItem, SaleItemBarcode, CashTransaction




from django import forms
from django.forms import inlineformset_factory
from .models import SaleReturn, SaleReturnItem, SaleReturnItemBarcode



#================================================
#  الصندوق
# ===============================================


class CashTransactionForm(forms.ModelForm):
    class Meta:
        model = CashTransaction
        fields = ['transaction_type', 'amount_in', 'amount_out', 'notes']
        widgets = {
            'transaction_type': forms.HiddenInput(),
            'amount_in': forms.NumberInput(attrs={
                'class': 'form-control amount-input', 
                'step': '0.01', 
                'min': '0', 
                'placeholder': '0.00'
            }),
            'amount_out': forms.NumberInput(attrs={
                'class': 'form-control amount-input', 
                'step': '0.01', 
                'min': '0', 
                'placeholder': '0.00'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'أدخل ملاحظات الحركة هنا...'
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        transaction_type = cleaned_data.get('transaction_type')
        amount_in = cleaned_data.get('amount_in', Decimal('0.00'))
        amount_out = cleaned_data.get('amount_out', Decimal('0.00'))
        
        if transaction_type == 'deposit':
            if amount_in <= 0:
                raise forms.ValidationError("يجب إدخال مبلغ أكبر من صفر للإيداع.")
            if amount_out > 0:
                raise forms.ValidationError("لا يمكن إدخال مبلغ خارجي في عملية الإيداع.")
        elif transaction_type in ['withdrawal', 'expense']:
            if amount_out <= 0:
                raise forms.ValidationError("يجب إدخال مبلغ أكبر من صفر للسحب أو المصروفات.")
            if amount_in > 0:
                raise forms.ValidationError("لا يمكن إدخال مبلغ داخلي في عملية السحب أو المصروفات.")
        return cleaned_data


#================================================
#    اعدادات الايمل 
# ===============================================



class EmailSettingForm(forms.ModelForm):
    class Meta:
        model = EmailSetting
        fields = '__all__'
        widgets = {
            'email_host_password': forms.PasswordInput(render_value=True),
        }




#================================================
#  المشتريات 
# ===============================================


class PurchForm(forms.ModelForm):
    """نموذج فاتورة المشتريات الرئيسي"""
    
    class Meta:
        model = Purch
        fields = [
            'purch_supplier', 'purch_date', 'purch_supplier_phone', 'purch_address',
            'supplier_invoice_number', 'purch_delivery_method', 'purch_payment_method',
            'purch_notes', 'purch_currency', 'purch_type', 'purch_status',
            'purch_shipping_company', 'purch_due_date', 'purch_image', 'paid_amount',
            'purch_shipping_num', 'purch_tax_percentage', 'purch_discount', 'purch_addition',
            'purch_subtotal', 'purch_tax_amount', 'purch_final_total', 'balance_due'
        ]
        widgets = {
            'purch_supplier': forms.HiddenInput(),
            'purch_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'purch_due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'purch_notes': forms.Textarea(attrs={'rows': 1, 'class': 'form-control'}),
            'purch_shipping_num': forms.Textarea(attrs={'rows': 1, 'class': 'form-control'}),
            'purch_supplier_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'purch_address': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'purch_image': forms.FileInput(attrs={'class': 'd-none'}),
            'paid_amount': forms.NumberInput(attrs={'class': 'd-none'}),
            'purch_tax_percentage': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'min': '0', 
                'max': '100'
            }),
            'purch_discount': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'min': '0'
            }),
            'purch_addition': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'min': '0'
            }),
            'purch_subtotal': forms.HiddenInput(),
            'purch_tax_amount': forms.HiddenInput(),
            'purch_final_total': forms.HiddenInput(),
            'balance_due': forms.HiddenInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        for field_name, field in self.fields.items():
            if field_name not in [
                'purch_notes', 'purch_supplier', 'purch_image', 'paid_amount',
                'purch_subtotal', 'purch_tax_amount', 'purch_final_total', 'balance_due'
            ]:
                field.widget.attrs.update({'class': 'form-control'})
        
        non_required_fields = [
            'purch_tax_percentage', 'purch_discount', 'purch_addition',
            'purch_subtotal', 'purch_tax_amount', 'purch_final_total', 'balance_due'
        ]
        for field_name in non_required_fields:
            self.fields[field_name].required = False

    def clean(self):
        """
        ★★★ إصلاح الخلل الرئيسي ★★★
        
        المشكلة السابقة: كان الفحص يقارن المبلغ المدفوع بـ calculated_total
        المحسوبة من purch_subtotal — لكن قالب الإنشاء لا يرسل هذا الحقل إطلاقاً،
        فكانت المقارنة تجري ضد (الإضافة - الخصم) فقط، وترفض أي فاتورة نقدية
        فيها إضافة بمبلغ مدفوع كامل.
        
        الفحص المرجعي الصحيح موجود في الفيو (purch_create) بعد حساب
        calculate_and_save_totals() حيث يُحسب الإجمالي الحقيقي من بنود
        قاعدة البيانات داخل معاملة ذرية.
        
        الحارس المشروط أدناه يعمل فقط إذا أرسل القالب قيمة subtotal فعلية
        (قالب الإنشاء لا يرسلها أبداً) — بقي كحماية لمسار التعديل حتى
        نراجعه في المرحلة الثانية.
        """
        cleaned_data = super().clean()
        
        paid_amount = cleaned_data.get('paid_amount') or Decimal('0.00')
        
        # التحقق من أن المبلغ المدفوع ليس سالباً
        if paid_amount < Decimal('0.00'):
            self.add_error('paid_amount', _('المبلغ المدفوع لا يمكن أن يكون سالباً'))
        
        # حارس مشروط: يتفعّل فقط عند إرسال subtotal فعلي مع الفورم
        subtotal = cleaned_data.get('purch_subtotal')
        if subtotal:
            tax_percentage = cleaned_data.get('purch_tax_percentage') or Decimal('0.00')
            addition = cleaned_data.get('purch_addition') or Decimal('0.00')
            discount = cleaned_data.get('purch_discount') or Decimal('0.00')
            
            tax_amount = (subtotal * tax_percentage / Decimal('100')).quantize(Decimal('0.01'))
            calculated_total = subtotal + tax_amount + addition - discount
            
            if paid_amount > calculated_total:
                self.add_error(
                    'paid_amount', 
                    _('المبلغ المدفوع (%(paid)s) أكبر من الإجمالي العام (%(total)s)') % {
                        'paid': paid_amount, 
                        'total': calculated_total
                    }
                )
            
        return cleaned_data



class PurchItemForm(forms.ModelForm):
    """نموذج بند الشراء (لإنشاء فاتورة جديدة)"""
    
    class Meta:
        model = PurchItem
        fields = ['product', 'item_name', 'purchased_quantity', 'unit_price', 'notes', 'purch_item_image']
        widgets = {
            'product': forms.HiddenInput(),
            'item_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'اسم المادة'
            }),
            'purchased_quantity': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'min': '0.01'
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'min': '0'
            }),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
            'purch_item_image': forms.FileInput(attrs={'class': 'd-none'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purch_item_image'].required = False


class PurchItemBarcodeForm(forms.ModelForm):
    """نموذج لربط الباركود ببند الشراء"""
    
    class Meta:
        model = PurchItemBarcode
        fields = ['barcode', 'quantity_used', 'barcode_status']
        widgets = {
            'quantity_used': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'min': '0.01'
            }),
            'barcode_status': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['barcode'].widget.attrs.update({'class': 'form-control select2'})


PurchItemFormSet = inlineformset_factory(
    Purch, 
    PurchItem, 
    form=PurchItemForm,
    extra=1,
    can_delete=True,
    can_order=False
)

PurchItemBarcodeFormSet = inlineformset_factory(
    PurchItem, 
    PurchItemBarcode, 
    form=PurchItemBarcodeForm,
    extra=1, 
    can_delete=True, 
    can_order=False
)


#================================================
#  تعديل  المشتريات 
# ===============================================


class PurchEditForm(forms.ModelForm):
    """فورم تعديل فاتورة المشتريات مع إضافة حقول مالية"""
    
    class Meta:
        model = Purch
        fields = [
            'purch_supplier', 'purch_date', 'purch_supplier_phone', 'purch_address',
            'supplier_invoice_number', 'purch_delivery_method', 'purch_payment_method',
            'purch_notes', 'purch_currency', 'purch_type', 'purch_status',
            'purch_shipping_company', 'purch_due_date', 'purch_image', 'paid_amount',
            'purch_shipping_num', 'purch_tax_percentage', 'purch_discount', 
            'purch_addition', 'purch_subtotal', 'purch_tax_amount', 'purch_final_total',
            'balance_due', 'is_paid'
        ]
        widgets = {
            'purch_supplier': forms.Select(attrs={'class': 'form-control'}),
            'purch_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'purch_due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'purch_notes': forms.Textarea(attrs={'rows': 1, 'class': 'form-control'}),
            'purch_shipping_num': forms.Textarea(attrs={'rows': 1, 'class': 'form-control'}),
            'purch_supplier_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'purch_address': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'purch_image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'paid_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'purch_tax_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'purch_discount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'purch_addition': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'purch_subtotal': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'readonly': True}),
            'purch_tax_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'readonly': True}),
            'purch_final_total': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'readonly': True}),
            'balance_due': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'readonly': True}),
            'is_paid': forms.CheckboxInput(attrs={'class': 'form-check-input', 'disabled': True}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تعطيل بعض الحقول للقراءة فقط
        readonly_fields = ['purch_subtotal', 'purch_tax_amount', 'purch_final_total', 'balance_due', 'is_paid']
        for field in readonly_fields:
            if field in self.fields:
                self.fields[field].widget.attrs['readonly'] = True
        
        # تحسين عرض حقل صورة الفاتورة
        self.fields['purch_image'].widget.attrs.update({
            'class': 'form-control file-input',
            'accept': 'image/*',
            'data-max-size': '5242880'  # 5MB
        })
        
        # تعيين كلاس form-control للحقول المرئية
        for field_name, field in self.fields.items():
            if field_name not in ['purch_notes', 'purch_image', 'purch_shipping_num']:
                field.widget.attrs.update({'class': 'form-control'})


class PurchItemEditForm(forms.ModelForm):
    """Form لتعديل بند الشراء مع حساب الكمية المتبقية بعد المرتجعات"""
    class Meta:
        model = PurchItem
        fields = [
            'product', 'item_name', 'purchased_quantity', 
            'unit_price', 'notes', 'purch_item_image'
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control', 'style': 'display: none;'}),
            'item_name': forms.TextInput(attrs={'class': 'form-control', 'style': 'display: none;'}),
            'purchased_quantity': forms.NumberInput(attrs={'class': 'form-control quantity-input'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control price-input'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        # 1. استخراج الفاتورة الأصلية وبيانات المرتجعات من kwargs قبل استدعاء super()
        self.original_purchase = kwargs.pop('original_purchase', None)
        self.returned_items_data = kwargs.pop('returned_items_data', None)
        super().__init__(*args, **kwargs)
        
        # جعل الحقول غير مطلوبة للسماح بالإدخال المرن
        self.fields['product'].required = False
        self.fields['item_name'].required = False

        # 2. 🔑 هنا يتم المنطق الجديد: تعديل القيمة الأولية للكمية
        # يتم التحقق من أن البند موجود (له pk) وأن الفاتورة الأصلية ممررة
        if self.instance and self.instance.pk and self.original_purchase:
            # ======== استخدام returned_items_data إذا كانت متاحة ========
            if self.returned_items_data and self.instance.id in self.returned_items_data:
                returned_quantity = self.returned_items_data[self.instance.id]
            else:
                # استخدام الطريقة القديمة كخطة احتياطية
                from invoice.models import PurchaseReturnItem
                returned_quantity = PurchaseReturnItem.objects.filter(
                    original_item=self.instance,
                    purchase_return__original_purchase=self.original_purchase
                ).aggregate(total=Sum('returned_quantity'))['total'] or 0

            original_quantity = self.instance.purchased_quantity
            remaining_quantity = original_quantity - returned_quantity
            
            # تحديث القيمة الأولية لحقل الكمية في الفورم
            # هذا هو الإجراء الصحيح الذي يضمن عرض القيمة الصحيحة في الواجهة
            self.initial['purchased_quantity'] = remaining_quantity
            
            print(f"🔧 فورم البند {self.instance.pk}: تعديل الكمية الأولية من {original_quantity} إلى {remaining_quantity}")


class BasePurchItemEditFormSet(BaseInlineFormSet):
    """
    فورمست مخصص للسماح بتمرير original_purchase و returned_items_data إلى كل فورم داخلي.
    هذا هو الجسر الذي يسمح لنا بإرسال البيانات من الفيو إلى كل فورم على حدة.
    """
    def __init__(self, *args, **kwargs):
        # استخراج original_purchase و returned_items_data من kwargs وتخزينها في الفورمست
        self.original_purchase = kwargs.pop('original_purchase', None)
        self.returned_items_data = kwargs.pop('returned_items_data', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        # عند بناء كل فورم، قم بتمرير original_purchase و returned_items_data إليه
        kwargs['original_purchase'] = self.original_purchase
        kwargs['returned_items_data'] = self.returned_items_data
        return super()._construct_form(i, **kwargs)


class PurchItemBarcodeEditForm(forms.ModelForm):
    """فورم تعديل ربط الباركود ببند الشراء"""
    
    class Meta:
        model = PurchItemBarcode
        fields = ['barcode', 'quantity_used', 'barcode_status']
        widgets = {
            'quantity_used': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'min': '0.01'
            }),
            'barcode_status': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['barcode'].widget.attrs.update({'class': 'form-control select2'})



PurchItemEditFormSet = inlineformset_factory(
    Purch, 
    PurchItem, 
    form=PurchItemEditForm,
    formset=BasePurchItemEditFormSet,  # 🔑 استخدام الفورمست المخصص هنا
    extra=0,
    can_delete=True,
    can_order=False
)


PurchItemBarcodeEditFormSet = inlineformset_factory(
    PurchItem, 
    PurchItemBarcode, 
    form=PurchItemBarcodeEditForm,
    extra=0,
    can_delete=True, 
    can_order=False
)


#================================================
#  المنتجات و الباركود 
# ===============================================


class ProductForm(forms.ModelForm):
    """نموذج المنتج - معلومات فقط بدون حسابات"""
    
    class Meta:
        model = Product
        fields = [
            'product_name', 'main_barcode', 'product_description', 'product_image'
        ]
        widgets = {
            'product_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('اسم المادة'),
                'autofocus': True
            }),
            'main_barcode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('أدخل الباركود الأساسي (اختياري)')
            }),
            'product_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': _('وصف المادة (اختياري)')
            }),
            'product_image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            })
        }
        labels = {
            'product_name': _('اسم المادة'),
            'main_barcode': _('الباركود الأساسي'),
            'product_description': _('وصف المادة'),
            'product_image': _('صورة المادة')
        }
        help_texts = {
            'product_name': _('أدخل اسم المادة كاملاً'),
            'main_barcode': _('الباركود الأساسي للمادة (اختياري) - يجب أن يكون فريداً'),
            'product_description': _('يمكنك إضافة وصف تفصيلي للمادة'),
            'product_image': _('صورة المادة (اختياري)')
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # جعل جميع الحقول غير إجبارية ما عدا اسم المادة
        self.fields['product_name'].required = True
        self.fields['main_barcode'].required = False
        self.fields['product_description'].required = False
        self.fields['product_image'].required = False



class BarcodeForm(forms.ModelForm):
    """نموذج لإضافة باركود جديد"""
    
    class Meta:
        model = Barcode
        fields = ['barcode_in', 'barcode_out', 'suffix', 'product', 'is_primary', 'notes', 'status']
        widgets = {
            'barcode_in': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('أدخل الباركود الداخلي')
            }),
            'barcode_out': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('أدخل الباركود الخارجي (اختياري)')
            }),
            'suffix': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('اللاحقة (اختياري)')
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('ملاحظات حول الباركود')
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].widget.attrs.update({'class': 'form-control select2'})
        
        # جعل الحقول غير مطلوبة
        self.fields['barcode_out'].required = False
        self.fields['suffix'].required = False
        self.fields['notes'].required = False






#================================================
#       مرتجع المشتريات
# ===============================================

class PurchaseReturnForm(forms.ModelForm):
    class Meta:
        model = PurchaseReturn
        fields = ['return_date', 'return_notes', 'paid_amount']
        widgets = {
            'return_date': forms.DateInput(attrs={
                'type': 'date', 
                'class': 'form-control',
                'required': 'required',
                'readonly': 'readonly'
            }),
            'return_notes': forms.Textarea(attrs={
                'rows': 2, 
                'class': 'form-control', 
                'placeholder': 'أدخل ملاحظات المرتجع هنا...'
            }),
            'paid_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
                'id': 'paid-amount'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        return_final_total = kwargs.pop('return_final_total', Decimal('0.00'))
        is_cash_payment = kwargs.pop('is_cash_payment', False)
        super().__init__(*args, **kwargs)
        
        # تعيين المبلغ المستلم تلقائياً إذا كانت الفاتورة نقدية
        if is_cash_payment and 'paid_amount' in self.fields:
            self.initial['paid_amount'] = return_final_total

class PurchaseReturnItemForm(forms.ModelForm):
    original_barcodes = forms.ModelMultipleChoiceField(
        queryset=Barcode.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'barcode-checkbox'}),
        label=_("الباركودات المرتجعة")
    )

    class Meta:
        model = PurchaseReturnItem
        fields = ['original_item', 'product', 'purchased_quantity', 
                 'returned_quantity', 'return_unit_price', 'return_total' ]
        
        widgets = {
            'original_item': forms.HiddenInput(),
            'product': forms.HiddenInput(),
            'purchased_quantity': forms.HiddenInput(attrs={
                'class': 'purchased-quantity-hidden'
            }),
            # ======== التعديل الرئيسي هنا ========
            # تمت إزالة 'required': 'required' للسماح بترك الحقل فارغاً
            'returned_quantity': forms.NumberInput(attrs={
                'class': 'form-control returned-quantity', 
                'step': '0.01', 
                'min': '0.00',
                'placeholder': _('أدخل الكمية المرتجعة')
            }),
            'return_unit_price': forms.HiddenInput(attrs={
                'class': 'unit-price-hidden'
            }),
            'return_total': forms.HiddenInput(attrs={
                'class': 'item-total-hidden'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        original_item = kwargs.pop('original_item', None)
        super().__init__(*args, **kwargs)
        
        # ======== تعديل في __init__ ========
        # جعل حقل الكمية غير إلزامي دائماً
        # الاعتماد على منطق التحقق في دالة clean()
        self.fields['returned_quantity'].required = False
        
        if original_item:
            self.fields['original_item'].initial = original_item
            self.fields['product'].initial = original_item.product
            self.fields['purchased_quantity'].initial = original_item.purchased_quantity
            self.fields['return_unit_price'].initial = original_item.unit_price
            self.fields['return_total'].initial = Decimal('0.00')
            
            if original_item.pk:
                available_barcodes = PurchItemBarcode.objects.filter(
                    purch_item=original_item,
                    barcode_status='active'
                ).select_related('barcode')
                
                barcode_ids = [barcode.barcode_id for barcode in available_barcodes]
                self.fields['original_barcodes'].queryset = Barcode.objects.filter(id__in=barcode_ids)
        
        # هذه الحقول مخفية ويجب أن تظل مطلوبة للعملية الداخلية
        self.fields['purchased_quantity'].required = True
        self.fields['return_unit_price'].required = True
        self.fields['return_total'].required = True
    
    def clean_returned_quantity(self):
        # ======== هذه الدالة تبقى كما هي ========
        returned_quantity = self.cleaned_data.get('returned_quantity')
        
        # إذا كانت الكمية فارغة، نرجعها كصفر
        if returned_quantity is None or returned_quantity == '':
            return Decimal('0.00')
        
        try:
            returned_quantity = Decimal(str(returned_quantity))
        except (ValueError, TypeError):
            raise forms.ValidationError(_('القيمة المدخلة غير صالحة'))
        
        # السماح بالصفر (يمكن للمستخدم عدم اختيار هذا البند)
        if returned_quantity < Decimal('0.00'):
            raise forms.ValidationError(_('لا يمكن أن تكون الكمية المرتجعة سالبة'))
        
        return returned_quantity
    
    def clean(self):
        # ======== هذه الدالة تبقى كما هي ========
        cleaned_data = super().clean()
        returned_quantity = cleaned_data.get('returned_quantity', Decimal('0.00'))
        original_barcodes = cleaned_data.get('original_barcodes', [])
        original_item = cleaned_data.get('original_item')
        
        # التحقق من وجود باركودات للبند
        has_barcodes = False
        if original_item and original_item.pk:
            has_barcodes = PurchItemBarcode.objects.filter(
                purch_item=original_item,
                barcode_status='active'
            ).exists()
        
        # إذا كان هناك باركودات متاحة
        if has_barcodes:
            # إذا تم اختيار باركودات، يجب أن تتطابق الكمية مع عدد الباركودات
            if original_barcodes:
                barcode_count = len(original_barcodes)
                cleaned_data['returned_quantity'] = Decimal(str(barcode_count))
            # إذا لم يتم اختيار باركودات، يجب أن تكون الكمية صفر
            else:
                cleaned_data['returned_quantity'] = Decimal('0.00')
        else:
            # إذا لم يكن هناك باركودات، يمكن إدخال الكمية يدوياً
            if returned_quantity > Decimal('0.00') and not original_barcodes:
                # لا يوجد خطأ - يمكن إرجاع كمية بدون باركودات
                pass
        
        if original_item and returned_quantity > Decimal('0.00'):
            total_returned = original_item.returned_items.aggregate(
                total=Sum('returned_quantity')
            )['total'] or Decimal('0.00')
            
            available_quantity = original_item.purchased_quantity - total_returned
            
            if returned_quantity > available_quantity:
                raise forms.ValidationError({
                    'returned_quantity': _('الكمية المرتجعة (%(returned)s) تتجاوز الكمية المتاحة (%(available)s)') % {
                        'returned': returned_quantity,
                        'available': available_quantity
                    }
                })
        
        return cleaned_data

PurchaseReturnItemFormSet = inlineformset_factory(
    PurchaseReturn, 
    PurchaseReturnItem, 
    form=PurchaseReturnItemForm,
    extra=0, 
    can_delete=True,
    min_num=0,
    validate_min=True
)






#===============================================
#        المبيعات 
# ==============================================



class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = [
            'sale_customer', 'sale_date', 'sale_customer_phone', 'sale_address',
            'sale_invoice_number', 'sale_payment_method', 'sale_notes', 'sale_currency',
            'sale_status', 'sale_image', 'paid_amount', 'sale_tax_percentage',
            'sale_discount', 'sale_addition', 'sale_subtotal', 'sale_tax_amount',
            'sale_final_total', 'balance_due', 'sale_shipping_company', 'sale_shipping_num'
        ]
        widgets = {
            'sale_customer': forms.HiddenInput(),
            'sale_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'sale_notes': forms.Textarea(attrs={'rows': 1, 'class': 'form-control'}),
            'sale_shipping_num': forms.TextInput(attrs={'class': 'form-control'}),
            'sale_customer_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'sale_address': forms.TextInput(attrs={'class': 'form-control'}),
            'sale_invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'sale_image': forms.FileInput(attrs={'class': 'd-none'}),
            # ✅ إصلاح: تحويل الحقول المالية إلى HiddenInput لمنع تعارضها مع الحقول المخصصة في HTML
            'paid_amount': forms.HiddenInput(attrs={'id': 'form-paid-amount'}),
            'sale_tax_percentage': forms.HiddenInput(attrs={'id': 'form-tax-percentage'}),
            'sale_discount': forms.HiddenInput(attrs={'id': 'form-discount'}),
            'sale_addition': forms.HiddenInput(attrs={'id': 'form-addition'}),
            'sale_subtotal': forms.HiddenInput(attrs={'id': 'form-subtotal'}),
            'sale_tax_amount': forms.HiddenInput(attrs={'id': 'form-tax-amount'}),
            'sale_final_total': forms.HiddenInput(attrs={'id': 'form-final-total'}),
            'balance_due': forms.HiddenInput(attrs={'id': 'form-balance-due'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # إضافة التنسيق للحقول الظاهرة
        for field_name, field in self.fields.items():
            if field_name not in [
                'sale_notes', 'sale_customer', 'sale_image',
                'sale_subtotal', 'sale_tax_amount', 'sale_final_total', 'balance_due',
                'paid_amount', 'sale_tax_percentage', 'sale_discount', 'sale_addition',
            ]:
                field.widget.attrs.update({'class': 'form-control'})
        
        # ✅ إصلاح: جعل الحقول المالية غير مطلوبة لتجنب أخطاء التحقق عند الإرسال
        non_required_fields = [
            'sale_tax_percentage', 'sale_discount', 'sale_addition',
            'sale_subtotal', 'sale_tax_amount', 'sale_final_total', 'balance_due',
            'paid_amount',
        ]
        for field_name in non_required_fields:
            self.fields[field_name].required = False
    
    # ✅ دوال التنظيف للتعامل مع الفواصل العربية وتحويل النصوص إلى أرقام عشرية
    def clean_sale_tax_percentage(self):
        value = self.cleaned_data.get('sale_tax_percentage')
        if value is not None and value != '':
            if isinstance(value, str):
                value = value.replace(',', '.')
            try:
                return Decimal(str(value))
            except (ValueError, InvalidOperation):
                return Decimal('0.00')
        return Decimal('0.00')
    
    def clean_sale_discount(self):
        value = self.cleaned_data.get('sale_discount')
        if value is not None and value != '':
            if isinstance(value, str):
                value = value.replace(',', '.')
            try:
                return Decimal(str(value))
            except (ValueError, InvalidOperation):
                return Decimal('0.00')
        return Decimal('0.00')
    
    def clean_sale_addition(self):
        value = self.cleaned_data.get('sale_addition')
        if value is not None and value != '':
            if isinstance(value, str):
                value = value.replace(',', '.')
            try:
                return Decimal(str(value))
            except (ValueError, InvalidOperation):
                return Decimal('0.00')
        return Decimal('0.00')
    
    def clean_paid_amount(self):
        value = self.cleaned_data.get('paid_amount')
        if value is not None and value != '':
            if isinstance(value, str):
                value = value.replace(',', '.')
            try:
                return Decimal(str(value))
            except (ValueError, InvalidOperation):
                return Decimal('0.00')
        return Decimal('0.00')


class SaleItemForm(forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = [
            'product', 'item_name', 'sold_quantity', 
            # ✅✅✅ تم حذف quantity_with_barcode و quantity_without_barcode
            # لأنها تُحسب آلياً في العرض (view) من بيانات الباركود
            'unit_price', 'notes', 'sale_item_image'
        ]
        widgets = {
            'product': forms.HiddenInput(),
            'item_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'اسم المادة'
            }),
            'sold_quantity': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'min': '0.01'
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'min': '0'
            }),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
            'sale_item_image': forms.FileInput(attrs={'class': 'd-none'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sale_item_image'].required = False
    
    def clean_sold_quantity(self):
        value = self.cleaned_data.get('sold_quantity')
        if value is not None:
            if isinstance(value, str):
                value = value.replace(',', '.')
            try:
                return Decimal(str(value))
            except (ValueError, InvalidOperation):
                return Decimal('1.00')
        return Decimal('1.00')
    
    def clean_unit_price(self):
        value = self.cleaned_data.get('unit_price')
        if value is not None:
            if isinstance(value, str):
                value = value.replace(',', '.')
            try:
                return Decimal(str(value))
            except (ValueError, InvalidOperation):
                return Decimal('0.00')
        return Decimal('0.00')

class SaleItemBarcodeForm(forms.ModelForm):
    class Meta:
        model = SaleItemBarcode
        fields = ['barcode', 'quantity_used', 'barcode_status']
        widgets = {
            'quantity_used': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'min': '0.01'
            }),
            'barcode_status': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['barcode'].widget.attrs.update({'class': 'form-control select2'})


class CashTransactionForm(forms.ModelForm):
    class Meta:
        model = CashTransaction
        fields = ['transaction_type', 'amount_in', 'amount_out', 'notes']
        widgets = {
            'transaction_type': forms.HiddenInput(),
            'amount_in': forms.NumberInput(attrs={
                'class': 'form-control amount-input', 
                'step': '0.01', 
                'min': '0', 
                'placeholder': '0.00'
            }),
            'amount_out': forms.NumberInput(attrs={
                'class': 'form-control amount-input', 
                'step': '0.01', 
                'min': '0', 
                'placeholder': '0.00'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'أدخل ملاحظات الحركة هنا...'
            }),
        }

SaleItemFormSet = inlineformset_factory(
    Sale,
    SaleItem,
    form=SaleItemForm,
    extra=1,
    can_delete=True,
    can_order=False
)

SaleItemBarcodeFormSet = inlineformset_factory(
    SaleItem,
    SaleItemBarcode,
    form=SaleItemBarcodeForm,
    extra=1,
    can_delete=True,
    can_order=False
)




#===============================================
#       مرتجع المبيعات 
# ==============================================





class SaleReturnForm(forms.ModelForm):
    class Meta:
        model = SaleReturn
        fields = [
            'original_sale', 'return_date', 'return_reason', 'return_invoice_number',
            'return_payment_method', 'return_notes', 'return_currency',
            'return_status', 'return_image', 
            'paid_amount',
            'return_subtotal', 'return_tax_amount', 'return_final_total'
        ]
        widgets = {
            'original_sale': forms.HiddenInput(),
            'return_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'return_reason': forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'أدخل سبب الإرجاع...'}),
            'return_notes': forms.Textarea(attrs={'rows': 1, 'class': 'form-control'}),
            'return_invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'return_image': forms.FileInput(attrs={'class': 'd-none'}),
            
            'paid_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
                'placeholder': '0.00', 'id': 'paid-amount'
            }),
            'return_subtotal': forms.HiddenInput(),
            'return_tax_amount': forms.HiddenInput(),
            'return_final_total': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['original_sale'].required = False
        for field_name in ['return_payment_method', 'return_currency', 'return_status']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})
        
        self.fields['paid_amount'].required = False


class SaleReturnItemForm(forms.ModelForm):
    class Meta:
        model = SaleReturnItem
        fields = [
            'original_sale_item', 'product', 'item_name', 'returned_quantity',
            'quantity_with_barcode', 'quantity_without_barcode',
            'unit_price', 'notes', 'return_item_image'
        ]
        widgets = {
            'original_sale_item': forms.HiddenInput(),
            'product': forms.HiddenInput(),
            'item_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المادة'}),
            # تم إضافة كلاسات مميزة ليسهل التعامل معها في الجافاسكربت
            'returned_quantity': forms.NumberInput(attrs={'class': 'form-control returned-qty-input', 'step': '0.01', 'min': '0.01'}),
            'quantity_with_barcode': forms.HiddenInput(),
            'quantity_without_barcode': forms.HiddenInput(),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control unit-price-input', 'step': '0.01', 'min': '0', 'readonly': 'readonly'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
            'return_item_image': forms.FileInput(attrs={'class': 'd-none'}),
        }


class SaleReturnItemBarcodeForm(forms.ModelForm):
    class Meta:
        model = SaleReturnItemBarcode
        fields = ['barcode', 'quantity_used', 'barcode_status']
        widgets = {
            'barcode': forms.Select(attrs={'class': 'form-control select2'}),
            'quantity_used': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'min': '0.01'
            }),
            'barcode_status': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['barcode'].widget.attrs.update({'class': 'form-control select2'})


SaleReturnItemFormSet = inlineformset_factory(
    SaleReturn,
    SaleReturnItem,
    form=SaleReturnItemForm,
    extra=0, 
    can_delete=True
)

SaleReturnItemBarcodeFormSet = inlineformset_factory(
    SaleReturnItem,
    SaleReturnItemBarcode,
    form=SaleReturnItemBarcodeForm,
    extra=1,
    can_delete=True
)

#===============================================
#        الجداول المساعدة 
# ==============================================



class CurrencyForm(forms.ModelForm):
    class Meta:
        model = Currency
        fields = ['code', 'symbol', 'name', 'name_ar', 'singular_ar', 'dual_ar', 
                 'plural_ar', 'fraction_name_ar', 'fraction_dual_ar', 'fraction_plural_ar',
                 'exchange_rate', 'decimals', 'is_default', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('مثال: USD')}),
            'symbol': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('مثال: $')}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Dollar')}),
            'name_ar': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('دولار')}),
            'singular_ar': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('دولار')}),
            'dual_ar': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('دولاران')}),
            'plural_ar': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('دولارات')}),
            'fraction_name_ar': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('سنت')}),
            'fraction_dual_ar': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('سنتان')}),
            'fraction_plural_ar': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('سنتات')}),
            'exchange_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'min': '0'}),
            'decimals': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '4'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = Payment_method
        fields = ['name', 'notes', 'is_cash']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم طريقة الدفع')}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _('ملاحظات إضافية')}),
            'is_cash': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class ShippingCompanyForm(forms.ModelForm):
    class Meta:
        model = Shipping_com_m
        fields = ['name', 'contact_person', 'phone_number', 'email', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم شركة الشحن')}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('شخص الاتصال')}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('رقم الهاتف')}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': _('البريد الإلكتروني')}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('العنوان')}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _('ملاحظات إضافية')}),
        }

class StatusForm(forms.ModelForm):
    class Meta:
        model = Status
        fields = ['name', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم الحالة')}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _('ملاحظات إضافية')}),
        }

class PriceTypeForm(forms.ModelForm):
    class Meta:
        model = PriceType
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('نوع السعر')}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _('وصف نوع السعر')}),
        }




