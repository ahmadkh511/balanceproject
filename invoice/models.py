
# ==================== مكتبات النظام الأساسية (Standard Library) ====================
import logging
import re
import uuid
from decimal import Decimal

# ==================== مكتبات خارجية (Third-party) ====================
from num2words import num2words

# ==================== مكتبات Django ====================
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum, F
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)
User = get_user_model()




#================================================
#  الصندوق
# ===============================================



class CashTransaction(models.Model):
    """نموذج لتسجيل جميع حركات الصندوق"""
    TRANSACTION_TYPES = (
        ('purchase_payment', 'دفع مشتريات'),
        ('sale_receipt', 'تحصيل مبيعات'),
        ('purchase_return', 'مرتجع مشتريات'),
        ('sale_return', 'مرتجع مبيعات'),
        ('expense', 'مصروفات تشغيلية'),
        ('deposit', 'إيداع في الصندوق'),
        ('withdrawal', 'سحب من الصندوق'),
    )

    transaction_date = models.DateTimeField(default=timezone.now, verbose_name=_("تاريخ العملية"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("ملاحظات العملية"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                  null=True, blank=True, verbose_name=_("أجرى العملية"))

    amount_in = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), 
                                   verbose_name=_("المبلغ الداخل"))
    amount_out = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), 
                                    verbose_name=_("المبلغ الخارج"))

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, 
                                       verbose_name=_("نوع العملية"))
    payment_method = models.ForeignKey('Payment_method', on_delete=models.SET_NULL, 
                                      null=True, blank=True, verbose_name=_("طريقة الدفع"))
    
    purchase_invoice = models.ForeignKey('Purch', on_delete=models.SET_NULL, 
                                        null=True, blank=True, related_name="cash_transactions",
                                        verbose_name=_("فاتورة المشتريات المرتبطة"))
    
    sale_invoice = models.ForeignKey('Sale', on_delete=models.SET_NULL, 
                                    null=True, blank=True, related_name="cash_transactions",
                                    verbose_name=_("فاتورة المبيعات المرتبطة"))

    sale_return = models.ForeignKey('SaleReturn', on_delete=models.SET_NULL, 
                                    null=True, blank=True, related_name="cash_transactions",
                                    verbose_name=_("مرتجع المبيعات المرتبط"))
    
    purchase_return = models.ForeignKey('PurchaseReturn', on_delete=models.SET_NULL, 
                                        null=True, blank=True, related_name="cash_transactions",
                                        verbose_name=_("مرتجع المشتريات المرتبط"))

    class Meta:
        verbose_name = _("حركة صندوق")
        verbose_name_plural = _("حركات الصندوق")
        ordering = ["-transaction_date"]

    def __str__(self):
        direction = "داخل" if self.amount_in > 0 else "خارج"
        amount = self.amount_in if self.amount_in > 0 else self.amount_out
        return f"{self.get_transaction_type_display()} - {amount} ({direction})"

    def clean(self):
        if self.amount_in > 0 and self.amount_out > 0:
            raise ValidationError(_("لا يمكن أن يكون المبلغ الداخل والخارج أكبر من صفر في نفس العملية."))
        if self.amount_in <= 0 and self.amount_out <= 0:
            raise ValidationError(_("يجب أن يكون إما المبلغ الداخل أو الخارج أكبر من صفر."))
        
        if self.transaction_type in ['withdrawal', 'expense'] and not self.payment_method:
            cash_payment_method, _ = Payment_method.objects.get_or_create(name='نقداً')
            self.payment_method = cash_payment_method

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_cash_balance(cls):
        total_in = cls.objects.aggregate(total=Sum('amount_in'))['total'] or Decimal('0.00')
        total_out = cls.objects.aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')
        return total_in - total_out

    # ★★★ الدالة الجديدة: جلب اسم الطرف الآخر في الحركة ★★★
    def get_partner_name(self):
        """
        جلب اسم الطرف الآخر في الحركة (عميل، مورد، مستفيد)
        """
        # 1. حالة تحصيل مبيعات (sale_receipt)
        if self.transaction_type == 'sale_receipt' and self.sale_invoice:
            customer = self.sale_invoice.sale_customer
            if customer:
                return customer.get_full_name() or customer.username
        
        # 2. حالة مرتجع مبيعات (sale_return)
        elif self.transaction_type == 'sale_return' and self.sale_return:
            original_sale = self.sale_return.original_sale
            if original_sale and original_sale.sale_customer:
                customer = original_sale.sale_customer
                return customer.get_full_name() or customer.username
        
        # 3. حالة دفع مشتريات (purchase_payment)
        elif self.transaction_type == 'purchase_payment' and self.purchase_invoice:
            supplier = self.purchase_invoice.purch_supplier
            if supplier:
                return supplier.get_full_name() or supplier.username
        
        # 4. حالة مرتجع مشتريات (purchase_return)
        elif self.transaction_type == 'purchase_return' and self.purchase_return:
            original_purch = self.purchase_return.original_purchase
            if original_purch and original_purch.purch_supplier:
                supplier = original_purch.purch_supplier
                return supplier.get_full_name() or supplier.username
        
        # 5. للحالات اليدوية (expense, withdrawal, deposit)
        #    نحاول استخراج اسم من الملاحظات
        if self.notes:
            import re
            # أنماط شائعة: "لـ أحمد", "لصالح محمد", "إلى علي", "من خالد"
            match = re.search(r'(?:لـ|لصالح|إلى|من)\s*([^\s]+)', self.notes)
            if match:
                return match.group(1)
        
        # 6. إذا لم نجد طرفاً آخر
        return "—"


#================================================
#  اعدادات الايمل 
# ===============================================

class EmailSetting(models.Model):
    email_backend = models.CharField(max_length=255, default='django.core.mail.backends.smtp.EmailBackend', verbose_name="Email Backend")
    email_host = models.CharField(max_length=255, verbose_name="SMTP Host")
    email_port = models.PositiveIntegerField(default=587, verbose_name="Port")
    email_use_tls = models.BooleanField(default=True, verbose_name="Use TLS")
    email_host_user = models.EmailField(verbose_name="Email Address")
    email_host_password = models.CharField(max_length=255, verbose_name="Email Password")
    default_from_email = models.EmailField(verbose_name="Default From Email")

    class Meta:
        verbose_name = "Email Setting"
        verbose_name_plural = "Email Settings"

    def __str__(self):
        return "Email Configuration"

    def clean(self):
        if not self.pk and EmailSetting.objects.exists():
            raise ValidationError("You can only have one Email Setting instance.")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


# ================ نماذج الأنظمة الأساسية ================

class Currency(models.Model):
    code = models.CharField(max_length=3, unique=True, verbose_name=_("كود العملة"))
    symbol = models.CharField(max_length=10, verbose_name=_("رمز العملة"))
    name = models.CharField(max_length=100, verbose_name=_("الاسم بالإنجليزية"))
    name_ar = models.CharField(max_length=100, verbose_name=_("الاسم بالعربية"))
    singular_ar = models.CharField(max_length=100, verbose_name=_("المفرد بالعربية"), default="")
    dual_ar = models.CharField(max_length=100, verbose_name=_("المثنى بالعربية"), default="")
    plural_ar = models.CharField(max_length=100, verbose_name=_("الجمع بالعربية"), default="")
    fraction_name_ar = models.CharField(max_length=100, verbose_name=_("اسم الكسر"), default="")
    fraction_dual_ar = models.CharField(max_length=100, verbose_name=_("مثنى الكسر"), default="")
    fraction_plural_ar = models.CharField(max_length=100, verbose_name=_("جمع الكسر"), default="")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('1.0000'), verbose_name=_("سعر الصرف"))
    decimals = models.PositiveSmallIntegerField(default=2, verbose_name=_("المنازل العشرية"))
    is_default = models.BooleanField(default=False, verbose_name=_("العملة الأساسية"))
    is_active = models.BooleanField(default=True, verbose_name=_("نشط"))
    
    class Meta:
        verbose_name = _("عملة")
        verbose_name_plural = _("العملات")
        ordering = ['code']
    
    def __str__(self):
        return f"{self.name_ar} ({self.code})"
    
    def save(self, *args, **kwargs):
        if not self.singular_ar: self.singular_ar = self.name_ar
        if not self.dual_ar:
            self.dual_ar = self.singular_ar[:-1] + "تان" if self.singular_ar.endswith('ة') else self.singular_ar + "ان"
        if not self.plural_ar:
            self.plural_ar = self.singular_ar[:-1] + "ات" if self.singular_ar.endswith('ة') else self.singular_ar + "ات"
        
        if not self.fraction_name_ar:
            self.fraction_name_ar = {'SYP': 'قرش', 'SAR': 'هللة'}.get(self.code, "جزء")
        if not self.fraction_dual_ar: self.fraction_dual_ar = self.fraction_name_ar + "ان"
        if not self.fraction_plural_ar: self.fraction_plural_ar = self.fraction_name_ar + "ات"
        
        if self.is_default:
            Currency.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class Payment_method(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name=_("الاسم"))
    notes = models.TextField(blank=True, verbose_name=_("ملاحظات"))
    uniqueId = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name=_("الرقم المسلسل"))
    slug = models.SlugField(max_length=225, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))
    is_cash = models.BooleanField(default=False, verbose_name=_("هل هي طريقة دفع نقدية؟"))
    
    class Meta:
        verbose_name = _("طريقة دفع")
        verbose_name_plural = _("طرق الدفع")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.uniqueId: self.uniqueId = str(uuid.uuid4()).replace('-', '')[:10]
        if not self.slug:
            base_slug = slugify(self.name)
            unique_slug, num = base_slug, 1
            while Payment_method.objects.filter(slug=unique_slug).exists():
                unique_slug, num = f"{base_slug}-{num}", num + 1
            self.slug = unique_slug
        super().save(*args, **kwargs)


class Shipping_com_m(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name=_("الاسم"))
    contact_person = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("شخص الاتصال"))
    phone_number = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("رقم الهاتف"))
    email = models.EmailField(max_length=255, blank=True, null=True, verbose_name=_("البريد الإلكتروني"))
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("العنوان"))
    notes = models.TextField(blank=True, verbose_name=_("ملاحظات"))
    uniqueId = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name=_("الرقم المسلسل"))
    slug = models.SlugField(max_length=225, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))

    class Meta:
        verbose_name = _("شركة شحن")
        verbose_name_plural = _("شركات الشحن")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.uniqueId: self.uniqueId = str(uuid.uuid4()).replace('-', '')[:10]
        if not self.slug:
            base_slug = slugify(self.name)
            unique_slug, num = base_slug, 1
            while Shipping_com_m.objects.filter(slug=unique_slug).exists():
                unique_slug, num = f"{base_slug}-{num}", num + 1
            self.slug = unique_slug
        super().save(*args, **kwargs)


class Status(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name=_("الاسم"))
    notes = models.TextField(blank=True, verbose_name=_("ملاحظات"))
    uniqueId = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name=_("الرقم المسلسل"))
    slug = models.SlugField(max_length=225, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))

    class Meta:
        verbose_name = _("حالة")
        verbose_name_plural = _("الحالات")
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.uniqueId: self.uniqueId = str(uuid.uuid4()).replace('-', '')[:10]
        if not self.slug:
            base_slug = slugify(self.name)
            unique_slug, num = base_slug, 1
            while Status.objects.filter(slug=unique_slug).exists():
                unique_slug, num = f"{base_slug}-{num}", num + 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

    def __str__(self): return self.name


class PriceType(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("نوع السعر"))
    description = models.TextField(blank=True, null=True, verbose_name=_("الوصف"))
    uniqueId = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name=_("الرقم المسلسل"))
    slug = models.SlugField(max_length=225, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))

    class Meta:
        verbose_name = _('نوع السعر')
        verbose_name_plural = _('أنواع الأسعار')
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.uniqueId: self.uniqueId = str(uuid.uuid4()).replace('-', '')[:10]
        if not self.slug:
            base_slug = slugify(self.name)
            unique_slug, num = base_slug, 1
            while PriceType.objects.filter(slug=unique_slug).exists():
                unique_slug, num = f"{base_slug}-{num}", num + 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

    def __str__(self): return self.name


#================================================
#  المشتريات 
# ===============================================


class Purch(models.Model):
    uniqueId = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name=_("الرقم المسلسل"))
    slug = models.SlugField(max_length=225, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))
    _last_invoice_number = models.IntegerField(default=0, editable=False)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchases_created', verbose_name=_("تم الإنشاء بواسطة"))
    purch_supplier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_purchases', verbose_name=_("المورد"))
    
    purch_date = models.DateField(blank=True, null=True, verbose_name=_("تاريخ فاتورة الشراء"))
    purch_supplier_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("هاتف المورد"))
    purch_address = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("عنوان المورد"))
    supplier_invoice_number = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("رقم فاتورة المورد"))
    purch_delivery_method = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("طريقة التسليم"))
    purch_delivery_tracking_number = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("رقم تتبع الشحنة"))
    purch_payment_method = models.ForeignKey('Payment_method', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("طريقة الدفع"))
    purch_notes = models.TextField(max_length=200, blank=True, verbose_name=_("ملاحظات الفاتورة"))
    purch_currency = models.ForeignKey('Currency', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("العملة"))
    purch_invoice_date = models.DateField(blank=True, null=True, verbose_name=_("تاريخ الفاتورة (من المورد)"))
    purch_type = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("نوع الشراء"))
    purch_status = models.ForeignKey('Status', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("حالة الفاتورة"))
    purch_shipping_company = models.ForeignKey('Shipping_com_m', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("شركة الشحن"))
    purch_shipping_num = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("رقم الشحنة"))
    purch_due_date = models.DateField(blank=True, null=True, verbose_name=_("تاريخ الاستحقاق"))
    purch_image = models.ImageField(upload_to='purch_invoice_images/%y/%m/%d/', blank=True, null=True, verbose_name=_("صورة الفاتورة"))
    
    purch_tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_("نسبة الضريبة (%)"))
    purch_discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("قيمة الخصم"))
    purch_addition = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("قيمة الإضافة"))
    
    purch_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("إجمالي البنود"))
    purch_tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("قيمة الضريبة"))
    purch_final_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("الإجمالي النهائي"))
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("المبلغ المتبقي"))
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("المبلغ المدفوع"))
    is_paid = models.BooleanField(default=False, verbose_name=_("تم الدفع بالكامل"))
    
    class Meta:
        verbose_name = _("فاتورة شراء")
        verbose_name_plural = _("فواتير الشراء")
        ordering = ["-date_created"]
    
    def __str__(self):
        return f"فاتورة شراء {self.uniqueId}"
    
    def save(self, *args, **kwargs):
        if not self.purch_date: self.purch_date = timezone.now().date()
        if not self.purch_invoice_date: self.purch_invoice_date = self.purch_date
        
        if not self.uniqueId:
            last_invoice = Purch.objects.order_by('-_last_invoice_number').first()
            new_number = (last_invoice._last_invoice_number if last_invoice else 0) + 1
            self._last_invoice_number = new_number
            self.uniqueId = f"P{new_number:04d}"
        
        if not self.slug:
            self.slug = slugify(f"purch-{self.uniqueId}")
        
        super().save(*args, **kwargs)
    
    def get_amount_parts(self):
        if not self.purch_final_total: return 0, 0
        amount = float(self.purch_final_total)
        decimals = self.get_currency_info().get('decimals', 2)
        integer_part = int(amount)
        fractional_part = int(round((amount - integer_part) * (10 ** decimals)))
        return integer_part, fractional_part
    
    @property
    def total_in_words(self): return self.get_total_in_words()
    
    def get_total_in_words(self):
        if not self.purch_final_total: return ""
        try:
            currency_info = self.get_currency_info()
            integer_part, fractional_part = self.get_amount_parts()
            
            integer_words = num2words(integer_part, lang='ar')
            currency_word = currency_info['singular'] if integer_part <= 2 else currency_info['plural']
            result = f"{integer_words} {currency_word}".strip()
            
            if fractional_part > 0:
                fraction_words = num2words(fractional_part, lang='ar')
                fraction_currency = currency_info['fraction_dual'] if fractional_part == 2 else currency_info['fraction_plural'] if fractional_part > 10 else currency_info['fraction']
                result += f" و{fraction_words} {fraction_currency}" if integer_part != 0 else f"{fraction_words} {fraction_currency}"
            
            return result + " فقط لا غير"
        except Exception as e:
            logger.error(f"خطأ في تحويل المبلغ إلى كلمات: {e}", exc_info=True)
            return f"{self.purch_final_total} ليرة سورية فقط لا غير"
    
    def get_currency_info(self):
        if not self.purch_currency:
            return {'singular': 'ليرة سورية', 'dual': 'ليرتان سوريتان', 'plural': 'ليرات سورية', 'fraction': 'قرش', 'fraction_dual': 'قرشان', 'fraction_plural': 'قروش', 'decimals': 2}
        return {'singular': self.purch_currency.singular_ar, 'dual': self.purch_currency.dual_ar, 'plural': self.purch_currency.plural_ar, 'fraction': self.purch_currency.fraction_name_ar, 'fraction_dual': self.purch_currency.fraction_dual_ar, 'fraction_plural': self.purch_currency.fraction_plural_ar, 'decimals': self.purch_currency.decimals}
    
    def calculate_and_save_totals(self):
        try:
            self.purch_subtotal = self.purchitem_set.aggregate(total_sum=Sum('purch_total'))['total_sum'] or Decimal('0.00')
            self.purch_tax_amount = (self.purch_subtotal * (self.purch_tax_percentage / Decimal('100.00'))).quantize(Decimal('0.01'))
            self.purch_final_total = self.purch_subtotal + self.purch_tax_amount + self.purch_addition - self.purch_discount
            self.balance_due = max(self.purch_final_total - self.paid_amount, Decimal('0.00'))
            self.is_paid = self.paid_amount >= self.purch_final_total
            super().save(update_fields=['purch_subtotal', 'purch_tax_amount', 'purch_final_total', 'balance_due', 'is_paid', 'purch_tax_percentage', 'purch_discount', 'purch_addition', 'paid_amount'])
        except Exception as e:
            logger.error(f"خطأ في حساب الإجماليات المالية: {e}")
            raise
    
    def update_financial_fields(self, tax_percentage, discount, addition, paid_amount):
        self.purch_tax_percentage, self.purch_discount = Decimal(str(tax_percentage)), Decimal(str(discount))
        self.purch_addition, self.paid_amount = Decimal(str(addition)), Decimal(str(paid_amount))
        self.calculate_and_save_totals()
    
    # ★★★ الدالة الوحيدة المعدلة في هذا الكلاس ★★★
    def create_cash_transaction(self):
        """
        إنشاء أو تحديث أو حذف حركة الصندوق المرتبطة بفاتورة الشراء.
        
        القاعدة الموحدة بين مساري الإنشاء والتعديل:
        - دفع نقدي بمبلغ أكبر من صفر → إنشاء الحركة أو تحديث مبلغها
        - أي حالة أخرى (آجل، أو مدفوع صفر) → حذف أي حركة قديمة بدل تركها صفرية
        
        ملاحظة تاريخية: الكود القديم كان عند التحويل إلى آجل يحدّث الحركة بمبلغ صفر،
        فترفضها clean() في CashTransaction (داخل=صفر وخارج=صفر) ويفشل الحفظ كلياً.
        """
        existing_transaction = CashTransaction.objects.filter(
            purchase_invoice=self, transaction_type='purchase_payment'
        ).first()

        is_cash = self.purch_payment_method and self.purch_payment_method.is_cash
        should_have_transaction = is_cash and self.paid_amount > 0

        if should_have_transaction:
            if not existing_transaction:
                CashTransaction.objects.create(
                    transaction_date=timezone.now(),
                    amount_out=self.paid_amount,
                    transaction_type='purchase_payment',
                    payment_method=self.purch_payment_method,
                    purchase_invoice=self,
                    notes=f"دفعة مقابل فاتورة شراء {self.uniqueId}",
                    created_by=self.created_by
                )
            elif existing_transaction.amount_out != self.paid_amount:
                existing_transaction.amount_out = self.paid_amount
                existing_transaction.save()
        elif existing_transaction:
            # تحولت الفاتورة إلى آجل أو أصبح المدفوع صفراً → حذف الحركة
            existing_transaction.delete()

    @property
    def total_items_count(self):
        return self.purchitem_set.count() if self.pk else 0
    
    @property
    def total_quantity_purchased(self):
        return self.purchitem_set.aggregate(total_qty=Sum('purchased_quantity'))['total_qty'] or Decimal('0.00') if self.pk else Decimal('0.00')

    @property
    def has_return(self):
        return self.purchase_returns.exists()


class PurchItem(models.Model):
    purch = models.ForeignKey('Purch', on_delete=models.CASCADE, verbose_name=_("فاتورة الشراء"))
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='purch_items', verbose_name=_("المنتج المرتبط"))
    item_name = models.CharField(max_length=255, blank=True, verbose_name=_("اسم المادة"))
    purchased_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), verbose_name=_("الكمية المشتراة"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("سعر الوحدة"))
    notes = models.CharField(max_length=255, blank=True, verbose_name=_("ملاحظات"))
    purch_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("إجمالي البند"))
    purch_currency = models.ForeignKey("Currency", on_delete=models.PROTECT, related_name='purch_items_by_currency', verbose_name=_("عملة الشراء لهذا البند"), null=True, blank=True)
    exchange_rate_at_purchase = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('1.00'), verbose_name=_("سعر الصرف وقت الشراء"))
    unit_price_base_currency = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("سعر الوحدة (بالعملة الأساسية)"))
    purch_item_image = models.ImageField(upload_to='purch_items_image/%y/%m/%d/', max_length=100, blank=True, null=True, verbose_name=_("صورة المادة"))
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))

    class Meta:
        verbose_name = _("بند فاتورة الشراء")
        verbose_name_plural = _("بنود فواتير الشراء")
        ordering = ["id"]

    def __str__(self):
        name = self.product.product_name if self.product else self.item_name
        return f"{name} - {self.purchased_quantity} × {self.unit_price} = {self.purch_total}"
    
    def save(self, *args, **kwargs):
        if not self.item_name: self.item_name = self.product.product_name if self.product else "مادة غير محددة"
        if self.purchased_quantity and self.unit_price:
            self.purch_total = (self.purchased_quantity * self.unit_price).quantize(Decimal('0.01'))
        self.unit_price_base_currency = self.unit_price
        super().save(*args, **kwargs)
    
    def update_product_stock(self, old_quantity=None, old_product=None):
        try:
            if not self.product: return
            product = self.product
            product.refresh_from_db()

            if old_quantity is not None and old_product is not None:
                if old_product and product.id == old_product.id:
                    quantity_difference = self.purchased_quantity - Decimal(str(old_quantity))
                    # استخدام F() لمنع تزامن المخزون
                    product.current_stock_quantity = F('current_stock_quantity') + quantity_difference
                    product.save(update_fields=['current_stock_quantity'])
                    product.refresh_from_db()
                    
                    if quantity_difference > 0 and product.current_stock_quantity > 0:
                        old_total_value = (product.current_stock_quantity - quantity_difference) * product.average_purchase_cost
                        new_total_value = old_total_value + (quantity_difference * self.unit_price_base_currency)
                        product.average_purchase_cost = (new_total_value / product.current_stock_quantity).quantize(Decimal('0.01'))
                        product.save()
                else:
                    if old_product:
                        old_product.current_stock_quantity = F('current_stock_quantity') - Decimal(str(old_quantity))
                        old_product.save(update_fields=['current_stock_quantity'])
                    product.current_stock_quantity = F('current_stock_quantity') + self.purchased_quantity
                    product.save(update_fields=['current_stock_quantity'])
                    product.refresh_from_db()
                    product.average_purchase_cost = self.unit_price_base_currency
                    product.save()
            else:
                product.current_stock_quantity = F('current_stock_quantity') + self.purchased_quantity
                product.save(update_fields=['current_stock_quantity'])
                product.refresh_from_db()
                
                if product.current_stock_quantity > 0:
                    old_total_value = (product.current_stock_quantity - self.purchased_quantity) * product.average_purchase_cost
                    new_total_value = old_total_value + (self.purchased_quantity * self.unit_price_base_currency)
                    product.average_purchase_cost = (new_total_value / product.current_stock_quantity).quantize(Decimal('0.01'))
                    product.save()

            product.last_operation_type = 'purchase'
            product.save(update_fields=['last_operation_type'])
            logger.info(f"✅ تم تحديث مخزون المنتج {product.product_name}")
                
        except Exception as e:
            logger.error(f"❌ خطأ في تحديث المخزون: {e}", exc_info=True)

    def delete(self, *args, **kwargs):
        try:
            if self.product:
                self.product.current_stock_quantity = F('current_stock_quantity') - self.purchased_quantity
                self.product.save(update_fields=['current_stock_quantity'])
                logger.info(f"↩️ تم التراجع عن مخزون المنتج بعد الحذف")
            super().delete(*args, **kwargs)
        except Exception as e:
            logger.error(f"❌ خطأ في حذف البند: {e}")
            raise


class PurchItemBarcode(models.Model):
    purch_item = models.ForeignKey('PurchItem', on_delete=models.CASCADE, related_name='item_barcodes', verbose_name=_("بند الشراء"))
    barcode = models.ForeignKey('Barcode', on_delete=models.CASCADE, related_name='purch_items', verbose_name=_("الباركود"))
    quantity_used = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), verbose_name=_("الكمية المرتبطة"))
    barcode_status = models.CharField(max_length=20, choices=[('active', 'نشط'), ('returned', 'مرتجع'), ('damaged', 'تالف')], default='active', verbose_name=_("حالة الباركود في الفاتورة"))
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))

    class Meta:
        verbose_name = _("باركود بند الشراء")
        verbose_name_plural = _("باركودات بنود الشراء")
        unique_together = ('purch_item', 'barcode')
        ordering = ['-date_created']

    def __str__(self):
        return f"{self.purch_item.item_name} - {self.barcode.barcode_in}"

    def save(self, *args, **kwargs):
        self.barcode_status = self.barcode_status or 'active'
        self.barcode.status = self.barcode_status
        self.barcode.save(update_fields=['status'])
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        barcode_to_check = self.barcode
        super().delete(*args, **kwargs)
        if not PurchItemBarcode.objects.filter(barcode=barcode_to_check).exists():
            if not barcode_to_check.sale_items.exists() and not hasattr(barcode_to_check, 'inventory_items'):
                barcode_to_check.delete()


#================================================
#           مرتجع المشتريات 
# ===============================================


class PurchaseReturn(models.Model):
    SETTLEMENT_STATUS = (('pending', 'في انتظار الاستلام'), ('partial', 'تم الاستلام جزئياً'), ('settled', 'تم الاستلام كاملاً'))
    
    original_purchase = models.ForeignKey('Purch', on_delete=models.CASCADE, related_name='purchase_returns', verbose_name=_("فاتورة الشراء الأصلية"))
    uniqueId = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name=_("الرقم المسلسل"))
    slug = models.SlugField(max_length=225, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))
    _last_return_number = models.IntegerField(default=0, editable=False)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='returns_created', verbose_name=_("تم الإنشاء بواسطة"))
    return_date = models.DateField(default=timezone.now, verbose_name=_("تاريخ المرتجع"))
    return_notes = models.TextField(max_length=500, blank=True, verbose_name=_("ملاحظات المرتجع"))
    purch_supplier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_returns', verbose_name=_("المورد"))
    purch_currency = models.ForeignKey('Currency', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("العملة"))
    
    return_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("إجمالي بنود المرتجع"))
    return_tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("قيمة الضريبة المعادة"))
    return_final_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("الإجمالي النهائي للمرتجع"))
    
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("المبلغ المستلم من المورد"))
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("المبلغ المتبقي للمورد"))
    settlement_status = models.CharField(max_length=20, choices=SETTLEMENT_STATUS, default='pending', verbose_name=_("حالة التسوية المالية"))

    class Meta:
        verbose_name = _("فاتورة مرتجع شراء")
        verbose_name_plural = _("فواتير مرتجع الشراء")
        ordering = ["-date_created"]
    
    def __str__(self):
        return f"مرتجع شراء {self.uniqueId} لفاتورة {self.original_purchase.uniqueId}"
    
    def save(self, *args, **kwargs):
        if not self.uniqueId:
            # ★ الإصلاح: استخدام aggregate بدل order_by (أكثر أماناً)
            from django.db.models import Max
            last_number = PurchaseReturn.objects.aggregate(
                max_num=Max('_last_return_number')
            )['max_num'] or 0
            new_number = last_number + 1
            
            # ★ حماية إضافية: التأكد أن الرقم غير مستخدم (بسبب الأخطاء السابقة)
            while PurchaseReturn.objects.filter(uniqueId=f"PR{new_number:05d}").exists():
                new_number += 1
            
            # ★ الإصلاح: استخدام اسم الحقل الصحيح _last_return_number
            self._last_return_number = new_number
            self.uniqueId = f"PR{new_number:05d}"
        
        if not self.slug: 
            self.slug = slugify(f"purchase-return-{self.uniqueId}")
        
        if self.original_purchase:
            if not self.purch_supplier: 
                self.purch_supplier = self.original_purchase.purch_supplier
            if not self.purch_currency and hasattr(self.original_purchase, 'purch_currency'): 
                self.purch_currency = self.original_purchase.purch_currency
        
        self.remaining_amount = self.return_final_total - self.paid_amount
        self.update_settlement_status()
        super().save(*args, **kwargs)

    def calculate_and_save_totals(self):
        try:
            self.return_subtotal = self.return_items.aggregate(total_sum=Sum('return_total'))['total_sum'] or Decimal('0.00')
            self.return_final_total = self.return_subtotal
            self.remaining_amount = self.return_final_total - self.paid_amount
            self.save(update_fields=['return_subtotal', 'return_final_total', 'remaining_amount'])
            return True
        except Exception as e:
            logger.error(f"خطأ في حساب إجماليات المرتجع {self.uniqueId}: {e}")
            return False

    def update_settlement_status(self):
        if self.remaining_amount <= 0: 
            self.settlement_status = 'settled'
        elif self.paid_amount > 0: 
            self.settlement_status = 'partial'
        else: 
            self.settlement_status = 'pending'
    
    def get_available_items_for_return(self):
        items_data = []
        if not self.original_purchase: return items_data
        for original_item in self.original_purchase.purchitem_set.all():
            total_returned = original_item.returned_items.aggregate(total=Sum('returned_quantity'))['total'] or Decimal('0.00')
            available_quantity = original_item.purchased_quantity - total_returned
            if available_quantity > 0:
                items_data.append({'original_item': original_item, 'available_quantity': available_quantity, 'previously_returned': total_returned})
        return items_data


class PurchaseReturnItem(models.Model):
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name='return_items', verbose_name=_("فاتورة المرتجع"))
    original_item = models.ForeignKey('PurchItem', on_delete=models.CASCADE, related_name='returned_items', verbose_name=_("بند الشراء الأصلي"))
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("المادة"))
    purchased_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_("الكمية الأساسية"))
    returned_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_("الكمية المرتجعة"))
    return_unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("سعر الوحدة"))
    return_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("إجمالي المرتجع للبند"))
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))

    class Meta:
        verbose_name = _("بند مرتجع الشراء")
        verbose_name_plural = _("بنود مرتجع الشراء")
        ordering = ["id"]

    def __str__(self):
        return f"مرتجع {self.product.product_name if self.product else 'غير محدد'} - {self.returned_quantity} × {self.return_unit_price}"

    def save(self, *args, **kwargs):
        if self.original_item:
            if not self.product: self.product = self.original_item.product
            if not self.purchased_quantity: self.purchased_quantity = self.original_item.purchased_quantity
            if not self.return_unit_price: self.return_unit_price = self.original_item.unit_price
        if self.returned_quantity and self.return_unit_price:
            self.return_total = (Decimal(str(self.returned_quantity)) * Decimal(str(self.return_unit_price))).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)
        
        if self.product and self.returned_quantity > Decimal('0.00'):
            try:
                self.product.current_stock_quantity = F('current_stock_quantity') - self.returned_quantity
                self.product.save(update_fields=['current_stock_quantity'])
            except Exception as e:
                logger.error(f"خطأ في تحديث المخزون: {e}")

    def delete(self, *args, **kwargs):
        if self.product and self.returned_quantity > Decimal('0.00'):
            self.product.current_stock_quantity = F('current_stock_quantity') + self.returned_quantity
            self.product.save(update_fields=['current_stock_quantity'])
        super().delete(*args, **kwargs)


class PurchaseReturnItemBarcode(models.Model):
    purchase_return_item = models.ForeignKey('PurchaseReturnItem', on_delete=models.CASCADE, related_name='returned_barcodes', verbose_name=_("بند المرتجع"))
    barcode = models.ForeignKey('Barcode', on_delete=models.CASCADE, related_name='purchase_return_items', verbose_name=_("الباركود المرتجع"))
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))

    class Meta:
        verbose_name = _("باركود بند المرتجع")
        verbose_name_plural = _("باركودات بنود المرتجع")
        unique_together = ('purchase_return_item', 'barcode')

    def __str__(self):
        return f"مرتجع: {self.barcode.barcode_in}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # ★ إصلاح مهم: حذف الباركود من بند الشراء المحدد فقط (وليس كل الفواتير)
        PurchItemBarcode.objects.filter(
            barcode=self.barcode,
            purch_item=self.purchase_return_item.original_item
        ).delete()
        
        if hasattr(self.barcode, 'status'):
            self.barcode.status = 'returned'
            self.barcode.save(update_fields=['status'])

    def delete(self, *args, **kwargs):
        original_item = self.purchase_return_item.original_item
        barcode_instance = self.barcode
        super().delete(*args, **kwargs)
        if original_item:
            PurchItemBarcode.objects.get_or_create(
                purch_item=original_item, 
                barcode=barcode_instance, 
                defaults={'barcode_status': 'active'}
            )
        if hasattr(barcode_instance, 'status'):
            barcode_instance.status = 'active'
            barcode_instance.save(update_fields=['status'])


#=========================================
#             المبيعات 
# ========================================

class Sale(models.Model):
    uniqueId = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name=_("الرقم المسلسل"))
    slug = models.SlugField(max_length=225, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))
    _last_invoice_number = models.IntegerField(default=0, editable=False)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_created', verbose_name=_("تم الإنشاء بواسطة"))
    sale_customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_sales', verbose_name=_("العميل"))
    sale_date = models.DateField(blank=True, null=True, verbose_name=_("تاريخ فاتورة البيع"))
    sale_customer_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("هاتف العميل"))
    sale_address = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("عنوان العميل"))
    sale_invoice_number = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("رقم الفاتورة"))
    sale_payment_method = models.ForeignKey('Payment_method', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("طريقة الدفع"))
    sale_notes = models.TextField(max_length=200, blank=True, verbose_name=_("ملاحظات الفاتورة"))
    sale_currency = models.ForeignKey('Currency', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("العملة"))
    sale_status = models.ForeignKey('Status', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("حالة الفاتورة"))
    sale_shipping_company = models.ForeignKey('Shipping_com_m', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("شركة الشحن"))
    sale_shipping_num = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("رقم الشحنة"))
    sale_image = models.ImageField(upload_to='sale_invoice_images/%y/%m/%d/', blank=True, null=True, verbose_name=_("صورة الفاتورة"))

    sale_tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_("نسبة الضريبة (%)"))
    sale_discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("قيمة الخصم"))
    sale_addition = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("قيمة الإضافة"))
    
    sale_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("إجمالي البنود"))
    sale_tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("قيمة الضريبة"))
    sale_final_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("الإجمالي النهائي"))
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("المبلغ المتبقي"))
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("المبلغ المدفوع"))
    is_paid = models.BooleanField(default=False, verbose_name=_("تم الدفع بالكامل"))
    
    class Meta:
        verbose_name = _("فاتورة بيع")
        verbose_name_plural = _("فواتير البيع")
        ordering = ["-date_created"]
    
    def __str__(self):
        return f"فاتورة بيع {self.uniqueId}"
    
    def save(self, *args, **kwargs):
        if not self.sale_date: self.sale_date = timezone.now().date()
        if not self.uniqueId:
            last_invoice = Sale.objects.order_by('-_last_invoice_number').first()
            new_number = (last_invoice._last_invoice_number if last_invoice else 0) + 1
            self._last_invoice_number = new_number
            self.uniqueId = f"S{new_number:04d}"
        if not self.slug: self.slug = slugify(f"sale-{self.uniqueId}")
        super().save(*args, **kwargs)

    def get_amount_parts(self):
        if not self.sale_final_total: return 0, 0
        amount = float(self.sale_final_total)
        decimals = self.get_currency_info().get('decimals', 2)
        return int(amount), int(round((amount - int(amount)) * (10 ** decimals)))
    
    @property
    def total_in_words(self): return self.get_total_in_words()
    
    def get_total_in_words(self):
        if not self.sale_final_total: return ""
        try:
            c = self.get_currency_info()
            ip, fp = self.get_amount_parts()
            iw = re.sub(r'واحد (ألف|مليون|مليار)', r'\1', num2words(ip, lang='ar'))
            cw = c['singular'] if ip <= 2 else c['plural']
            res = f"{iw} {cw}".strip()
            if fp > 0:
                fw = num2words(fp, lang='ar')
                fc = c['fraction_dual'] if fp == 2 else c['fraction_plural'] if fp > 10 else c['fraction']
                res += f" و{fw} {fc}" if ip != 0 else f"{fw} {fc}"
            return res + " فقط لا غير"
        except Exception as e:
            logger.error(f"خطأ في تحويل المبلغ: {e}")
            return f"{self.sale_final_total} ليرة سورية فقط لا غير"
    
    def get_currency_info(self):
        if not self.sale_currency:
            return {'singular': 'ليرة سورية', 'dual': 'ليرتان سوريتان', 'plural': 'ليرات سورية', 'fraction': 'قرش', 'fraction_dual': 'قرشان', 'fraction_plural': 'قروش', 'decimals': 2}
        return {'singular': self.sale_currency.singular_ar, 'dual': self.sale_currency.dual_ar, 'plural': self.sale_currency.plural_ar, 'fraction': self.sale_currency.fraction_name_ar, 'fraction_dual': self.sale_currency.fraction_dual_ar, 'fraction_plural': self.sale_currency.fraction_plural_ar, 'decimals': self.sale_currency.decimals}
    
    def calculate_and_save_totals(self):
        try:
            self.sale_subtotal = self.saleitem_set.aggregate(total_sum=Sum('sale_total'))['total_sum'] or Decimal('0.00')
            self.sale_tax_amount = (self.sale_subtotal * (self.sale_tax_percentage / Decimal('100.00'))).quantize(Decimal('0.01'))
            self.sale_final_total = self.sale_subtotal + self.sale_tax_amount + self.sale_addition - self.sale_discount
            self.balance_due = max(self.sale_final_total - self.paid_amount, Decimal('0.00'))
            self.is_paid = self.paid_amount >= self.sale_final_total
            super().save(update_fields=['sale_subtotal', 'sale_tax_amount', 'sale_final_total', 'balance_due', 'is_paid', 'sale_tax_percentage', 'sale_discount', 'sale_addition', 'paid_amount'])
        except Exception as e:
            logger.error(f"خطأ في حساب الإجماليات: {e}")
            raise
    
    def update_financial_fields(self, tax_percentage, discount, addition, paid_amount):
        self.sale_tax_percentage, self.sale_discount = Decimal(str(tax_percentage)), Decimal(str(discount))
        self.sale_addition, self.paid_amount = Decimal(str(addition)), Decimal(str(paid_amount))
        self.calculate_and_save_totals()
    
    def create_cash_transaction(self):
        existing = CashTransaction.objects.filter(sale_invoice=self, transaction_type='sale_receipt').first()
        if not existing and self.paid_amount > 0:
            CashTransaction.objects.create(transaction_date=timezone.now(), amount_in=self.paid_amount, transaction_type='sale_receipt', payment_method=self.sale_payment_method, sale_invoice=self, notes=f"تحصيل مقابل فاتورة بيع {self.uniqueId}", created_by=self.created_by)
        elif existing and existing.amount_in != self.paid_amount:
            existing.amount_in = self.paid_amount
            existing.save()

    @property
    def total_items_count(self): return self.saleitem_set.count() if self.pk else 0
    @property
    def total_quantity_sold(self): return self.saleitem_set.aggregate(total_qty=Sum('sold_quantity'))['total_qty'] or Decimal('0.00') if self.pk else Decimal('0.00')
    @property
    def has_return(self): return self.sale_returns.exists()


class SaleItem(models.Model):
    sale = models.ForeignKey('Sale', on_delete=models.CASCADE, verbose_name=_("فاتورة البيع"))
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='sale_items', verbose_name=_("المنتج المرتبط"))
    item_name = models.CharField(max_length=255, blank=True, verbose_name=_("اسم المادة"))
    sold_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), verbose_name=_("الكمية المباعة"))
    quantity_with_barcode = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_("الكمية المباعة بباركود"))
    quantity_without_barcode = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_("الكمية المباعة بدون باركود"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("سعر الوحدة"))
    notes = models.CharField(max_length=255, blank=True, verbose_name=_("ملاحظات"))
    sale_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("إجمالي البند"))
    sale_currency = models.ForeignKey("Currency", on_delete=models.PROTECT, related_name='sale_items_by_currency', verbose_name=_("عملة البيع لهذا البند"), null=True, blank=True)
    exchange_rate_at_sale = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('1.00'), verbose_name=_("سعر الصرف وقت البيع"))
    unit_price_base_currency = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("سعر الوحدة (بالعملة الأساسية)"))
    sale_item_image = models.ImageField(upload_to='sale_items_image/%y/%m/%d/', max_length=100, blank=True, null=True, verbose_name=_("صورة المادة"))
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))

    class Meta:
        verbose_name = _("بند فاتورة البيع")
        verbose_name_plural = _("بنود فواتير البيع")
        ordering = ["id"]

    def __str__(self):
        name = self.product.product_name if self.product else self.item_name
        return f"{name} - {self.sold_quantity} × {self.unit_price} = {self.sale_total}"
    
    def save(self, *args, **kwargs):
        if not self.item_name: self.item_name = self.product.product_name if self.product else "مادة غير محددة"
        total_q = self.quantity_with_barcode + self.quantity_without_barcode
        if total_q > 0: self.sold_quantity = total_q
        if self.sold_quantity and self.unit_price:
            self.sale_total = (self.sold_quantity * self.unit_price).quantize(Decimal('0.01'))
        self.unit_price_base_currency = self.unit_price
        super().save(*args, **kwargs)

    def update_product_stock(self, old_quantity=None, old_product=None):
        try:
            if not self.product: return
            product = self.product
            product.refresh_from_db()

            if old_quantity is not None and old_product is not None:
                if old_product and product.id == old_product.id:
                    quantity_difference = self.sold_quantity - Decimal(str(old_quantity))
                    product.current_stock_quantity = F('current_stock_quantity') - quantity_difference
                    product.save(update_fields=['current_stock_quantity'])
                else:
                    if old_product:
                        old_product.current_stock_quantity = F('current_stock_quantity') + Decimal(str(old_quantity))
                        old_product.save(update_fields=['current_stock_quantity'])
                    product.current_stock_quantity = F('current_stock_quantity') - self.sold_quantity
                    product.save(update_fields=['current_stock_quantity'])
            else:
                product.current_stock_quantity = F('current_stock_quantity') - self.sold_quantity
                product.save(update_fields=['current_stock_quantity'])
            
            product.last_operation_type = 'sale'
            product.save(update_fields=['last_operation_type'])
            logger.info(f"✅ تم تحديث مخزون البيع للمنتج {product.product_name}")
        except Exception as e:
            logger.error(f"❌ خطأ في تحديث مخزون البيع: {e}", exc_info=True)

    def delete(self, *args, **kwargs):
        try:
            if self.product:
                self.product.current_stock_quantity = F('current_stock_quantity') + self.sold_quantity
                self.product.save(update_fields=['current_stock_quantity'])
            super().delete(*args, **kwargs)
        except Exception as e:
            logger.error(f"❌ خطأ في حذف بند البيع: {e}")
            raise


class SaleItemBarcode(models.Model):
    sale_item = models.ForeignKey('SaleItem', on_delete=models.CASCADE, related_name='item_barcodes', verbose_name=_("بند البيع"))
    barcode = models.ForeignKey('Barcode', on_delete=models.CASCADE, related_name='sale_items', verbose_name=_("الباركود"))
    quantity_used = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), verbose_name=_("الكمية المرتبطة"))
    barcode_status = models.CharField(max_length=20, choices=[('active', 'نشط'), ('returned', 'مرتجع'), ('damaged', 'تالف')], default='active', verbose_name=_("حالة الباركود في الفاتورة"))
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))

    class Meta:
        verbose_name = _("باركود بند البيع")
        verbose_name_plural = _("باركودات بنود البيع")
        unique_together = ('sale_item', 'barcode')
        ordering = ['-date_created']

    def __str__(self):
        return f"{self.sale_item.item_name} - {self.barcode.barcode_in}"

    def save(self, *args, **kwargs):
        self.barcode_status = self.barcode_status or 'active'
        # تم تصحيح القيم لتطابق choices الموجودة في نموذج Barcode
        if self.barcode_status == 'active': self.barcode.status = 'sold'
        elif self.barcode_status == 'returned': self.barcode.status = 'active'
        elif self.barcode_status == 'damaged': self.barcode.status = 'damaged'
        self.barcode.save(update_fields=['status'])
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        barcode_to_check = self.barcode
        super().delete(*args, **kwargs)
        if not SaleItemBarcode.objects.filter(barcode=barcode_to_check).exists():
            if not barcode_to_check.purch_items.exists():
                barcode_to_check.status = 'active'
                barcode_to_check.save(update_fields=['status'])



#================================================
#        المبيعات  
# ===============================================


class SaleReturn(models.Model):
    uniqueId = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name="الرقم المسلسل")
    slug = models.SlugField(max_length=225, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    last_updated = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    _last_return_number = models.IntegerField(default=0, editable=False)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sale_returns_created', verbose_name="تم الإنشاء بواسطة")
    original_sale = models.ForeignKey('Sale', on_delete=models.CASCADE, related_name='sale_returns', verbose_name="الفاتورة الأصلية")
    return_date = models.DateField(blank=True, null=True, verbose_name="تاريخ المرتجع")
    return_reason = models.TextField(max_length=500, blank=True, verbose_name="سبب الإرجاع")
    return_invoice_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="رقم مرتجع البيع")
    return_payment_method = models.ForeignKey('Payment_method', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="طريقة الدفع للإرجاع")
    return_notes = models.TextField(max_length=200, blank=True, verbose_name="ملاحظات المرتجع")
    return_currency = models.ForeignKey('Currency', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="عملة المرتجع")
    return_status = models.ForeignKey('Status', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="حالة المرتجع")
    return_image = models.ImageField(upload_to='sale_return_images/%y/%m/%d/', blank=True, null=True, verbose_name="صورة المرتجع")

    return_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="إجمالي بنود المرتجع")
    return_tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="قيمة الضريبة المستردة")
    return_final_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="الإجمالي النهائي للمرتجع")
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="المبلغ المصروف نقداً")
    is_refunded = models.BooleanField(default=False, verbose_name="تم الاسترداد بالكامل")

    class Meta:
        verbose_name = "مرتجع مبيعات"
        verbose_name_plural = "مرتجعات المبيعات"
        ordering = ["-date_created"]
    
    def __str__(self):
        return f"مرتجع بيع {self.uniqueId}"
    
    def save(self, *args, **kwargs):
        if not self.return_date: self.return_date = timezone.now().date()
        if not self.uniqueId:
            last_return = SaleReturn.objects.order_by('-_last_return_number').first()
            new_number = (last_return._last_return_number if last_return else 0) + 1
            self._last_return_number = new_number
            self.uniqueId = f"SR{new_number:04d}"
        if not self.slug: self.slug = slugify(f"sale-return-{self.uniqueId}")
        super().save(*args, **kwargs)

    def calculate_and_save_totals(self):
        try:
            self.return_subtotal = self.salereturnitem_set.aggregate(total_sum=Sum('return_total'))['total_sum'] or Decimal('0.00')
            tax_percentage = getattr(self.original_sale, 'sale_tax_percentage', Decimal('0.00'))
            self.return_tax_amount = (self.return_subtotal * (tax_percentage / Decimal('100.00'))).quantize(Decimal('0.01')) if tax_percentage else Decimal('0.00')
            self.return_final_total = self.return_subtotal + self.return_tax_amount
            self.is_refunded = (self.paid_amount >= self.return_final_total)
            super().save(update_fields=['return_subtotal', 'return_tax_amount', 'return_final_total', 'paid_amount', 'is_refunded'])
        except Exception as e:
            logger.error(f"خطأ في حساب إجماليات مرتجع البيع: {e}")
            raise
    
    @property
    def total_items_count(self): return self.salereturnitem_set.count() if self.pk else 0
    @property
    def total_quantity_returned(self): return self.salereturnitem_set.aggregate(total_qty=Sum('returned_quantity'))['total_qty'] or Decimal('0.00') if self.pk else Decimal('0.00')


class SaleReturnItem(models.Model):
    sale_return = models.ForeignKey('SaleReturn', on_delete=models.CASCADE, verbose_name="مرتجع البيع")
    original_sale_item = models.ForeignKey('SaleItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='return_items', verbose_name="بند البيع الأصلي")
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='sale_return_items', verbose_name="المنتج المرتجع")
    item_name = models.CharField(max_length=255, blank=True, verbose_name="اسم المادة")
    returned_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), verbose_name="الكمية المرتجعة")
    quantity_with_barcode = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="الكمية المرتجعة بباركود")
    quantity_without_barcode = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="الكمية المرتجعة بدون باركود")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="سعر الوحدة وقت البيع")
    notes = models.CharField(max_length=255, blank=True, verbose_name="ملاحظات")
    return_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="إجمالي بند المرتجع")
    return_currency = models.ForeignKey("Currency", on_delete=models.PROTECT, related_name='sale_return_items_by_currency', verbose_name="عملة المرتجع", null=True, blank=True)
    exchange_rate_at_return = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('1.00'), verbose_name="سعر الصرف وقت الإرجاع")
    unit_price_base_currency = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="سعر الوحدة (بالعملة الأساسية)")
    return_item_image = models.ImageField(upload_to='sale_return_items_image/%y/%m/%d/', max_length=100, blank=True, null=True, verbose_name="صورة المادة المرتجعة")
    date_created = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    last_updated = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")

    class Meta:
        verbose_name = "بند مرتجع مبيعات"
        verbose_name_plural = "بنود مرتجعات المبيعات"
        ordering = ["id"]

    def __str__(self):
        name = self.product.product_name if self.product else self.item_name
        return f"{name} - {self.returned_quantity} × {self.unit_price} = {self.return_total}"
    
    def save(self, *args, **kwargs):
        if not self.item_name: self.item_name = self.product.product_name if self.product else "مادة غير محددة"
        if self.returned_quantity and self.unit_price:
            self.return_total = (self.returned_quantity * self.unit_price).quantize(Decimal('0.01'))
        self.unit_price_base_currency = self.unit_price
        super().save(*args, **kwargs)

    def restore_product_stock(self):
        try:
            if not self.product: return
            self.product.current_stock_quantity = F('current_stock_quantity') + self.returned_quantity
            self.product.last_operation_type = 'sale_return'
            self.product.save(update_fields=['current_stock_quantity', 'last_operation_type'])
        except Exception as e:
            logger.error(f"❌ خطأ في إعادة المخزون: {e}")
            raise


class SaleReturnItemBarcode(models.Model):
    sale_return_item = models.ForeignKey('SaleReturnItem', on_delete=models.CASCADE, related_name='return_item_barcodes', verbose_name="بند المرتجع")
    barcode = models.ForeignKey('Barcode', on_delete=models.CASCADE, related_name='sale_return_items', verbose_name=_("الباركود"))
    quantity_used = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), verbose_name=_("الكمية المرتجعة"))
    barcode_status = models.CharField(max_length=20, choices=[('returned', 'مرتجع'), ('damaged', 'تالف')], default='returned', verbose_name="حالة الباركود بعد الإرجاع")
    date_created = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    last_updated = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")

    class Meta:
        verbose_name = "باركود مرتجع مبيعات"
        verbose_name_plural = "باركودات مرتجعات المبيعات"
        unique_together = ('sale_return_item', 'barcode')
        ordering = ['-date_created']

    def __str__(self):
        return f"{self.sale_return_item.item_name} - {self.barcode.barcode_in}"

    def save(self, *args, **kwargs):
        if self.barcode_status == 'returned': self.barcode.status = 'active'
        elif self.barcode_status == 'damaged': self.barcode.status = 'damaged'
        self.barcode.save(update_fields=['status'])
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        barcode_to_check = self.barcode
        super().delete(*args, **kwargs)
        if not SaleReturnItemBarcode.objects.filter(barcode=barcode_to_check).exists():
            if not barcode_to_check.sale_items.exists():
                barcode_to_check.status = 'active'
                barcode_to_check.save(update_fields=['status'])





#================================================
#  المنتجات و الباركود 
# ===============================================


class Product(models.Model):
    product_name = models.CharField(max_length=255, verbose_name=_("اسم المادة"))
    product_description = models.TextField(blank=True, verbose_name=_("وصف المادة"))
    main_barcode = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name=_("الباركود الأساسي"))
    category = models.ForeignKey('Category', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("التصنيف"), related_name='products')

    foreign_currency = models.ForeignKey('Currency', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("العملة الأجنبية"), related_name="products")
    cost_in_foreign_currency = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("التكلفة بالعملة الأجنبية"))
    purch_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("سعر الشراء الافتراضي"))
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("سعر البيع النهائي"))
    
    retail_profit_margin = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('25.00'), verbose_name=_("هامش الربح للمفرق (%)"))
    semi_wholesale_profit_margin = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('20.00'), verbose_name=_("هامش الربح لنصف الجملة (%)"))
    wholesale_profit_margin = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('15.00'), verbose_name=_("هامش الربح للجملة (%)"))
    price_adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("تعديل السعر (+/-)"))
    
    wholesale_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("سعر البيع جملة"))
    semi_wholesale_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("سعر البيع نصف جملة"))
    retail_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("سعر البيع مفرق"))
    foreign_currency_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("السعر بالعملة الأجنبية"))
    
    current_stock_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_("الكمية الحالية في المخزون"))
    average_purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("متوسط تكلفة الشراء"))
    product_image = models.ImageField(upload_to='products/%Y/%m/%d/', blank=True, null=True, verbose_name=_("صورة المنتج"))
    
    OPERATION_TYPES = (('purchase', 'مشتريات'),('sale', 'مبيعات'),('sale_return', 'مرتجع مبيعات'),('purchase_return', 'مرتجع مشتريات'))
    last_operation_type = models.CharField(max_length=20, choices=OPERATION_TYPES, null=True, blank=True, verbose_name=_("نوع آخر عملية"))
    
    uniqueId = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name=_("الرقم المسلسل"))
    slug = models.SlugField(max_length=225, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))
    
    class Meta:
        verbose_name = _("مادة")
        verbose_name_plural = _("المواد")
        ordering = ["-date_created"]
    
    def __str__(self):
        return self.product_name
    
    def save(self, *args, **kwargs):
        if not self.uniqueId:
            self.uniqueId = str(uuid.uuid4()).replace('-', '')[:10]
        needs_new_slug = not self.slug or self.slug.startswith('-') or not self.slug.strip()
        if needs_new_slug:
            base_slug = slugify(self.product_name) or f"product-{self.uniqueId}"
            base_slug = re.sub(r'-+', '-', base_slug).strip('-')
            if not base_slug: base_slug = f"product-{self.uniqueId}"
            original_slug, counter = base_slug, 1
            while Product.objects.filter(slug=base_slug).exclude(pk=self.pk if self.pk else None).exists():
                base_slug, counter = f"{original_slug}-{counter}", counter + 1
                if counter > 100:
                    base_slug = f"{original_slug}-{self.uniqueId}"
                    break
            self.slug = base_slug
        super().save(*args, **kwargs)

    @property
    def primary_barcode(self):
        primary_bc = self.barcodes.filter(is_primary=True).first()
        return primary_bc.barcode_in if primary_bc else None

    # ===== الخصائص الجديدة =====
    
    @property
    def default_sale_price(self):
        """إرجاع سعر البيع الافتراضي"""
        return self.retail_price if self.retail_price > 0 else self.sale_price
    
    @property
    def best_price(self):
        """إرجاع أقل سعر متاح"""
        prices = [self.retail_price, self.semi_wholesale_price, self.wholesale_price, self.sale_price]
        valid_prices = [p for p in prices if p > 0]
        return min(valid_prices) if valid_prices else self.sale_price
    

    

    @property
    def default_sale_price(self):
        """إرجاع سعر البيع الافتراضي"""
        return self.retail_price if self.retail_price > 0 else self.sale_price

    @property
    def best_available_price(self):
        """إرجاع أفضل (أقل) سعر متاح"""
        prices = [self.retail_price, self.semi_wholesale_price, self.wholesale_price, self.sale_price]
        valid_prices = [p for p in prices if p > 0]
        return min(valid_prices) if valid_prices else self.sale_price




class Barcode(models.Model):
    BARCODE_STATUS_CHOICES = [
        ('active', _('نشط')), ('returned', _('مرتجع')), ('sold', _('مباع')),
        ('damaged', _('تالف')), ('expired', _('منتهي الصلاحية')),
    ]
    
    barcode_in = models.CharField(max_length=255, unique=True, verbose_name=_("الباركود الداخل"))
    barcode_out = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("الباركود الخارج"))
    suffix = models.CharField(max_length=10, blank=True, null=True, verbose_name=_("اللاحقة"))
    notes = models.TextField(blank=True, verbose_name=_("ملاحظات"))
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='barcodes', verbose_name=_("المنتج"))
    status = models.CharField(max_length=20, choices=BARCODE_STATUS_CHOICES, default='active', verbose_name=_("حالة الباركود"))
    is_primary = models.BooleanField(default=False, verbose_name=_("باركود أساسي"))

    uniqueId = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name=_("الرقم المسلسل"))
    slug = models.SlugField(max_length=225, unique=True, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))

    class Meta:
        verbose_name = _("باركود")
        verbose_name_plural = _("باركودات")
        ordering = ["-date_created"]

    def __str__(self):
        return f"{self.barcode_in} - {self.product.product_name}"

    def save(self, *args, **kwargs):
        if self.is_primary:
            Barcode.objects.filter(product=self.product, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        
        if not self.uniqueId: self.uniqueId = str(uuid.uuid4()).replace('-', '')[:10]
        if not self.slug:
            base_slug = slugify(f"{self.barcode_in}-{self.product.product_name}")
            unique_slug, num = base_slug, 1
            while Barcode.objects.filter(slug=unique_slug).exists():
                unique_slug, num = f"{base_slug}-{num}", num + 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

    @property
    def is_active(self): return self.status == 'active'
    @property
    def is_available_for_sale(self): return self.status == 'active'




# ===============================================
#  نظام التسعير الديناميكي (الجديد)
# ===============================================
class PricingTier(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم المستوى")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name="نسبة الخصم (%)")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "مستوى تسعير"
        verbose_name_plural = "مستويات التسعير"
        ordering = ['display_order']

    def __str__(self):
        return f"{self.name} ({self.discount_percent}%)"


class ProductPriceTier(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='tier_prices', verbose_name="المنتج")
    tier = models.ForeignKey(PricingTier, on_delete=models.CASCADE, related_name='product_prices', verbose_name="مستوى التسعير")
    price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="السعر المحسوب")

    class Meta:
        verbose_name = "سعر المنتج في مستوى"
        verbose_name_plural = "أسعار المستويات"
        unique_together = ('product', 'tier')

    def __str__(self):
        return f"{self.product.product_name} - {self.tier.name}: {self.price}"


class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم التصنيف")
    slug = models.SlugField(max_length=100, unique=True, blank=True, verbose_name="الرابط النصي")
    pricing_tier = models.ForeignKey(PricingTier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="مستوى التسعير الافتراضي")
    is_active = models.BooleanField(default=True, verbose_name="ظاهر في المتجر")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب الظهور")
    icon = models.ImageField(upload_to='categories_icons/', blank=True, null=True, verbose_name="أيقونة التصنيف")

    class Meta:
        verbose_name = "تصنيف"
        verbose_name_plural = "تصنيفات المتجر"
        ordering = ['display_order']

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or f"cat-{uuid.uuid4().hex[:8]}"
            unique_slug, counter = base_slug, 1
            while Category.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug, counter = f"{base_slug}-{counter}", counter + 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


#================================================
# اعدادات من اجل البيانات المدخلة في قالاب التسعير 
# ===============================================



class PricingSetting(models.Model):
    conversion_factor = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_("معامل التحويل"))
    profit_margin = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_("نسبة الربح (%)"))
    pricing_password = models.CharField(max_length=255, blank=True, default='', verbose_name='كلمة مرور نظام التسعير (مشفرة)')
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("آخر تحديث"))

    class Meta:
        verbose_name = _("إعدادات التسعير")
        verbose_name_plural = _("إعدادات التسعير")

    def save(self, *args, **kwargs):
        # تشفير كلمة المرور تلقائياً قبل الحفظ إذا تم إدخال كلمة مرور جديدة
        # التحقق من أن كلمة المرور ليست فارغة، وأنها ليست مشفرة مسبقاً ب خوارزمية Django
        if self.pricing_password and not self.pricing_password.startswith(('pbkdf2_sha256$', 'argon2$', 'bcrypt_sha256$')):
            self.pricing_password = make_password(self.pricing_password)
        
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "إعدادات التسعير العامة"

# ===============================================
#  نظام تنبيهات توفر المواد
# ===============================================

class StockNotification(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="المنتج")
    email = models.EmailField(verbose_name="البريد الإلكتروني")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الطلب")
    is_sent = models.BooleanField(default=False, verbose_name="تم الإرسال")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإرسال")

    class Meta:
        verbose_name = "تنبيه مخزون"
        verbose_name_plural = "تنبيهات المخزون"
        unique_together = ('product', 'email') 

    def __str__(self):
        return f"{self.email} ينتظر {self.product.product_name}"



# ═══════════════════════════════════════════════════════════
#  عرض الفلاش (Flash Deal)
# ═══════════════════════════════════════════════════════════

class FlashDeal(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, verbose_name="المنتج")
    deal_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="سعر العرض")
    max_quantity = models.PositiveIntegerField(default=1, verbose_name="الكمية المخصصة للعرض")
    ends_at = models.DateTimeField(verbose_name="ينتهي في")
    is_active = models.BooleanField(default=False, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "عرض فلاش"
        verbose_name_plural = "عروض الفلاش"
        ordering = ['-created_at']

    def __str__(self):
        return f"فلاش: {self.product.product_name} — {self.deal_price}"

    def is_currently_active(self):
        if not self.is_active: return False
        if self.ends_at and timezone.now() > self.ends_at: return False
        return True

    def remaining_quantity(self):
        try:
            sold = WebsiteOrderItem.objects.filter(
                product=self.product, order__order_date__gte=self.created_at,
                order__status__in=['new', 'processing', 'shipped', 'delivered']
            ).aggregate(total=Sum('quantity'))['total'] or 0
            return max(0, self.max_quantity - int(sold))
        except Exception:
            return self.max_quantity

    def remaining_percentage(self):
        return int((self.remaining_quantity() / self.max_quantity) * 100) if self.max_quantity > 0 else 0


# ===============================================
#  نماذج إعدادات الواجهة
# ===============================================

class StoreAnnouncement(models.Model):
    text = models.CharField(max_length=200, verbose_name="نص الإعلان")
    icon_class = models.CharField(max_length=50, default="fa-bullhorn", verbose_name="رمز الأيقونة")
    order = models.PositiveIntegerField(default=0, verbose_name="الترتيب")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "إعلان شريط علوي"
        verbose_name_plural = "إعلانات الشريط العلوي"
        ordering = ['order']

    def __str__(self):
        return self.text


class StoreFeatureIcon(models.Model):
    title = models.CharField(max_length=100, verbose_name="العنوان")
    icon_class = models.CharField(max_length=50, verbose_name="رمز الأيقونة")
    order = models.PositiveIntegerField(default=0, verbose_name="الترتيب")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "أيقونة مميزة"
        verbose_name_plural = "الأيقونات المميزة"
        ordering = ['order']

    def __str__(self):
        return self.title




#================================================
#  بداية المتجر 
# ===============================================

class ProductStoreSetting(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, primary_key=True, related_name='store_setting')
    SECTION_CHOICES = [('none', 'بدون قسم'), ('offers', 'أحدث العروض'), ('new', 'منتجات جديدة'), ('products', 'منتجاتنا')]
    badge_image = models.ImageField(upload_to='store_badges/', blank=True, null=True, verbose_name="صورة الشعار")
    is_visible = models.BooleanField(default=True, verbose_name="ظاهر في المتجر")
    store_section = models.CharField(max_length=20, choices=SECTION_CHOICES, default='products', verbose_name="القسم في المتجر")
    show_old_price = models.BooleanField(default=True, verbose_name="إظهار السعر القديم")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب الظهور")

    def __str__(self):
        return f"إعدادات: {self.product.product_name}"


class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("المستخدم"))
    session_key = models.CharField(max_length=40, blank=True, null=True, verbose_name=_("مفتاح الجلسة (للزوار)"))
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    
    class Meta:
        verbose_name = _("سلة تسوق")
        verbose_name_plural = _("سلات التسوق")
    
    def __str__(self):
        return f"سلة {self.user if self.user else 'زائر'} - {self.id}"
    
    @property
    def total_price(self):
        """
        حساب إجمالي السلة
        """
        from decimal import Decimal
        total = Decimal('0.00')
        for item in self.items.select_related('product').all():
            total += item.total_item_price
        return total
    
    @property
    def total_items_count(self):
        """
        عدد العناصر في السلة
        """
        return self.items.count()

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items', verbose_name=_("السلة"))
    product = models.ForeignKey('Product', on_delete=models.CASCADE, verbose_name=_("المنتج"))
    quantity = models.PositiveIntegerField(default=1, verbose_name=_("الكمية"))
    
    class Meta:
        verbose_name = _("عنصر سلة")
        verbose_name_plural = _("عناصر السلة")
        unique_together = ('cart', 'product')

    def __str__(self):
        return f"{self.quantity} x {self.product.product_name}"




    @property
    def total_item_price(self):
        """
        حساب السعر الإجمالي للعنصر في السلة
        """
        # محاولة الحصول على السعر من مصادر متعددة
        price = (
            self.product.wholesale_price or 
            self.product.retail_price or 
            self.product.sale_price or 
            self.product.semi_wholesale_price or 
            0
        )
        
        # التأكد من أن السعر موجب
        if price < 0:
            price = 0
        
        return price * self.quantity


class WebsiteOrder(models.Model):
    STATUS_CHOICES = (('new', _('طلب جديد')), ('processing', _('قيد التجهيز')), ('shipped', _('تم الشحن')), ('delivered', _('تم التسليم')), ('cancelled', _('ملغي')))
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='website_orders', verbose_name=_("العميل"))
    full_name = models.CharField(max_length=100, verbose_name=_("الاسم الكامل"))
    phone = models.CharField(max_length=20, verbose_name=_("رقم الهاتف"))
    address = models.TextField(verbose_name=_("عنوان الشحن"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("ملاحظات العميل"))
    order_date = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الطلب"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name=_("حالة الطلب"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_("الإجمالي"))
    related_sale = models.OneToOneField(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name='web_order', verbose_name=_("فاتورة البيع المرتبطة"))
    
    class Meta:
        verbose_name = _("طلب متجر")
        verbose_name_plural = _("طلبات المتجر")
        ordering = ['-order_date']

    def __str__(self):
        return f"طلب #{self.id} - {self.full_name}"


class WebsiteOrderItem(models.Model):
    order = models.ForeignKey(WebsiteOrder, on_delete=models.CASCADE, related_name='items', verbose_name=_("الطلب"))
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, verbose_name=_("المنتج"))
    product_name = models.CharField(max_length=255, verbose_name=_("اسم المنتج (وقت الطلب)"))
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("سعر الوحدة"))
    quantity = models.PositiveIntegerField(default=1, verbose_name=_("الكمية"))
    
    class Meta:
        verbose_name = _("بند طلب")
        verbose_name_plural = _("بنود الطلب")

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"


class StoreBanner(models.Model):
    POSITION_CHOICES = [('top', 'بنر علوي (عرض كامل)'), ('side', 'بنر جانبي')]
    title = models.CharField(max_length=100, verbose_name="العنوان الترويجي")
    image = models.ImageField(upload_to='store_banners/', verbose_name="صورة البنر")
    link_url = models.URLField(blank=True, null=True, verbose_name="رابط عند الضغط")
    position = models.CharField(max_length=10, choices=POSITION_CHOICES, default='top', verbose_name="موضع العرض")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    order = models.PositiveIntegerField(default=0, verbose_name="الترتيب")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "بنر إعلاني"
        verbose_name_plural = "البنرات الإعلانية"
        ordering = ['order', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_position_display()})"




class StoreSection(models.Model):
    SECTION_STYLE_CHOICES = [('grid', 'بطاقات شبكية (Grid)'), ('list', 'قائمة أفقية (List)'), ('offers', 'أسلوب العروض (Offers)')]
    name = models.CharField(max_length=100, verbose_name="اسم القسم")
    slug = models.SlugField(max_length=100, unique=True, blank=True, verbose_name="الرابط النصي")
    style_type = models.CharField(max_length=20, choices=SECTION_STYLE_CHOICES, default='grid', verbose_name="شكل العرض")
    is_active = models.BooleanField(default=True, verbose_name="فعال (يظهر في المتجر)")
    is_offers_style = models.BooleanField(default=False, verbose_name="شكل عروض مميز")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب القسم")
    category = models.ForeignKey('Category', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="التصنيف المرتبط", related_name='store_sections')
    
    class Meta:
        verbose_name = "قسم متجر"
        verbose_name_plural = "أقسام المتجر"
        ordering = ['display_order']

    def save(self, *args, **kwargs):
        if self.category and not self.name:
            self.name = self.category.name
        if not self.slug:
            base_slug = slugify(self.name) or f"section-{uuid.uuid4().hex[:8]}"
            unique_slug, counter = base_slug, 1
            while StoreSection.objects.filter(slug=unique_slug).exists():
                unique_slug, counter = f"{base_slug}-{counter}", counter + 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name




class ProductSectionItem(models.Model):
    section = models.ForeignKey(StoreSection, on_delete=models.CASCADE, related_name='items', verbose_name="القسم")
    product = models.ForeignKey('Product', on_delete=models.CASCADE, verbose_name="المنتج")
    display_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب المنتج داخل القسم")
    show_old_price = models.BooleanField(default=False, verbose_name="إظهار السعر القديم كعرض")
    custom_badge = models.ImageField(upload_to='store_section_badges/', blank=True, null=True, verbose_name="شعار خاص (اختياري)")
    
    class Meta:
        verbose_name = "منتج داخل القسم"
        verbose_name_plural = "منتجات الأقسام"
        ordering = ['display_order']
        unique_together = ('section', 'product')

    def __str__(self):
        return f"{self.product.product_name} في ({self.section.name})"

