
# ==================== مكتبات بايثون القياسية ====================
import csv
import datetime
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from urllib.parse import quote

# ==================== مكتبات خارجية ====================
import requests

# ==================== إطار عمل Django الأساسي ====================
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import User
from django.core import serializers
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.temp import NamedTemporaryFile
from django.core.mail import EmailMessage, send_mail
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import CharField, Count, DecimalField, ExpressionWrapper, F, Func, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce, Concat, Now
from django.forms import inlineformset_factory
from django.http import Http404, HttpResponse, JsonResponse, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.utils.translation import gettext as _, gettext_lazy as _lazy
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

# ==================== التطبيقات والأدوات المساعدة الأخرى ====================
from accounts.models import Profile
from accounts.views import is_staff_user
from invoice.models import PricingSetting, Product, PricingTier, ProductPriceTier, Sale, Purch, SaleReturn, PurchaseReturn, CashTransaction
from invoice.utils import get_active_email_connection

# ==================== النماذج المحلية (Models) ====================
from .models import (
    Barcode, CashTransaction, Cart, CartItem, Category, Currency,
    EmailSetting, FlashDeal, Payment_method, PriceType, PricingSetting,
    PricingTier, Product, ProductPriceTier, ProductSectionItem, ProductStoreSetting,
    Purch, PurchItem, PurchItemBarcode, PurchaseReturn, PurchaseReturnItem,
    PurchaseReturnItemBarcode, Sale, SaleItem, SaleItemBarcode, SaleReturn,
    SaleReturnItem, SaleReturnItemBarcode, Shipping_com_m, Status,
    StockNotification, StoreAnnouncement, StoreBanner, StoreFeatureIcon,
    StoreSection, User, WebsiteOrder, WebsiteOrderItem
)

# ==================== النماذج المحلية (Forms) ====================
from .forms import (
    BarcodeForm, CashTransactionForm, CurrencyForm, EmailSettingForm,
    PaymentMethodForm, PriceTypeForm, PurchEditForm, PurchForm,
    PurchaseReturnForm, PurchaseReturnItemForm, PurchaseReturnItemFormSet,
    PurchItemEditFormSet, PurchItemFormSet, SaleForm, SaleItemBarcodeForm,
    SaleItemBarcodeFormSet, SaleItemForm, SaleItemFormSet, SaleReturnForm,
    SaleReturnItemBarcodeForm, SaleReturnItemBarcodeFormSet, SaleReturnItemForm,
    SaleReturnItemFormSet, ShippingCompanyForm, StatusForm
)

# ==================== ملفات المشروع المحلية ====================
from .backup_engine import (
    create_backup,
    save_backup_to_server,
    get_server_backups,
    get_backups_dir,
    delete_server_backup as delete_backup_file,
)
from .utils import send_custom_email, verify_pricing_password

# ==================== إعدادات التسجيل ====================
logger = logging.getLogger(__name__)
User = get_user_model()



#================================================
#               فواتير الشراء                  #
# ===============================================


@login_required
@permission_required('invoice.view_purch', raise_exception=True)
def purch_list(request):
    """عرض قائمة فواتير الشراء مع فرز وترقيم صفحات"""
    from django.db.models import Sum, Avg, Count, Q
    from django.core.paginator import Paginator
    
    user = request.user

    if user.is_superuser:
        queryset = Purch.objects.all().select_related(
            'purch_supplier', 'purch_status', 'purch_currency', 'purch_payment_method'
        ).order_by('-date_created')
    else:
        queryset = Purch.objects.filter(
            Q(created_by=user) | Q(purch_supplier=user)
        ).distinct().select_related(
            'purch_supplier', 'purch_status', 'purch_currency', 'purch_payment_method'
        ).order_by('-date_created')
    
    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(uniqueId__icontains=q) |
            Q(purch_supplier__first_name__icontains=q) |
            Q(purch_supplier__last_name__icontains=q) |
            Q(purch_supplier__username__icontains=q) |
            Q(supplier_invoice_number__icontains=q)
        ).distinct()
    
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        queryset = queryset.filter(purch_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(purch_date__lte=date_to)
    
    status = request.GET.get('status', '')
    if status == 'paid':
        queryset = queryset.filter(is_paid=True)
    elif status == 'unpaid':
        queryset = queryset.filter(is_paid=False, paid_amount=0)
    elif status == 'partial':
        queryset = queryset.filter(is_paid=False, paid_amount__gt=0)
    
    supplier = request.GET.get('supplier', '')
    if supplier:
        queryset = queryset.filter(
            Q(purch_supplier__first_name__icontains=supplier) |
            Q(purch_supplier__last_name__icontains=supplier) |
            Q(purch_supplier__username__icontains=supplier)
        ).distinct()
    
    stats = queryset.aggregate(
        total_amount=Sum('purch_final_total'),
        total_paid=Sum('paid_amount'),
        total_due=Sum('balance_due'),
        avg_invoice=Avg('purch_final_total'),
        count=Count('id')
    )
    
    sort_field = request.GET.get('sort', '')
    sort_order = request.GET.get('order', '')
    
    sort_map = {
        'uniqueId': 'uniqueId', 'purch_date': 'purch_date',
        'supplier': 'purch_supplier__username', 'purch_final_total': 'purch_final_total',
        'paid_amount': 'paid_amount', 'balance_due': 'balance_due', 'is_paid': 'is_paid',
    }
    
    if sort_field in sort_map:
        field = sort_map[sort_field]
        if sort_order == 'desc':
            field = f'-{field}'
        queryset = queryset.order_by(field)
    
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page', 1)
    purchases = paginator.get_page(page_number)
    
    return render(request, 'invoice/purchase/purch_list.html', {
        'purchases': purchases,
        'total_purchases_amount': stats['total_amount'] or 0,
        'total_paid_amount': stats['total_paid'] or 0,
        'total_due_amount': stats['total_due'] or 0,
        'average_invoice': stats['avg_invoice'] or 0,
        'title': _('فواتير الشراء')
    })


@login_required
@permission_required('invoice.add_purch', raise_exception=True)
def purch_create(request):
    """إنشاء فاتورة شراء جديدة."""
    if request.method == 'POST':
        form = PurchForm(request.POST, request.FILES)
        formset = PurchItemFormSet(request.POST, request.FILES, prefix='items')
        
        barcode_errors = []
        invoice_barcodes_set = set()
        
        submitted_barcodes_data = {}
        for key, values in request.POST.lists():
            if key.startswith('item_') and key.endswith('_barcodes'):
                try:
                    parts = key.split('_')
                    idx = int(parts[1])
                    submitted_barcodes_data[idx] = values
                except (ValueError, IndexError):
                    continue
        
        for idx, barcodes in submitted_barcodes_data.items():
            for bc in barcodes:
                bc = bc.strip()
                if not bc: continue
                if bc in invoice_barcodes_set:
                    barcode_errors.append(f"الباركود '{bc}' مكرر أكثر من مرة في نفس الفاتورة.")
                else:
                    invoice_barcodes_set.add(bc)
                if PurchItemBarcode.objects.filter(barcode__barcode_in=bc).exists():
                    barcode_errors.append(f"الباركود '{bc}' مستخدم سابقاً في فاتورة شراء أخرى ولا يمكن تكراره.")

        if form.is_valid() and formset.is_valid() and not barcode_errors:
            try:
                with transaction.atomic():
                    purchase = form.save(commit=False)
                    purchase.created_by = request.user
                    
                    if not purchase.uniqueId:
                        last_invoice = Purch.objects.order_by('-_last_invoice_number').first()
                        last_number = last_invoice._last_invoice_number if last_invoice else 0
                        new_number = last_number + 1
                        purchase._last_invoice_number = new_number
                        purchase.uniqueId = f"P{new_number:04d}"
                        
                    if not purchase.slug:
                        purchase.slug = slugify(f"purch-{purchase.uniqueId}")
                    
                    purchase.save()

                    instances = formset.save(commit=False)
                    
                    for i, instance in enumerate(instances):
                        instance.purch = purchase

                        product_id_from_form = request.POST.get(f'items-{i}-product')
                        product_search_value = request.POST.get(f'items-{i}-product_search', '')
                        
                        if not instance.product and product_id_from_form and product_id_from_form != '':
                            try:
                                instance.product = Product.objects.get(id=product_id_from_form)
                            except Product.DoesNotExist:
                                pass
                        
                        # ================= تمت المعالجة هنا =================
                        if not instance.product and product_search_value and product_search_value != "مادة غير محددة":
                            try:
                                instance.product = Product.objects.filter(product_name=product_search_value.split(' - ')[0].strip()).first()
                            except Exception as e:
                                logger.warning(f"خطأ في البحث عن المنتج بالاسم '{product_search_value}' أثناء إنشاء فاتورة الشراء: {e}")
                        # ====================================================
                        
                        if not instance.item_name and instance.product:
                            instance.item_name = instance.product.product_name
                        elif not instance.item_name:
                            instance.item_name = product_search_value if product_search_value else "مادة غير محددة"
                        
                        image_field_name = f'items-{i}-purch_item_image'
                        image_url = request.POST.get(f'items-{i}-product_image_url', '')
                        is_auto_image = request.POST.get(f'items-{i}-is_auto_image') == 'true'
                        is_manual_upload = request.POST.get(f'items-{i}-manual_image_upload') == 'true'
                        
                        if image_field_name in request.FILES:
                            pass 
                        elif image_url and is_auto_image and not is_manual_upload:
                            try:
                                response = requests.get(image_url, timeout=10)
                                if response.status_code == 200:
                                    img_temp = NamedTemporaryFile(delete=True)
                                    img_temp.write(response.content)
                                    img_temp.flush()
                                    filename = os.path.basename(image_url)
                                    if not filename or '.' not in filename:
                                        filename = f"product_{instance.product_id if instance.product else 'auto'}.jpg"
                                    instance.purch_item_image.save(filename, File(img_temp), save=False)
                            except Exception as e:
                                logger.error(f"خطأ في تحميل الصورة التلقائية: {e}")
                        
                        instance.save()
                        
                        if instance.product:
                            instance.update_product_stock()
                        
                        barcodes_key = f'item_{i}_barcodes'
                        barcodes = request.POST.getlist(barcodes_key)
                        
                        for barcode_value in barcodes:
                            barcode_value = barcode_value.strip()
                            if barcode_value:
                                try:
                                    barcode_obj = None
                                    try:
                                        barcode_obj = Barcode.objects.get(barcode_in=barcode_value)
                                        if instance.product and barcode_obj.product != instance.product:
                                            continue
                                    except Barcode.DoesNotExist:
                                        if instance.product:
                                            barcode_obj = Barcode.objects.create(
                                                barcode_in=barcode_value, product=instance.product,
                                                is_primary=False, status='active'
                                            )
                                        elif instance.item_name and instance.item_name != "مادة غير محددة":
                                            product = Product.objects.filter(product_name=instance.item_name).first()
                                            if product:
                                                barcode_obj = Barcode.objects.create(barcode_in=barcode_value, product=product, is_primary=False, status='active')
                                    
                                    if barcode_obj:
                                        PurchItemBarcode.objects.get_or_create(
                                            purch_item=instance, barcode=barcode_obj,
                                            defaults={'quantity_used': Decimal('1.00'), 'barcode_status': 'active'}
                                        )
                                except IntegrityError:
                                    continue
                                except Exception as e:
                                    logger.error(f"خطأ في ربط الباركود: {e}")
                    
                    for instance in formset.deleted_objects:
                        instance.item_barcodes.all().delete()
                        instance.delete()
                    
                    purchase.calculate_and_save_totals()

                    if purchase.paid_amount > purchase.purch_final_total:
                        raise ValidationError(_("المبلغ المدفوع لا يمكن أن يتجاوز الإجمالي النهائي للفاتورة"))

                    if purchase.paid_amount > 0 and purchase.purch_payment_method and purchase.purch_payment_method.is_cash:
                        purchase.create_cash_transaction()
                    
                    messages.success(request, 'تم إنشاء فاتورة الشراء بنجاح وتحديث المخزون')
                    return redirect('invoice:purch_detail', slug=purchase.slug)
                    
            except ValidationError as e:
                messages.error(request, e.messages[0] if e.messages else str(e))
            except Exception as e:
                logger.error(f"خطأ في إنشاء فاتورة الشراء: {e}")
                messages.error(request, 'حدث خطأ غير متوقع أثناء إنشاء الفاتورة، يرجى المحاولة مرة أخرى.')
        
        if not form.is_valid() or not formset.is_valid() or barcode_errors:
            for error in barcode_errors:
                messages.error(request, error)
            if not barcode_errors:
                messages.error(request, 'يرجى تصحيح الأخطاء في النموذج.')
            else:
                messages.error(request, 'لم يتم حفظ الفاتورة بسبب أخطاء في الباركودات أو البيانات.')
            
            products = Product.objects.all()
            return render(request, 'invoice/purchase/purch_form.html', {
                'form': form, 'formset': formset, 'products': products,
                'title': 'إنشاء فاتورة شراء جديدة'
            })

    else:
        form = PurchForm(initial={
            'purch_date': timezone.now().date(), 'paid_amount': 0,
            'purch_tax_percentage': 0, 'purch_discount': 0, 'purch_addition': 0
        })
        formset = PurchItemFormSet(prefix='items', queryset=PurchItem.objects.none())
    
    products = Product.objects.all()
    return render(request, 'invoice/purchase/purch_form.html', {
        'form': form, 'formset': formset, 'products': products,
        'title': 'إنشاء فاتورة شراء جديدة'
    })



@login_required
@permission_required('invoice.view_purch', raise_exception=True)
def purch_detail(request, slug):
    """عرض تفاصيل فاتورة المشتريات"""
    purchase = get_object_or_404(Purch, slug=slug)
    
    user = request.user
    is_allowed = (user.is_superuser or purchase.created_by == user or purchase.purch_supplier == user)
    if not is_allowed:
        raise PermissionDenied(_("ليس لديك صلاحية للوصول إلى هذه الفاتورة"))
    
    items_for_template = []
    effective_subtotal = Decimal('0.00')  # ★ متغير لتجميع الإجمالي الفعلي
    
    purchase_items = purchase.purchitem_set.all().select_related('product')

    for item in purchase_items:
        # ★★★ إصلاح حساب الكميات: بدون شرط التاريخ لحساب الكمية الفعلية الصحيحة ★★★
        total_returned = item.returned_items.all().aggregate(
            total=Sum('returned_quantity')
        )['total'] or Decimal('0.00')

        available_quantity = item.purchased_quantity - total_returned
        # ★ حساب إجمالي البند الفعلي (الكمية المتوفرة × السعر)
        effective_item_total = available_quantity * item.unit_price
        effective_subtotal += effective_item_total
        
        barcodes_list = []

        # عرض كل الباركودات التابعة للفاتورة (سجل تاريخي)
        if hasattr(item, 'item_barcodes'):
            for b in item.item_barcodes.all():
                if b.barcode:
                    # تمييز الباركود المباع
                    if b.barcode.status == 'sold':
                        barcodes_list.append(f"{b.barcode} (مباع)")
                    else:
                        barcodes_list.append(b.barcode)

        # إضافة الباركودات المرتجعة
        for ret_item in item.returned_items.all():
            ret_barcodes = []
            if hasattr(ret_item, 'returned_barcodes'):
                try:
                    ret_barcodes.extend([b.barcode for b in ret_item.returned_barcodes.all() if b.barcode])
                except Exception as e:
                    logger.warning(f"خطأ في جلب باركودات المرتجع للبند {item.id}: {e}")
            
            for code in ret_barcodes:
                barcodes_list.append(f"{code} (returned)")

        item_data = SimpleNamespace(
            product_name=item.product.product_name if item.product else item.item_name,
            original_quantity=item.purchased_quantity,
            returned_quantity=total_returned,
            purchased_quantity=available_quantity, 
            unit_price=item.unit_price,
            purch_total=item.purch_total,  # الأصلي للسجل
            effective_total=effective_item_total,  # ★ الفعلي للعرض المالي
            purch_item_image=item.purch_item_image,
            barcodes=barcodes_list,
            notes=item.notes,  # إضافة الملاحظات
        )
        items_for_template.append(item_data)

    # ★★★ إعادة حساب القسم المالي الفعلي بناءً على الكميات المتوفرة ★★★
    tax_percentage = purchase.purch_tax_percentage or Decimal('0.00')
    addition = purchase.purch_addition or Decimal('0.00')
    discount = purchase.purch_discount or Decimal('0.00')
    paid_amount = purchase.paid_amount or Decimal('0.00')
    
    calculated_tax = (effective_subtotal * tax_percentage / Decimal('100')).quantize(Decimal('0.01'))
    calculated_final_total = effective_subtotal + calculated_tax + addition - discount
    calculated_balance_due = calculated_final_total - paid_amount
    
    financials = SimpleNamespace(
        purch_subtotal=effective_subtotal,
        purch_tax_amount=calculated_tax,
        purch_tax_percentage=tax_percentage,
        purch_addition=addition,
        purch_discount=discount,
        purch_final_total=calculated_final_total,
        paid_amount=paid_amount,
        balance_due=calculated_balance_due,
        purch_currency=purchase.purch_currency
    )

    context = {
        'purchase': purchase,
        'items': items_for_template,
        'financials': financials,  # ★ تمرير الأرقام المالية الصحيحة
        'title': f'تفاصيل فاتورة الشراء {purchase.uniqueId}',
    }
    return render(request, 'invoice/purchase/purch_detail.html', context)



@login_required
@permission_required('invoice.change_purch', raise_exception=True)
def purch_edit(request, slug):
    """تعديل فاتورة شراء موجودة - النسخة الآمنة والمتوافقة مع F()"""
    from django.db.models import Q, Sum
    from decimal import Decimal
    from django.core.exceptions import PermissionDenied
    import json
    
    purchase = get_object_or_404(Purch, slug=slug)
    
    if purchase.created_by and purchase.created_by != request.user and not request.user.is_superuser:
        raise PermissionDenied(_("ليس لديك صلاحية للوصول إلى هذه الفاتورة"))
    
    logger.info(f"بدء تعديل فاتورة: {purchase.uniqueId}")
    
    reset_date = purchase.last_updated
    
    # ★★★ إصلاح حساس: حساب الكميات الفعالة والأرصدة المرتجعة (بدون شرط التاريخ لحساب الإجمالي الصحيح) ★★★
    effective_quantities = {}
    total_returned_per_item = {}
    for item in purchase.purchitem_set.all():
        # نجمع كل المرتجعات بغض النظر عن التاريخ لنحصل على الرصيد الفعلي الحقيقي
        total_returned = item.returned_items.all().aggregate(total=Sum('returned_quantity'))['total'] or Decimal('0.00')
        effective_quantities[item.id] = item.purchased_quantity - total_returned
        total_returned_per_item[item.id] = total_returned
    
    if request.method == 'POST':
        post_data = request.POST.copy()
        files_data = request.FILES
        
        # معالجة حقل المورد إذا جاء من حقل البحث
        supplier_search_value = post_data.get('supplier-search-input', '')
        if supplier_search_value and supplier_search_value != '':
            try:
                if supplier_search_value.isdigit():
                    supplier = User.objects.get(id=int(supplier_search_value))
                    post_data['purch_supplier'] = str(supplier.id)
                else:
                    supplier = User.objects.filter(
                        Q(first_name__icontains=supplier_search_value) |
                        Q(last_name__icontains=supplier_search_value) |
                        Q(username__icontains=supplier_search_value)
                    ).first()
                    if supplier:
                        post_data['purch_supplier'] = str(supplier.id)
            except Exception as e:
                logger.error(f"خطأ في البحث عن المورد: {e}")
        
        # معالجة بيانات البنود والمنتجات
        total_forms = int(post_data.get('items-TOTAL_FORMS', 0))
        for i in range(total_forms):
            product_search_key = f'items-{i}-product_search'
            if product_search_key in post_data:
                product_search = post_data[product_search_key]
                if product_search and product_search.strip():
                    try:
                        if product_search.isdigit():
                            product = Product.objects.get(id=int(product_search))
                            post_data[f'items-{i}-product'] = str(product.id)
                            post_data[f'items-{i}-item_name'] = product.product_name
                        else:
                            product = Product.objects.filter(
                                Q(product_name__icontains=product_search) |
                                Q(barcodes__barcode_in__icontains=product_search)
                            ).first()
                            if product:
                                post_data[f'items-{i}-product'] = str(product.id)
                                post_data[f'items-{i}-item_name'] = product.product_name
                            else:
                                post_data[f'items-{i}-item_name'] = product_search
                    except Product.DoesNotExist:
                        post_data[f'items-{i}-item_name'] = product_search
        
        form = PurchEditForm(post_data, files_data, instance=purchase)
        formset = PurchItemEditFormSet(
            post_data, files_data, instance=purchase, 
            prefix='items', original_purchase=purchase,
            returned_items_data=effective_quantities
        )
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    saved_purchase = form.save()
                    saved_items = formset.save(commit=False)
                    
                    for i, item_form in enumerate(formset):
                        item = item_form.instance
                        original_item = None
                        old_effective_quantity = Decimal('0.00')
                        old_product = None
                        item_total_returned = Decimal('0.00')
                        
                        if item.pk:
                            try:
                                original_item = PurchItem.objects.get(id=item.id)
                                old_effective_quantity = effective_quantities.get(original_item.id, Decimal('0.00'))
                                item_total_returned = total_returned_per_item.get(original_item.id, Decimal('0.00'))
                                old_product = original_item.product
                            except PurchItem.DoesNotExist:
                                pass
                        
                        item.purch = saved_purchase
                        
                        # رفع الصور
                        if f'items-{i}-product_image_upload' in files_data:
                            uploaded_file = files_data[f'items-{i}-product_image_upload']
                            if uploaded_file:
                                item.purch_item_image = uploaded_file
                        
                        if not item.item_name and item.product:
                            item.item_name = item.product.product_name
                        elif not item.item_name:
                            item_name_from_form = item_form.cleaned_data.get('item_name', '')
                            if item_name_from_form:
                                item.item_name = item_name_from_form
                        
                        # ★ الحصول على الكمية الفعالة من الفورم
                        submitted_effective_quantity = item_form.cleaned_data.get('purchased_quantity')
                        unit_price_new = item_form.cleaned_data.get('unit_price')
                        
                        if submitted_effective_quantity is not None:
                            if unit_price_new is not None:
                                item.unit_price = unit_price_new
                            
                            # ★ حساب purchased_quantity الكلي = فعالة + مرتجع
                            item.purchased_quantity = submitted_effective_quantity + item_total_returned
                            
                            if item.purchased_quantity and item.unit_price:
                                item.purch_total = item.purchased_quantity * item.unit_price
                        
                        item.save()
                        
                        # ==========================================
                        # ★ تحديث المخزون بناءً على تغيير الكمية الفعالة
                        # ==========================================
                        if item.product:
                            product = item.product
                            product.refresh_from_db()
                            
                            if original_item:
                                # حساب الفرق في الكمية الفعالة
                                stock_difference = submitted_effective_quantity - old_effective_quantity
                                
                                if old_product and product.id != old_product.id:
                                    # تم تغيير المنتج
                                    old_product.current_stock_quantity = F('current_stock_quantity') - old_effective_quantity
                                    old_product.save(update_fields=['current_stock_quantity'])
                                    
                                    product.current_stock_quantity = F('current_stock_quantity') + submitted_effective_quantity
                                    product.save(update_fields=['current_stock_quantity'])
                                    product.refresh_from_db()
                                    product.average_purchase_cost = item.unit_price_base_currency
                                    product.save()
                                elif stock_difference != 0:
                                    # نفس المنتج، تغيرت الكمية الفعالة
                                    product.current_stock_quantity = F('current_stock_quantity') + stock_difference
                                    product.save(update_fields=['current_stock_quantity'])
                                    
                                    if stock_difference > 0:
                                        product.refresh_from_db()
                                        if product.current_stock_quantity > 0:
                                            old_total_value = (product.current_stock_quantity - stock_difference) * product.average_purchase_cost
                                            new_total_value = old_total_value + (stock_difference * item.unit_price_base_currency)
                                            product.average_purchase_cost = (new_total_value / product.current_stock_quantity).quantize(Decimal('0.01'))
                                            product.save()
                            else:
                                # بند جديد
                                product.current_stock_quantity = F('current_stock_quantity') + submitted_effective_quantity
                                product.save(update_fields=['current_stock_quantity'])
                                product.refresh_from_db()
                                
                                if product.current_stock_quantity > 0:
                                    old_total_value = (product.current_stock_quantity - submitted_effective_quantity) * product.average_purchase_cost
                                    new_total_value = old_total_value + (submitted_effective_quantity * item.unit_price_base_currency)
                                    product.average_purchase_cost = (new_total_value / product.current_stock_quantity).quantize(Decimal('0.01'))
                                    product.save()
                            
                            product.last_operation_type = 'purchase'
                            product.save(update_fields=['last_operation_type'])
                            logger.info(f"✅ تم تحديث مخزون المنتج {product.product_name}")
                        
                        # ==========================================
                        # ★ معالجة الباركودات - التعامل فقط مع النشطة
                        # ==========================================
                        barcode_keys = [k for k in post_data.keys() if k.startswith(f'item_{i}_barcodes[')]
                        new_barcodes = [post_data.get(k, '').strip() for k in barcode_keys if post_data.get(k, '').strip()]
                        
                        # ★ حماية الباركودات المرتجعة من الحذف
                        active_item_barcodes = item.item_barcodes.filter(barcode_status='active')
                        
                        for existing_barcode in active_item_barcodes:
                            if existing_barcode.barcode.barcode_in not in new_barcodes:
                                existing_barcode.delete()
                        
                        for barcode_value in new_barcodes:
                            if not active_item_barcodes.filter(barcode__barcode_in=barcode_value).exists():
                                try:
                                    barcode_obj, created = Barcode.objects.get_or_create(
                                        barcode_in=barcode_value,
                                        defaults={'status': 'active', 'product': item.product if item.product else None}
                                    )
                                    PurchItemBarcode.objects.get_or_create(
                                        purch_item=item, barcode=barcode_obj,
                                        defaults={'quantity_used': Decimal('1.00'), 'barcode_status': 'active'}
                                    )
                                except Exception as e:
                                    logger.error(f"خطأ في معالجة الباركود: {e}")
                    
                    # حذف البنود المحذوفة
                    for item in formset.deleted_objects:
                        item.delete()
                    
                    # إعادة حساب الإجماليات
                    saved_purchase.calculate_and_save_totals()
                    
                    if saved_purchase.paid_amount > 0:
                        saved_purchase.create_cash_transaction()
                    
                    messages.success(request, _('✅ تم تعديل فاتورة الشراء بنجاح وتحديث المخزون والباركودات'))
                    return redirect('invoice:purch_detail', slug=saved_purchase.slug)

            except Exception as e:
                logger.error(f"خطأ في تعديل فاتورة الشراء: {e}", exc_info=True)
                messages.error(request, _('❌ حدث خطأ أثناء الحفظ، يرجى المحاولة مرة أخرى'))
        else:
            # ★★★ إصلاح إبراز أخطاء الفورم للمستخدم (خاصة المبلغ المدفوع) ★★★
            if form.errors.get('paid_amount'):
                for error in form.errors['paid_amount']:
                    messages.error(request, f"❌ {error}")
            else:
                messages.error(request, _('❌ يرجى تصحيح الأخطاء في النموذج'))
    else:
        form = PurchEditForm(instance=purchase)
        formset = PurchItemEditFormSet(
            instance=purchase, prefix='items', 
            original_purchase=purchase, returned_items_data=effective_quantities
        )

    # ★ تمرير الكميات الفعالة كـ JSON للقالب
    effective_quantities_json = json.dumps({
        str(k): str(v) for k, v in effective_quantities.items()
    })

    return render(request, 'invoice/purchase/purch_edit.html', {
        'form': form, 'formset': formset, 'purchase': purchase,
        'title': f'تعديل فاتورة الشراء {purchase.uniqueId}',
        'effective_quantities_json': effective_quantities_json,
    })


@login_required
@permission_required('invoice.delete_purch', raise_exception=True)
def purch_delete(request, slug):
    """حذف فاتورة شراء مع استرجاع الكميات من المخزون وحذف الباركودات ومعاملات الصندوق"""
    purchase = get_object_or_404(Purch, slug=slug)
    
    if purchase.created_by and purchase.created_by != request.user and not request.user.is_superuser:
        raise PermissionDenied(_("ليس لديك صلاحية للوصول إلى هذه الفاتورة"))
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # ★★★ 1. استرجاع الكميات من المخزون لكل منتج في الفاتورة ★★★
                items_updated = []
                for purch_item in purchase.purchitem_set.all().select_related('product'):
                    if purch_item.product:
                        product = purch_item.product
                        product.refresh_from_db()
                        
                        # حساب الكمية الفعالة (المشتريات - المرتجعات)
                        total_returned = purch_item.returned_items.all().aggregate(
                            total=Sum('returned_quantity')
                        )['total'] or Decimal('0.00')
                        
                        effective_quantity = purch_item.purchased_quantity - total_returned
                        
                        if effective_quantity > 0:
                            # استرجاع الكمية من المخزون
                            product.current_stock_quantity = F('current_stock_quantity') - effective_quantity
                            product.save(update_fields=['current_stock_quantity'])
                            product.refresh_from_db()
                            
                            # إعادة حساب متوسط التكلفة إذا بقي رصيد
                            if product.current_stock_quantity > 0:
                                # حساب متوسط التكلفة الجديد (بحذف تكلفة هذه الفاتورة)
                                # ملاحظة: هذه عملية تقديرية، يمكن تعديلها حسب منطق العمل
                                total_value = product.current_stock_quantity * product.average_purchase_cost
                                product.average_purchase_cost = (total_value / product.current_stock_quantity).quantize(Decimal('0.01'))
                                product.save(update_fields=['average_purchase_cost'])
                            
                            items_updated.append({
                                'product': product.product_name,
                                'quantity': effective_quantity
                            })
                            logger.info(f"✅ تم استرجاع {effective_quantity} من المنتج {product.product_name}")
                
                # ★★★ 2. حذف معاملات الصندوق المرتبطة بالفاتورة ★★★
                cash_transactions_count = CashTransaction.objects.filter(
                    purchase_invoice=purchase
                ).count()
                
                if cash_transactions_count > 0:
                    CashTransaction.objects.filter(
                        purchase_invoice=purchase
                    ).delete()
                    logger.info(f"✅ تم حذف {cash_transactions_count} معاملة صندوق مرتبطة بالفاتورة {purchase.uniqueId}")
                
                # ★★★ 3. حذف الباركودات المرتبطة ★★★
                barcodes_to_delete = []
                for purch_item in purchase.purchitem_set.all():
                    for purch_barcode in purch_item.item_barcodes.all():
                        barcodes_to_delete.append(purch_barcode.barcode)
                    PurchItemBarcode.objects.filter(purch_item=purch_item).delete()
                
                # ★★★ 4. حذف الفاتورة ★★★
                purchase.delete()
                
                # ★★★ 5. حذف الباركودات التي لم تعد مرتبطة بأي فاتورة ★★★
                deleted_barcodes_count = 0
                for barcode in barcodes_to_delete:
                    if not PurchItemBarcode.objects.filter(barcode=barcode).exists():
                        barcode.delete()
                        deleted_barcodes_count += 1
                
                # رسالة النجاح مع تفاصيل الكميات المسترجعة
                items_summary = ", ".join([f"{item['product']} ({item['quantity']})" for item in items_updated[:5]])
                if len(items_updated) > 5:
                    items_summary += f" و {len(items_updated) - 5} منتجات أخرى"
                
                messages.success(
                    request, 
                    _(f'✅ تم حذف فاتورة الشراء بنجاح.\n'
                      f'📦 تم استرجاع {len(items_updated)} منتج من المخزون: {items_summary}\n'
                      f'🏷️ تم حذف {deleted_barcodes_count} باركود\n'
                      f'💰 تم حذف {cash_transactions_count} معاملة صندوق')
                )
                return redirect('invoice:purch_list')
                
        except Exception as e:
            logger.error(f"Error deleting purchase {purchase.uniqueId}: {str(e)}", exc_info=True)
            messages.error(request, 'حدث خطأ أثناء حذف الفاتورة، يرجى المحاولة مرة أخرى.')
    
    return render(request, 'invoice/purchase/purch_confirm_delete.html', {
        'purchase': purchase, 'title': _('حذف فاتورة شراء')
    })











#================================================
#                 مرتجع المشتريات              #
# ===============================================

@login_required
@permission_required('invoice.add_purchasereturn', raise_exception=True)
def purch_return_create_view(request, slug):
    """إنشاء مرتجع فاتورة مشتريات"""
    original_purchase = get_object_or_404(Purch, slug=slug)
    
    if original_purchase.created_by and original_purchase.created_by != request.user and not request.user.is_superuser:
        raise PermissionDenied(_("ليس لديك صلاحية لإنشاء مرتجع لهذه الفاتورة"))
    
    if not original_purchase.purchitem_set.exists():
        messages.warning(request, 'لا توجد بنود في هذه الفاتورة للإرجاع')
        return redirect('invoice:purch_detail', slug=slug)
    
    original_payment_method = original_purchase.purch_payment_method
    payment_method_name = original_payment_method.name if original_payment_method else 'على الآجل'
    is_cash_payment = original_payment_method.is_cash if original_payment_method and hasattr(original_payment_method, 'is_cash') else False
    
    reset_date = original_purchase.last_updated
    
    returned_items_data = {}
    for item in original_purchase.purchitem_set.all():
        total_returned = item.returned_items.filter(
            purchase_return__date_created__gte=reset_date
        ).aggregate(total=Sum('returned_quantity'))['total']
        returned_items_data[item.id] = total_returned if total_returned else Decimal('0.00')
    
    expected_return_total = Decimal('0.00')
    for item in original_purchase.purchitem_set.all():
        returned_quantity = returned_items_data.get(item.id, Decimal('0.00'))
        available_quantity = item.purchased_quantity - returned_quantity
        if available_quantity > 0:
            expected_return_total += available_quantity * item.unit_price
    
    if request.method == 'POST':
        # نسخ البيانات مع تعيين قيمة افتراضية لـ paid_amount
        post_data = request.POST.copy()
        
        # إذا كان الدفع نقدياً، تأكد من وجود قيمة للحقل
        if is_cash_payment:
            if 'paid_amount' not in post_data or post_data.get('paid_amount', '').strip() == '':
                post_data['paid_amount'] = str(expected_return_total)
        else:
            # إذا لم يكن نقدياً، اجعل القيمة صفراً
            post_data['paid_amount'] = '0.00'
        
        # إنشاء النموذج مع تمرير المعاملات المطلوبة
        form = PurchaseReturnForm(
            post_data,
            is_cash_payment=is_cash_payment,
            return_final_total=expected_return_total
        )
        
        items_data = []
        form_valid = True
        has_any_returned_items = False
        actual_return_total = Decimal('0.00')
        
        original_items = original_purchase.purchitem_set.all().select_related('product')
        
        for item in original_items:
            returned_quantity = returned_items_data.get(item.id, Decimal('0.00'))
            available_quantity = item.purchased_quantity - returned_quantity
            prefix = f"item-{item.id}"
            
            available_barcodes = PurchItemBarcode.objects.filter(
                purch_item=item, 
                barcode_status='active',
                barcode__status='active' 
            ).select_related('barcode')
            
            barcode_queryset = Barcode.objects.filter(id__in=available_barcodes.values_list('barcode_id', flat=True))
            
            item_form = PurchaseReturnItemForm(request.POST, prefix=prefix, original_item=item)
            item_form.fields['original_barcodes'].queryset = barcode_queryset
            has_barcodes = available_barcodes.exists()
            
            if has_barcodes and item_form.is_valid():
                selected_barcodes = item_form.cleaned_data.get('original_barcodes', [])
                if selected_barcodes:
                    item_form.cleaned_data['returned_quantity'] = Decimal(str(len(selected_barcodes)))
                    item_form.data = item_form.data.copy()
                    item_form.data[f"{prefix}-returned_quantity"] = str(len(selected_barcodes))
            
            if not item_form.is_valid():
                form_valid = False
                logger.error(f"خطأ في نموذج البند {item.id}: {item_form.errors}")
            
            if item_form.is_valid():
                returned_quantity_value = item_form.cleaned_data.get('returned_quantity', Decimal('0.00'))
                if returned_quantity_value and returned_quantity_value > 0:
                    has_any_returned_items = True
                    unit_price = item_form.cleaned_data.get('return_unit_price', Decimal('0.00'))
                    actual_return_total += returned_quantity_value * unit_price
            
            items_data.append({
                'form': item_form, 'original_item': item,
                'product': item.product if hasattr(item, 'product') else None,
                'available_quantity': available_quantity, 'previously_returned': returned_quantity,
                'available_barcodes': available_barcodes, 'available_barcodes_count': available_barcodes.count(),
                'has_barcodes': has_barcodes
            })
        
        if form.is_valid() and form_valid:
            if not has_any_returned_items:
                messages.error(request, 'يجب إدخال كمية مرتجعة لبند واحد على الأقل')
                context = {
                    'form': form, 'items_data': items_data, 'original_purchase': original_purchase,
                    'payment_method_name': payment_method_name, 'is_cash_payment': is_cash_payment,
                    'expected_return_total': expected_return_total,
                    'title': f'إنشاء مرتجع لفاتورة شراء {original_purchase.uniqueId}'
                }
                return render(request, 'invoice/purchase/purch_return_form.html', context)
            
            try:
                with transaction.atomic():
                    purchase_return = form.save(commit=False)
                    purchase_return.original_purchase = original_purchase
                    purchase_return.created_by = request.user
                    purchase_return.purch_supplier = original_purchase.purch_supplier
                    if hasattr(original_purchase, 'purch_currency'):
                        purchase_return.purch_currency = original_purchase.purch_currency
                    
                    # التأكد من تعيين المبلغ المستلم بشكل صحيح
                    paid_amount = Decimal('0.00')
                    if is_cash_payment:
                        paid_amount = form.cleaned_data.get('paid_amount', Decimal('0.00'))
                        if paid_amount is None or paid_amount == '':
                            paid_amount = actual_return_total
                    else:
                        paid_amount = Decimal('0.00')
                    
                    purchase_return.paid_amount = paid_amount
                    purchase_return.remaining_amount = Decimal('0.00')
                    purchase_return.settlement_status = 'pending'
                    purchase_return.return_final_total = actual_return_total
                    purchase_return.save()
                    
                    saved_items = False
                    for item_data in items_data:
                        item_form = item_data['form']
                        if item_form.is_valid():
                            returned_quantity = item_form.cleaned_data.get('returned_quantity', Decimal('0.00'))
                            if returned_quantity and returned_quantity > 0:
                                item_instance = item_form.save(commit=False)
                                item_instance.purchase_return = purchase_return
                                item_instance.return_total = returned_quantity * item_form.cleaned_data.get('return_unit_price', Decimal('0.00'))
                                if not item_instance.product and item_data['original_item'].product:
                                    item_instance.product = item_data['original_item'].product
                                item_instance.save()
                                
                                returned_barcodes = item_form.cleaned_data.get('original_barcodes')
                                if returned_barcodes:
                                    for barcode in returned_barcodes:
                                        PurchaseReturnItemBarcode.objects.create(
                                            purchase_return_item=item_instance, barcode=barcode
                                        )
                                saved_items = True
                    
                    if not saved_items:
                        purchase_return.delete()
                        messages.warning(request, 'لم يتم تحديد أي كميات للاسترجاع')
                        return redirect('invoice:purch_detail', slug=slug)
                    
                    purchase_return.refresh_from_db()
                    purchase_return.return_subtotal = actual_return_total
                    purchase_return.return_final_total = actual_return_total
                    purchase_return.remaining_amount = actual_return_total - paid_amount
                    purchase_return.update_settlement_status()
                    purchase_return.save(update_fields=['return_subtotal', 'return_final_total', 'remaining_amount', 'settlement_status'])
                    
                    # ==================== تحديث فاتورة الشراء الأصلية ====================
                    # تحديث المبلغ المدفوع في فاتورة الشراء الأصلية
                    if is_cash_payment and paid_amount > 0:
                        # إضافة المبلغ المستلم إلى paid_amount في فاتورة الشراء الأصلية
                        original_purchase.paid_amount = F('paid_amount') + paid_amount
                        original_purchase.save(update_fields=['paid_amount'])
                        
                        # تحديث الرصيد المتبقي
                        original_purchase.refresh_from_db()
                        original_purchase.balance_due = original_purchase.purch_final_total - original_purchase.paid_amount
                        original_purchase.is_paid = original_purchase.balance_due <= 0
                        original_purchase.save(update_fields=['balance_due', 'is_paid'])
                    
                    # ==================== تسجيل حركة الصندوق ====================
                    if is_cash_payment and paid_amount > 0:
                        try:
                            # تسجيل حركة الصندوق التفصيلية (CashTransaction)
                            CashTransaction.objects.create(
                                transaction_date=timezone.now(), 
                                amount_in=paid_amount,
                                amount_out=Decimal('0.00'),
                                transaction_type='purchase_return',
                                notes=f"استلام {paid_amount} مقابل مرتجع فاتورة {original_purchase.uniqueId}",
                                created_by=request.user, 
                                purchase_invoice=original_purchase,
                                purchase_return=purchase_return,
                                payment_method=original_payment_method
                            )
                            
                            logger.info(f"تم تسجيل حركة الصندوق: +{paid_amount} | مرتجع فاتورة {original_purchase.uniqueId}")
                            
                        except Exception as e:
                            logger.error(f"خطأ في تسجيل حركة الصندوق: {e}")
                            messages.warning(request, 'تم إنشاء المرتجع ولكن حدث خطأ في تسجيل حركة الصندوق')
                    
                    messages.success(request, f'✅ تم إنشاء فاتورة المرتجع {purchase_return.uniqueId} بنجاح')
                    return redirect('invoice:purchase_return_detail', slug=purchase_return.slug)
                    
            except Exception as e:
                logger.error(f"خطأ في إنشاء المرتجع: {str(e)}", exc_info=True)
                messages.error(request, 'حدث خطأ غير متوقع أثناء إنشاء المرتجع، يرجى المحاولة مرة أخرى.')
        else:
            error_messages = []
            if form.errors:
                for field, errors in form.errors.items():
                    for error in errors:
                        label = form.fields[field].label if field in form.fields else field
                        error_messages.append(f"{label}: {error}")
            
            for item_data in items_data:
                if item_data['form'].errors:
                    item_name = item_data['product'].product_name if item_data['product'] else f"بند {item_data['original_item'].id}"
                    for field, errors in item_data['form'].errors.items():
                        for error in errors:
                            error_messages.append(f"{item_name} - {error}")
            
            if error_messages:
                messages.error(request, 'يرجى تصحيح الأخطاء التالية:')
                for error_msg in error_messages[:5]:
                    messages.error(request, f"• {error_msg}")
            
            context = {
                'form': form, 'items_data': items_data, 'original_purchase': original_purchase,
                'payment_method_name': payment_method_name, 'is_cash_payment': is_cash_payment,
                'expected_return_total': expected_return_total,
                'title': f'إنشاء مرتجع لفاتورة شراء {original_purchase.uniqueId}'
            }
            return render(request, 'invoice/purchase/purch_return_form.html', context)
    
    else:
        # طلب GET - تهيئة النموذج
        initial_data = {
            'return_date': timezone.now().date(),
            'paid_amount': expected_return_total if is_cash_payment else Decimal('0.00')
        }
        
        form = PurchaseReturnForm(
            initial=initial_data,
            is_cash_payment=is_cash_payment,
            return_final_total=expected_return_total
        )
        
        items_data = []
        original_items = original_purchase.purchitem_set.all().select_related('product')
        
        for item in original_items:
            total_returned = returned_items_data.get(item.id, Decimal('0.00'))
            available_quantity = item.purchased_quantity - total_returned
            prefix = f"item-{item.id}"
            
            available_barcodes = PurchItemBarcode.objects.filter(
                purch_item=item, 
                barcode_status='active',
                barcode__status='active'
            ).select_related('barcode')
            
            initial_data = {
                'original_item': item, 
                'product': item.product, 
                'purchased_quantity': item.purchased_quantity, 
                'return_unit_price': item.unit_price, 
                'return_total': Decimal('0.00'), 
                'returned_quantity': ''
            }
            
            item_form = PurchaseReturnItemForm(prefix=prefix, initial=initial_data, original_item=item)
            item_form.fields['original_barcodes'].queryset = Barcode.objects.filter(
                id__in=available_barcodes.values_list('barcode_id', flat=True)
            )
            has_barcodes = available_barcodes.exists()
            
            if available_quantity > 0:
                if has_barcodes:
                    item_form.fields['returned_quantity'].widget.attrs.update({
                        'readonly': True, 
                        'placeholder': 'اختر الباركودات', 
                        'class': 'quantity-with-barcode form-control text-center'
                    })
                else:
                    item_form.fields['returned_quantity'].widget.attrs.update({
                        'max': available_quantity, 
                        'readonly': False, 
                        'placeholder': 'أدخل الكمية', 
                        'class': 'quantity-without-barcode form-control text-center'
                    })
            else:
                item_form.fields['returned_quantity'].widget.attrs.update({
                    'readonly': True, 
                    'placeholder': 'غير متاح', 
                    'value': '0', 
                    'class': 'form-control text-center bg-light'
                })
            
            items_data.append({
                'form': item_form, 
                'original_item': item, 
                'product': item.product,
                'available_quantity': available_quantity, 
                'previously_returned': total_returned,
                'available_barcodes': available_barcodes, 
                'available_barcodes_count': available_barcodes.count(),
                'has_barcodes': has_barcodes,
                'item_image': item.purch_item_image or (item.product.product_image if item.product else None)
            })
    
    context = {
        'form': form, 
        'items_data': items_data, 
        'original_purchase': original_purchase,
        'payment_method_name': payment_method_name, 
        'is_cash_payment': is_cash_payment,
        'title': f'إنشاء مرتجع لفاتورة شراء {original_purchase.uniqueId}',
        'supplier': original_purchase.purch_supplier,
        'total_invoice_amount': original_purchase.purch_final_total,
        'expected_return_total': expected_return_total,
    }
    return render(request, 'invoice/purchase/purch_return_form.html', context)


@login_required
@permission_required('invoice.view_purchasereturn', raise_exception=True)
def purchase_return_list_view(request):
    """قائمة مرتجعات المشتريات"""
    from django.db.models import Q
    from django.core.paginator import Paginator
    
    user = request.user
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    supplier_filter = request.GET.get('supplier', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    if user.is_superuser:
        purchase_returns = PurchaseReturn.objects.all().select_related('original_purchase', 'created_by', 'purch_supplier').order_by('-return_date', '-date_created')
    else:
        purchase_returns = PurchaseReturn.objects.filter(Q(created_by=user) | Q(purch_supplier=user)).distinct().select_related('original_purchase', 'created_by', 'purch_supplier').order_by('-return_date', '-date_created')
    
    if search_query:
        purchase_returns = purchase_returns.filter(Q(uniqueId__icontains=search_query) | Q(purch_supplier__username__icontains=search_query) | Q(purch_supplier__first_name__icontains=search_query) | Q(purch_supplier__last_name__icontains=search_query) | Q(original_purchase__uniqueId__icontains=search_query))
    if status_filter:
        if status_filter == 'completed': purchase_returns = purchase_returns.filter(settlement_status='settled')
        elif status_filter == 'partial': purchase_returns = purchase_returns.filter(settlement_status='partial')
        elif status_filter == 'pending': purchase_returns = purchase_returns.filter(settlement_status='pending')
    if supplier_filter and supplier_filter.isdigit(): purchase_returns = purchase_returns.filter(purch_supplier_id=supplier_filter)
    if date_from: purchase_returns = purchase_returns.filter(return_date__gte=date_from)
    if date_to: purchase_returns = purchase_returns.filter(return_date__lte=date_to)
    
    paginator = Paginator(purchase_returns, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    suppliers = User.objects.filter(is_active=True).order_by('username')
    
    context = {'purchase_returns': page_obj, 'page_obj': page_obj, 'suppliers': suppliers, 'title': 'قائمة مرتجعات المشتريات', 'search_query': search_query, 'status_filter': status_filter}
    return render(request, 'invoice/purchase/purchase_return_list.html', context)


@login_required
@permission_required('invoice.view_purchasereturn', raise_exception=True)
def purchase_return_detail_view(request, slug):
    """عرض تفاصيل مرتجع المشتريات"""
    # ★ التعديل هنا: إضافة prefetch_related للباركودات لتحسين الأداء ومنع استعلامات N+1
    purchase_return = get_object_or_404(
        PurchaseReturn.objects.select_related(
            'original_purchase', 'created_by', 'purch_supplier'
        ).prefetch_related(
            'return_items__product', 
            'return_items__returned_barcodes__barcode'  # ★ إضافة الباركودات
        ), 
        slug=slug
    )
    
    user = request.user
    is_allowed = (user.is_superuser or purchase_return.created_by == user or purchase_return.purch_supplier == user)
    if not is_allowed:
        raise PermissionDenied(_("ليس لديك صلاحية للوصول إلى هذا المرتجع"))
    
    items = purchase_return.return_items.all()
    items_count = items.count()
    total_quantity = items.aggregate(total=Sum('returned_quantity'))['total'] or 0
    
    context = {
        'return': purchase_return, 
        'purchase_return': purchase_return, 
        'items': items, 
        'items_count': items_count, 
        'total_quantity': total_quantity, 
        'title': f'تفاصيل مرتجع المشتريات {purchase_return.uniqueId}'
    }
    return render(request, 'invoice/purchase/purch_return_detail.html', context)


@login_required
@permission_required('invoice.delete_purchasereturn', raise_exception=True)
def purchase_return_delete_view(request, slug):
    """حذف مرتجع المشتريات مع استرجاع الكميات إلى المخزون ومعاملات الصندوق"""
    purchase_return = get_object_or_404(PurchaseReturn, slug=slug)
    
    if purchase_return.created_by and purchase_return.created_by != request.user and not request.user.is_superuser:
        raise PermissionDenied(_("ليس لديك صلاحية لحذف هذا المرتجع"))
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                original_purch_slug = purchase_return.original_purchase.slug if purchase_return.original_purchase else None
                return_uniqueId = purchase_return.uniqueId
                paid_amount = purchase_return.paid_amount or Decimal('0.00')
                original_purchase = purchase_return.original_purchase
                
                # ★★★ 1. استرجاع الكميات المرتجعة إلى المخزون ★★★
                items_restored = []
                for return_item in purchase_return.return_items.all().select_related('product'):
                    if return_item.product:
                        product = return_item.product
                        product.refresh_from_db()
                        
                        returned_quantity = return_item.returned_quantity or Decimal('0.00')
                        
                        if returned_quantity > 0:
                            # إعادة الكمية إلى المخزون (لأن المرتجع كان يقلل المخزون)
                            product.current_stock_quantity = F('current_stock_quantity') + returned_quantity
                            product.save(update_fields=['current_stock_quantity'])
                            product.refresh_from_db()
                            
                            # إعادة حساب متوسط التكلفة
                            if product.current_stock_quantity > 0:
                                total_value = product.current_stock_quantity * product.average_purchase_cost
                                product.average_purchase_cost = (total_value / product.current_stock_quantity).quantize(Decimal('0.01'))
                                product.save(update_fields=['average_purchase_cost'])
                            
                            items_restored.append({
                                'product': product.product_name,
                                'quantity': returned_quantity
                            })
                            logger.info(f"✅ تم استرجاع {returned_quantity} من المنتج {product.product_name} إلى المخزون")
                
                # ★★★ 2. حذف معاملات الصندوق المرتبطة بالمرتجع ★★★
                cash_transactions_count = CashTransaction.objects.filter(
                    purchase_return=purchase_return
                ).count()
                
                if cash_transactions_count > 0:
                    CashTransaction.objects.filter(
                        purchase_return=purchase_return
                    ).delete()
                    logger.info(f"✅ تم حذف {cash_transactions_count} معاملة صندوق مرتبطة بالمرتجع {return_uniqueId}")
                
                # ★★★ 3. استرجاع المبلغ المدفوع إلى فاتورة الشراء الأصلية ★★★
                if original_purchase and paid_amount > 0:
                    original_purchase.paid_amount = F('paid_amount') - paid_amount
                    original_purchase.save(update_fields=['paid_amount'])
                    
                    original_purchase.refresh_from_db()
                    original_purchase.balance_due = original_purchase.purch_final_total - original_purchase.paid_amount
                    original_purchase.is_paid = original_purchase.balance_due <= 0
                    original_purchase.save(update_fields=['balance_due', 'is_paid'])
                    
                    logger.info(f"✅ تم استرجاع {paid_amount} من المبلغ المدفوع إلى الفاتورة {original_purchase.uniqueId}")
                
                # ★★★ 4. حذف المرتجع ★★★
                purchase_return.delete()
                
                items_summary = ", ".join([f"{item['product']} ({item['quantity']})" for item in items_restored[:5]])
                if len(items_restored) > 5:
                    items_summary += f" و {len(items_restored) - 5} منتجات أخرى"
                
                messages.success(
                    request, 
                    f'✅ تم حذف مرتجع المشتريات {return_uniqueId} بنجاح.\n'
                    f'📦 تم استرجاع {len(items_restored)} منتج إلى المخزون: {items_summary}\n'
                    f'💰 تم حذف {cash_transactions_count} معاملة صندوق'
                )
                
                if original_purch_slug:
                    return redirect('invoice:purch_detail', slug=original_purch_slug)
                else:
                    return redirect('invoice:purchase_return_list')
                
        except Exception as e:
            logger.error(f"Error deleting purchase return {slug}: {str(e)}", exc_info=True)
            messages.error(request, 'حدث خطأ أثناء حذف المرتجع، يرجى المحاولة مرة أخرى.')
            return redirect('invoice:purchase_return_detail', slug=slug)
    
    context = {
        'purchase_return': purchase_return, 
        'title': f'حذف مرتجع المشتريات {purchase_return.uniqueId}'
    }
    return render(request, 'invoice/purchase/purchase_return_confirm_delete.html', context)









@login_required
@permission_required('invoice.add_sale', raise_exception=True)
def sale_create(request):
    """إنشاء فاتورة بيع جديدة مع منطق التحقق المحسّن والأمان المضاد لـ SSRF."""
    if request.method == 'POST':
        form = SaleForm(request.POST, request.FILES)
        formset = SaleItemFormSet(request.POST, request.FILES, prefix='items')
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    sale = form.save(commit=False)
                    sale.created_by = request.user
                    
                    if not sale.uniqueId:
                        last_invoice = Sale.objects.order_by('-_last_invoice_number').first()
                        last_number = last_invoice._last_invoice_number if last_invoice else 0
                        new_number = last_number + 1
                        sale._last_invoice_number = new_number
                        sale.uniqueId = f"S{new_number:04d}"
                        
                    if not sale.slug:
                        sale.slug = slugify(f"sale-{sale.uniqueId}")
                    sale.save()

                    instances = formset.save(commit=False)
                    
                    for i, instance in enumerate(instances):
                        instance.sale = sale
                        product_id_from_form = request.POST.get(f'items-{i}-product')
                        product_search_value = request.POST.get(f'items-{i}-product_search', '')
                        
                        if not instance.product and product_id_from_form and product_id_from_form != '':
                            try:
                                instance.product = Product.objects.get(id=product_id_from_form)
                            except Product.DoesNotExist:
                                pass
                        
                        if not instance.product and product_search_value and product_search_value != "مادة غير محددة":
                            try:
                                instance.product = Product.objects.get(product_name=product_search_value)
                            except (Product.DoesNotExist, Product.MultipleObjectsReturned):
                                instance.product = Product.objects.filter(product_name=product_search_value).first()
                        
                        if not instance.item_name and instance.product:
                            instance.item_name = instance.product.product_name
                        elif not instance.item_name:
                            instance.item_name = product_search_value if product_search_value else "مادة غير محددة"
                        
                        # ==========================================
                        # التعامل الآمن مع صورة البند (SSRF Fix)
                        # ==========================================
                        image_field_name = f'items-{i}-sale_item_image'
                        
                        if image_field_name in request.FILES:
                            # الحالة الأولى: المستخدم قام برفع صورة يدوياً (آمن تماماً)
                            pass 
                        elif instance.product and hasattr(instance.product, 'product_image') and instance.product.product_image:
                            # الحالة الثانية: نسخ صورة المنتج تلقائياً (محمي 100%)
                            try:
                                # نأخذ مسار الملف مباشرة من قاعدة البيانات (وليس من الـ POST)
                                image_path = instance.product.product_image.name
                                
                                # نتحقق من وجود الملف في نظام التخزين (سواء كان Local أو S3)
                                if default_storage.exists(image_path):
                                    # نفتح الملف بشكل آمن وبدون استخدام requests.get
                                    with default_storage.open(image_path, 'rb') as f:
                                        filename = os.path.basename(image_path)
                                        instance.sale_item_image.save(filename, File(f), save=False)
                            except Exception as e:
                                # إذا فشل النسخ الآمن لسبب تقني (مثل أذونات الملفات)، نسجل الخطأ ولا نوقف الفاتورة
                                logger.error(f"خطأ أمني/تقني في نسخ الصورة التلقائية للمنتج {instance.product_id}: {e}")
                        
                        # ==========================================
                        # حساب الكميات (مع باركود وبدون باركود)
                        # ==========================================
                        qty_sold_with_barcode = Decimal('0.00')
                        qty_sold_without_barcode = Decimal('0.00')
                        
                        if instance.product:
                            product = instance.product
                            barcodes_key = f'item_{i}_barcodes'
                            submitted_barcodes = request.POST.getlist(barcodes_key)
                            valid_submitted_barcodes = [b.strip() for b in submitted_barcodes if b.strip()]
                            
                            qty_sold_with_barcode = Decimal(str(len(valid_submitted_barcodes)))
                            qty_input_value = request.POST.get(f'items-{i}-sold_quantity', '0')
                            try:
                                manual_qty = Decimal(qty_input_value)
                            except:
                                manual_qty = Decimal('0.00')
                            
                            if manual_qty > qty_sold_with_barcode:
                                qty_sold_without_barcode = manual_qty - qty_sold_with_barcode
                            else:
                                if qty_sold_with_barcode == 0:
                                     qty_sold_without_barcode = manual_qty
                            
                            instance.quantity_with_barcode = qty_sold_with_barcode
                            instance.quantity_without_barcode = qty_sold_without_barcode
                            instance.sold_quantity = qty_sold_with_barcode + qty_sold_without_barcode
                            
                            # ==========================================
                            # التحقق الصارم من المخزون
                            # ==========================================
                            total_stock = product.current_stock_quantity
                            available_barcodes_count = Barcode.objects.filter(product=product, status='active').count()
                            non_barcoded_stock = max(Decimal('0.00'), total_stock - Decimal(str(available_barcodes_count)))
                            
                            errors = []
                            if instance.sold_quantity > total_stock:
                                errors.append(f"الكمية المطلوبة ({instance.sold_quantity}) تتجاوز المخزون ({total_stock})")
                            if qty_sold_with_barcode > available_barcodes_count:
                                errors.append(f"عدد الباركودات ({qty_sold_with_barcode}) يتجاوز المتاح ({available_barcodes_count})")
                            if qty_sold_without_barcode > non_barcoded_stock:
                                errors.append(f"الكمية بدون باركود ({qty_sold_without_barcode}) تتجاوز المخزون غير المباركود ({non_barcoded_stock})")
                            
                            for barcode_value in valid_submitted_barcodes:
                                if not Barcode.objects.filter(barcode_in=barcode_value, product=product, status='active').exists():
                                    errors.append(f"الباركود '{barcode_value}' غير متاح")
                            
                            if errors:
                                raise ValidationError(f"خطأ في بند '{product.product_name}': " + " | ".join(errors))
                        
                        instance.save()
                        
                        if instance.product:
                            instance.update_product_stock()
                        
                        # ==========================================
                        # ربط الباركودات وتغيير حالتها
                        # ==========================================
                        for barcode_value in valid_submitted_barcodes:
                            barcode_value = barcode_value.strip()
                            if barcode_value:
                                try:
                                    barcode_obj = Barcode.objects.get(barcode_in=barcode_value, product=instance.product, status='active')
                                    SaleItemBarcode.objects.create(sale_item=instance, barcode=barcode_obj, quantity_used=Decimal('1.00'), barcode_status='active')
                                    barcode_obj.status = 'sold'
                                    barcode_obj.save()
                                except Barcode.DoesNotExist:
                                    pass
                                except Exception as e:
                                    logger.error(f"خطأ في ربط الباركود {barcode_value}: {e}")
                    
                    # حذف البنود المحذوفة من الواجهة
                    for instance in formset.deleted_objects:
                        instance.item_barcodes.all().delete()
                        instance.delete()
                    
                    # حساب الإجماليات المالية
                    sale.calculate_and_save_totals()

                    # التحقق من المبلغ المدفوع
                    paid_amt = Decimal(str(request.POST.get('paid_amount', '0')))
                    if paid_amt > sale.sale_final_total:
                        raise ValidationError("المبلغ المدفوع لا يمكن أن يتجاوز الإجمالي النهائي للفاتورة")

                    sale.paid_amount = paid_amt
                    sale.balance_due = sale.sale_final_total - sale.paid_amount
                    sale.is_paid = sale.balance_due <= 0
                    sale.save(update_fields=['paid_amount', 'balance_due', 'is_paid'])

                    # إنشاء حركة الصندوق إذا كانت نقدية
                    if sale.paid_amount > 0 and sale.sale_payment_method and sale.sale_payment_method.is_cash:
                        sale.create_cash_transaction()
                    
                    messages.success(request, 'تم إنشاء فاتورة البيع بنجاح وتحديث المخزون')
                    return redirect('invoice:sale_detail', slug=sale.slug)
                    
            except ValidationError as e:
                messages.error(request, e.messages[0] if hasattr(e, 'messages') and e.messages else str(e))
            except Exception as e:
                logger.error(f"خطأ في إنشاء فاتورة البيع: {e}", exc_info=True)
                messages.error(request, 'حدث خطأ غير متوقع أثناء إنشاء الفاتورة')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج.')
                
    else:
        form = SaleForm(initial={'sale_date': timezone.now().date(), 'paid_amount': 0, 'sale_tax_percentage': 0, 'sale_discount': 0, 'sale_addition': 0})
        formset = SaleItemFormSet(prefix='items', queryset=SaleItem.objects.none())
    
    products = Product.objects.all()
    return render(request, 'invoice/sale/sale_form.html', {'form': form, 'formset': formset, 'products': products, 'title': 'إنشاء فاتورة بيع جديدة'})




def handle_sale_cash_transaction(sale):
    """دالة مساعدة ولا تحتاج لديكوريتورات"""
    from .models import CashTransaction
    existing = CashTransaction.objects.filter(sale_invoice=sale, transaction_type='sale_receipt').first()
    is_cash = sale.sale_payment_method and sale.sale_payment_method.is_cash
    if sale.paid_amount > 0 and is_cash:
        if existing:
            existing.amount_in = sale.paid_amount
            existing.save()
        else:
            CashTransaction.objects.create(transaction_date=timezone.now(), amount_in=sale.paid_amount, transaction_type='sale_receipt', payment_method=sale.sale_payment_method, sale_invoice=sale, notes=f"تحصيل فاتورة {sale.uniqueId}", created_by=sale.created_by)
    else:
        if existing:
            existing.delete()


@login_required
@permission_required('invoice.view_sale', raise_exception=True)
def sale_detail(request, slug):
    """عرض تفاصيل فاتورة بيع محددة"""
    sale = get_object_or_404(Sale.objects.select_related('sale_customer', 'sale_payment_method', 'sale_currency', 'sale_status', 'sale_shipping_company', 'created_by'), slug=slug)
    
    user = request.user
    is_allowed = (user.is_superuser or sale.created_by == user or sale.sale_customer == user)
    if not is_allowed:
        raise PermissionDenied(_("ليس لديك صلاحية للوصول إلى هذه الفاتورة"))
    
    items = sale.saleitem_set.all().order_by('id')
    items_with_barcodes = []
    for item in items:
        barcode_links = item.item_barcodes.filter(barcode_status='active').select_related('barcode')
        barcodes = [{'code': link.barcode.barcode_in, 'status': link.barcode_status} for link in barcode_links]
        items_with_barcodes.append({'item': item, 'barcodes': barcodes})
    
    total_items = items.count()
    total_quantity = sum(item.sold_quantity for item in items)
    
    context = {'sale': sale, 'items_with_barcodes': items_with_barcodes, 'total_items': total_items, 'total_quantity': total_quantity, 'title': f'تفاصيل فاتورة البيع {sale.uniqueId}'}
    return render(request, 'invoice/sale/sale_detail.html', context)


@login_required
@permission_required('invoice.change_sale', raise_exception=True)
def sale_edit(request, slug):
    """تعديل فاتورة بيع موجودة."""
    sale = get_object_or_404(Sale, slug=slug)
    
    # التحقق من صلاحية التعديل
    if sale.created_by and sale.created_by != request.user and not request.user.is_superuser:
        raise PermissionDenied(_("ليس لديك صلاحية لتعديل هذه الفاتورة"))
    
    # إنشاء Formset للبنود
    SaleItemEditFormSet = inlineformset_factory(
        Sale, 
        SaleItem, 
        form=SaleItemForm, 
        extra=0, 
        can_delete=True, 
        can_order=False
    )
    
    if request.method == 'POST':
        form = SaleForm(request.POST, request.FILES, instance=sale)
        formset = SaleItemEditFormSet(request.POST, request.FILES, instance=sale, prefix='items')
        
        # تسجيل الأخطاء التفصيلية قبل التحقق
        if not form.is_valid():
            logger.error(f"❌ أخطاء نموذج الفاتورة: {form.errors.as_json()}")
        
        if not formset.is_valid():
            logger.error(f"❌ أخطاء نموذج البنود: {formset.errors}")
            for i, err in enumerate(formset.errors):
                if err: logger.error(f"  بند {i}: {err}")
            non_form_errors = formset.non_form_errors()
            if non_form_errors: logger.error(f"  أخطاء عامة للفورمست: {non_form_errors}")
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # حفظ الفاتورة الأساسية
                    updated_sale = form.save(commit=False)
                    
                    # قراءة القيم المالية من cleaned_data
                    updated_sale.sale_tax_percentage = form.cleaned_data.get('sale_tax_percentage', Decimal('0.00'))
                    updated_sale.sale_discount = form.cleaned_data.get('sale_discount', Decimal('0.00'))
                    updated_sale.sale_addition = form.cleaned_data.get('sale_addition', Decimal('0.00'))
                    updated_sale.paid_amount = form.cleaned_data.get('paid_amount', Decimal('0.00'))
                    
                    updated_sale.save()
                    
                    # ============================================
                    # معالجة البنود المحذوفة
                    # ============================================
                    for form_del in formset.deleted_forms:
                        del_instance = form_del.instance
                        if del_instance and del_instance.pk:
                            # ✅✅✅ حذف باركودات البند يدوياً لتفعيل المنطق المبرمج في delete()
                            for bc_item in del_instance.item_barcodes.all():
                                bc_item.delete()
                            del_instance.delete()
                    
                    # ============================================
                    # معالجة كل بند
                    # ============================================
                    for form_item in formset:
                        # تخطي البنود المحذوفة
                        if form_item in formset.deleted_forms:
                            continue
                        
                        # تخطي البنود الفارغة التي لم تتغير وليست جديدة
                        if not form_item.has_changed() and not form_item.instance.pk:
                            continue
                        
                        instance = form_item.save(commit=False)
                        instance.sale = updated_sale
                        
                        # الحصول على فهرس النموذج الصحيح
                        form_prefix = form_item.prefix or 'items-0'
                        form_index = int(form_prefix.split('-')[1]) if '-' in form_prefix else 0
                        
                        # ============================================
                        # تهيئة المتغيرات القديمة للمقارنة
                        # ============================================
                        old_instance = None
                        old_quantity = Decimal('0.00')
                        old_product = None
                        barcodes_to_add = set()
                        barcodes_to_remove = set()
                        product = None
                        errors = []
                        
                        # حفظ البيانات القديمة قبل التحديث
                        if instance.pk:
                            try:
                                old_instance = SaleItem.objects.get(pk=instance.pk)
                                old_quantity = old_instance.sold_quantity or Decimal('0.00')
                                old_product = old_instance.product
                            except SaleItem.DoesNotExist:
                                pass
                        
                        # ============================================
                        # معالجة المنتج
                        # ============================================
                        product_id_from_form = request.POST.get(f'items-{form_index}-product')
                        product_search_value = request.POST.get(f'items-{form_index}-product_search', '')
                        
                        if not instance.product and product_id_from_form:
                            try:
                                instance.product = Product.objects.get(id=product_id_from_form)
                            except Product.DoesNotExist:
                                pass
                        
                        if not instance.product and product_search_value and product_search_value != "مادة غير محددة":
                            instance.product = Product.objects.filter(product_name=product_search_value).first()
                        
                        if not instance.item_name:
                            if instance.product:
                                instance.item_name = instance.product.product_name
                            else:
                                instance.item_name = product_search_value if product_search_value else "مادة غير محددة"
                        
                        # ============================================
                        # قراءة الكمية المباعة من النموذج
                        # ============================================
                        manual_qty = form_item.cleaned_data.get('sold_quantity', Decimal('1.00'))
                        if manual_qty is None:
                            manual_qty = Decimal('1.00')
                        
                        # ============================================
                        # معالجة الباركودات المقدمة من الجافاسكربت
                        # ============================================
                        barcodes_key = f'item_{form_index}_barcodes'
                        submitted_barcodes = request.POST.getlist(barcodes_key)
                        valid_submitted_barcodes = [b.strip() for b in submitted_barcodes if b.strip()]
                        
                        # قائمة الباركودات الحالية للبند
                        current_item_barcodes_set = set()
                        if instance.pk:
                            current_item_barcodes_set = set(
                                SaleItemBarcode.objects.filter(sale_item_id=instance.pk)
                                .values_list('barcode__barcode_in', flat=True)
                            )
                        
                        # حساب الكميات بناءً على الباركودات برمجياً
                        qty_with_barcode = Decimal(str(len(valid_submitted_barcodes)))
                        
                        if manual_qty >= qty_with_barcode:
                            qty_without_barcode = manual_qty - qty_with_barcode
                        elif qty_with_barcode > Decimal('0.00'):
                            qty_without_barcode = Decimal('0.00')
                            manual_qty = qty_with_barcode
                        else:
                            qty_without_barcode = manual_qty
                        
                        instance.quantity_with_barcode = qty_with_barcode
                        instance.quantity_without_barcode = qty_without_barcode
                        instance.sold_quantity = qty_with_barcode + qty_without_barcode
                        
                        # ============================================
                        # التحقق من صحة الباركودات
                        # ============================================
                        if instance.product:
                            product = instance.product
                            submitted_set = set(valid_submitted_barcodes)
                            barcodes_to_add = submitted_set - current_item_barcodes_set
                            barcodes_to_remove = current_item_barcodes_set - submitted_set
                            
                            if barcodes_to_add:
                                # ✅✅✅ [إصلاح 1] البحث عن الباركودات الموجودة للمنتج
                                db_barcodes = Barcode.objects.filter(
                                    barcode_in__in=barcodes_to_add, 
                                    product=product
                                )
                                found_barcodes = set(db_barcodes.values_list('barcode_in', flat=True))
                                missing_or_invalid = barcodes_to_add - found_barcodes
                                
                                if missing_or_invalid:
                                    errors.append(
                                        f"الباركودات التالية غير موجودة أو لا تنتمي للمنتج: "
                                        f"{', '.join(list(missing_or_invalid)[:5])}"
                                    )
                                else:
                                    # ✅✅✅ [إصلاح 2] التحقق من حالة الباركودات الموجودة
                                    # مسموح: نشط (active) أو مباع في نفس الفاتورة (لنقله بين البنود)
                                    invalid_status_barcodes = db_barcodes.exclude(
                                        status='active'
                                    ).exclude(
                                        sale_items__sale_item__sale=updated_sale
                                    )
                                    
                                    for bc in invalid_status_barcodes:
                                        errors.append(
                                            f"الباركود '{bc.barcode_in}' غير متاح للبيع (حالته: {bc.get_status_display()})"
                                        )
                            
                            if errors:
                                raise ValidationError(
                                    f"خطأ في بند '{product.product_name}': " + " | ".join(errors)
                                )
                        
                        # حفظ البند
                        instance.save()
                        
                        # تحديث المخزون
                        if instance.product:
                            if old_instance and old_instance.product:
                                instance.update_product_stock(old_quantity=old_quantity, old_product=old_instance.product)
                            else:
                                instance.update_product_stock()
                        
                        # ✅✅✅ [إصلاح 3] إزالة الباركودات المزالة باستخدام ميثود delete() للنموذج
                        if barcodes_to_remove:
                            for b_val in barcodes_to_remove:
                                try:
                                    bc_obj = Barcode.objects.get(barcode_in=b_val, product=instance.product)
                                    sib = SaleItemBarcode.objects.filter(sale_item=instance, barcode=bc_obj).first()
                                    if sib:
                                        # delete() للنموذج تتكفل بتحديث حالة الباركود تلقائياً
                                        sib.delete()
                                except Barcode.DoesNotExist:
                                    pass
                        
                        # إضافة الباركودات الجديدة
                        if barcodes_to_add:
                            for b_val in barcodes_to_add:
                                try:
                                    # البحث عن الباركود النشط أو المرتبط بنفس الفاتورة
                                    bc_obj = Barcode.objects.get(
                                        Q(barcode_in=b_val) & Q(product=instance.product),
                                        Q(status='active') | Q(sale_items__sale_item__sale=updated_sale)
                                    )
                                    
                                    # إذا كان مرتبطاً ببند آخر في نفس الفاتورة (نقله)، نحذفه من البند القديم
                                    if bc_obj.status == 'sold':
                                        SaleItemBarcode.objects.filter(
                                            barcode=bc_obj
                                        ).exclude(
                                            sale_item=instance
                                        ).delete()
                                    
                                    SaleItemBarcode.objects.create(
                                        sale_item=instance, 
                                        barcode=bc_obj, 
                                        quantity_used=Decimal('1.00'), 
                                        barcode_status='active'
                                    )
                                    bc_obj.status = 'sold'
                                    bc_obj.save()
                                    
                                except Barcode.DoesNotExist:
                                    logger.warning(f"Barcode {b_val} disappeared during save.")
                                except Barcode.MultipleObjectsReturned:
                                    # في حال وجود سجلات متعددة، نأخذ الأول
                                    bc_obj = Barcode.objects.filter(
                                        barcode_in=b_val, product=instance.product
                                    ).filter(
                                        Q(status='active') | Q(sale_items__sale_item__sale=updated_sale)
                                    ).first()
                                    
                                    if bc_obj:
                                        if bc_obj.status == 'sold':
                                            SaleItemBarcode.objects.filter(
                                                barcode=bc_obj
                                            ).exclude(
                                                sale_item=instance
                                            ).delete()
                                        
                                        SaleItemBarcode.objects.create(
                                            sale_item=instance, 
                                            barcode=bc_obj, 
                                            quantity_used=Decimal('1.00'), 
                                            barcode_status='active'
                                        )
                                        bc_obj.status = 'sold'
                                        bc_obj.save()
                    
                    # حساب الإجماليات
                    updated_sale.calculate_and_save_totals()
                    
                    # معالجة المبلغ المدفوع النهائي
                    paid_amt = updated_sale.paid_amount or Decimal('0.00')
                    if paid_amt > updated_sale.sale_final_total:
                        raise ValidationError("المبلغ المدفوع لا يمكن أن يتجاوز الإجمالي النهائي للفاتورة")
                    
                    updated_sale.balance_due = updated_sale.sale_final_total - paid_amt
                    updated_sale.is_paid = updated_sale.balance_due <= 0
                    updated_sale.save(update_fields=['paid_amount', 'balance_due', 'is_paid'])
                    
                    # معالجة حركات الصندوق
                    if updated_sale.paid_amount > 0 and updated_sale.sale_payment_method and updated_sale.sale_payment_method.is_cash:
                        updated_sale.create_cash_transaction()
                    else:
                        CashTransaction.objects.filter(sale_invoice=updated_sale, transaction_type='sale_receipt').delete()
                    
                    messages.success(request, 'تم تعديل فاتورة البيع بنجاح')
                    return redirect('invoice:sale_detail', slug=updated_sale.slug)
                    
            except ValidationError as e:
                msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
                messages.error(request, msg)
            except Exception as e:
                logger.error(f"خطأ في تعديل فاتورة البيع: {e}", exc_info=True)
                messages.error(request, f'حدث خطأ غير متوقع أثناء تعديل الفاتورة: {str(e)}')
        else:
            # عرض أخطاء التحقق التفصيلية للمستخدم
            error_messages = []
            for field, errs in form.errors.items():
                for err in errs:
                    field_label = form.fields[field].label if field in form.fields else field
                    error_messages.append(f"{field_label}: {err}")
            
            for i, form_errors in enumerate(formset.errors):
                if form_errors:
                    for field, errs in form_errors.items():
                        for err in errs:
                            error_messages.append(f"بند {i+1} - {field}: {err}")
            
            non_form_errs = formset.non_form_errors()
            for err in non_form_errs:
                error_messages.append(str(err))
            
            if error_messages:
                for msg in error_messages[:10]:
                    messages.error(request, msg)
            else:
                messages.error(request, 'يرجى تصحيح الأخطاء في النموذج.')
    
    else:
        form = SaleForm(instance=sale)
        formset = SaleItemEditFormSet(instance=sale, prefix='items')
    
    # جمع البيانات للقالب
    barcodes_data = {}
    for item in sale.saleitem_set.all():
        barcodes_data[str(item.id)] = list(item.item_barcodes.values_list('barcode__barcode_in', flat=True))
    
    financial_data = {
        'tax_percentage': float(sale.sale_tax_percentage or 0),
        'discount': float(sale.sale_discount or 0),
        'addition': float(sale.sale_addition or 0),
        'paid_amount': float(sale.paid_amount or 0),
        'subtotal': float(sale.sale_subtotal or 0),
        'tax_amount': float(sale.sale_tax_amount or 0),
        'final_total': float(sale.sale_final_total or 0),
        'balance_due': float(sale.balance_due or 0),
    }
    
    items_data = {}
    for item in sale.saleitem_set.all():
        items_data[str(item.id)] = {
            'unit_price': float(item.unit_price or 0),
            'sold_quantity': float(item.sold_quantity or 0),
        }
    
    context = {
        'form': form, 
        'formset': formset, 
        'sale': sale, 
        'barcodes_data': barcodes_data, 
        'financial_data': financial_data,
        'items_data': items_data,
        'products': Product.objects.all(), 
        'title': f'تعديل فاتورة بيع: {sale.uniqueId}'
    }
    return render(request, 'invoice/sale/sale_form_edit.html', context)


@login_required
def get_cash_balance(request):
    """API لجلب رصيد الصندوق الحالي"""
    from .models import Cash
    try:
        cash = Cash.objects.first()
        balance = cash.current_balance if cash else Decimal('0.00')
        return JsonResponse({'balance': str(balance)})
    except Exception as e:
        return JsonResponse({'balance': '0.00', 'error': str(e)})


@login_required
def get_payment_method(request, payment_method_id):
    """API لجلب بيانات طريقة الدفع"""
    from .models import PaymentMethod
    try:
        payment_method = PaymentMethod.objects.get(id=payment_method_id)
        return JsonResponse({
            'id': payment_method.id,
            'name': payment_method.name,
            'is_cash': payment_method.is_cash
        })
    except PaymentMethod.DoesNotExist:
        return JsonResponse({'error': 'طريقة الدفع غير موجودة'}, status=404)




@login_required
@permission_required('invoice.view_sale', raise_exception=True)
def sale_list(request):
    """عرض قائمة فواتير البيع"""
    from django.db.models import Q
    user = request.user
    
    if user.is_superuser:
        sales = Sale.objects.all().select_related('sale_customer', 'sale_status').prefetch_related('saleitem_set')
    else:
        sales = Sale.objects.filter(Q(created_by=user) | Q(sale_customer=user)).distinct().select_related('sale_customer', 'sale_status').prefetch_related('saleitem_set')
    
    query = request.GET.get('q', '')
    status_id = request.GET.get('status', '')
    
    if query:
        sales = sales.filter(Q(uniqueId__icontains=query) | Q(sale_invoice_number__icontains=query))
    if status_id:
        sales = sales.filter(sale_status_id=status_id)
        
    context = {'sales': sales, 'title': 'قائمة فواتير البيع'}
    return render(request, 'invoice/sale/sale_list.html', context)


#--seale return---

@login_required
@permission_required('invoice.add_salereturn', raise_exception=True)
def sale_return_create(request, sale_slug):
    original_sale = get_object_or_404(Sale, slug=sale_slug)
    
    if original_sale.created_by and original_sale.created_by != request.user and not request.user.is_superuser:
        raise PermissionDenied(_("ليس لديك صلاحية لإنشاء مرتجع لهذه الفاتورة"))
    
    is_cash_payment = False
    payment_method_name = ""
    if original_sale.sale_payment_method:
        payment_method_name = original_sale.sale_payment_method.name
        if payment_method_name == 'نقداً' or payment_method_name == 'نقدا':
            is_cash_payment = True

    returned_items_data = {}
    for item in original_sale.saleitem_set.all():
        returned_qty = SaleReturnItem.objects.filter(original_sale_item=item, sale_return__isnull=False).aggregate(total=Sum('returned_quantity'))['total'] or Decimal('0.00')
        returned_items_data[item.id] = {'returned': returned_qty, 'sold': item.sold_quantity}
    
    SaleReturnItemFormSet = inlineformset_factory(SaleReturn, SaleReturnItem, form=SaleReturnItemForm, extra=original_sale.saleitem_set.count(), can_delete=True)

    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['original_sale'] = original_sale.id
        
        form = SaleReturnForm(post_data, request.FILES)
        formset = SaleReturnItemFormSet(request.POST, request.FILES, prefix='items')
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    sale_return = form.save(commit=False)
                    sale_return.original_sale = original_sale
                    sale_return.created_by = request.user
                    if not sale_return.return_currency:
                        sale_return.return_currency = getattr(original_sale, 'sale_currency', None)
                    if not sale_return.return_payment_method:
                        try:
                            cash_method = Payment_method.objects.filter(name__in=['نقداً', 'نقدا']).first()
                            if not cash_method:
                                cash_method = Payment_method.objects.create(name='نقداً')
                            sale_return.return_payment_method = cash_method
                        except Exception as e:
                            logger.error(f"خطأ حرج: تعذر تعيين أو إنشاء طريقة الدفع النقدية الافتراضية في مرتجع البيع: {e}")
                    sale_return.save()
                    
                    saved_items_count = 0
                    for item_form in formset:
                        if item_form.cleaned_data.get('DELETE') or not item_form.cleaned_data.get('original_sale_item'):
                            continue
                        item_instance = item_form.save(commit=False)
                        item_instance.sale_return = sale_return
                        original_item = item_form.cleaned_data.get('original_sale_item')
                        
                        data = returned_items_data.get(original_item.id, {'returned': 0, 'sold': 0})
                        available = data['sold'] - data['returned']
                        
                        if item_instance.returned_quantity > available:
                            raise ValueError(f"الكمية المرتجعة لـ {original_item.item_name} تتجاوز المتاح ({available}).")
                        
                        item_instance.product = original_item.product
                        item_instance.item_name = original_item.item_name
                        item_instance.unit_price = original_item.unit_price
                        item_instance.save()
                        saved_items_count += 1
                        
                        item_instance.restore_product_stock()
                        
                        form_index = item_form.prefix.split('-')[1] if '-' in item_form.prefix else None
                        if form_index:
                            barcode_key = f'barcodes_{form_index}'
                            raw_ids = request.POST.getlist(barcode_key)
                            ids_list = []
                            for val in raw_ids:
                                ids_list.extend(val.split(','))
                            for b_id in ids_list:
                                b_id = b_id.strip()
                                if b_id:
                                    try:
                                        barcode_link = SaleItemBarcode.objects.get(barcode_id=int(b_id), sale_item=original_item)
                                        SaleReturnItemBarcode.objects.create(sale_return_item=item_instance, barcode=barcode_link.barcode, quantity_used=Decimal('1.00'), barcode_status='returned')
                                    except Exception as e:
                                        logger.warning(f"Barcode save error: {e}")

                    if saved_items_count == 0:
                        sale_return.delete()
                        messages.warning(request, 'لم يتم تحديد أي كميات للاسترجاع.')
                        return redirect('invoice:sale_detail', slug=original_sale.slug)
                    
                    sale_return.calculate_and_save_totals()
                    
                    if sale_return.paid_amount > sale_return.return_final_total:
                         raise ValueError(f"المبلغ المصروف ({sale_return.paid_amount}) أكبر من إجمالي المرتجع ({sale_return.return_final_total})")
                    
                    sale_return.save()
                    
                    is_cash_method = False
                    if sale_return.return_payment_method:
                        method_name = sale_return.return_payment_method.name.strip()
                        if method_name in ['نقداً', 'نقدا', 'Cash']:
                            is_cash_method = True
                    
                    if sale_return.paid_amount > 0 and is_cash_method:
                        CashTransaction.objects.update_or_create(
                            sale_return=sale_return, 
                            defaults={
                                'transaction_date': timezone.now(), 
                                'transaction_type': 'sale_return', 
                                'amount_out': sale_return.paid_amount, 
                                'amount_in': Decimal('0.00'), 
                                'payment_method': sale_return.return_payment_method, 
                                'notes': f"صرف نقدي للعميل - مرتجع رقم {sale_return.uniqueId}", 
                                'created_by': request.user, 
                                'sale_invoice': sale_return.original_sale
                            }
                        )
                    else:
                        CashTransaction.objects.filter(sale_return=sale_return).delete()
                    
                    messages.success(request, f'تم إنشاء مرتجع البيع {sale_return.uniqueId} بنجاح')
                    return redirect('invoice:sale_detail', slug=original_sale.slug)
                    
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                logger.error(f"Error: {e}", exc_info=True)
                messages.error(request, 'حدث خطأ غير متوقع أثناء إنشاء المرتجع')
            
    else:
        form = SaleReturnForm(initial={'return_date': timezone.now().date(), 'return_currency': getattr(original_sale, 'sale_currency', None), 'original_sale': original_sale.id})
        initial_data = []
        for item in original_sale.saleitem_set.all():
            initial_data.append({'original_sale_item': item, 'product': item.product, 'item_name': item.item_name, 'unit_price': item.unit_price, 'returned_quantity': 0})
        formset = SaleReturnItemFormSet(prefix='items', initial=initial_data)

    # ============ بناء بيانات JSON للقالب ============
    items_json = []
    for sale_item in original_sale.saleitem_set.all().select_related('product'):
        data = returned_items_data.get(sale_item.id, {'returned': 0, 'sold': 0})
        available = data['sold'] - data['returned']
        
        barcodes_list = []
        # الطريقة الأدق: جلب الباركودات المرتبطة بالبند والتي حالتها sold فقط في جدول الباركودات
        # وبذلك نستبعد تلقائياً أي باركود تم إرجاعه (حالته أصبحت active) أو لم يباع
        item_barcodes = sale_item.item_barcodes.filter(
            barcode__status='sold'
        ).select_related('barcode')
        
        for ib in item_barcodes:
            barcodes_list.append({'id': ib.barcode.id, 'barcode_in': ib.barcode.barcode_in})
        
        # تحديد رابط الصورة
        image_url = None
        if sale_item.sale_item_image:
            image_url = sale_item.sale_item_image.url
        elif sale_item.product and hasattr(sale_item.product, 'product_image') and sale_item.product.product_image:
            image_url = sale_item.product.product_image.url
            
        items_json.append({
            'id': sale_item.id, 
            'product_id': sale_item.product.id if sale_item.product else None, 
            'product_name': sale_item.item_name, 
            'unit_price': float(sale_item.unit_price), 
            'sold_quantity': float(data['sold']), 
            'returned_quantity': float(data['returned']), 
            'available_to_return': float(available), 
            'item_image': image_url, 
            'barcodes': barcodes_list
        })

    context = {
        'form': form, 
        'formset': formset, 
        'original_sale': original_sale, 
        'title': f'إنشاء مرتجع لفاتورة بيع {original_sale.uniqueId}', 
        'items_json': items_json,  # تم إزالة json.dumps كما اتفقنا سابقاً
        'is_cash_payment': is_cash_payment, 
        'payment_method_name': payment_method_name
    }
    return render(request, 'invoice/sale/sale_return_form.html', context)


@login_required
@permission_required('invoice.view_salereturn', raise_exception=True)
def sale_return_detail(request, slug):
    """عرض تفاصيل مرتجع المبيعات"""
    try:
        sale_return = SaleReturn.objects.prefetch_related('salereturnitem_set__product', 'salereturnitem_set__return_item_barcodes__barcode').select_related('original_sale__sale_customer', 'created_by').get(slug=slug)
    except SaleReturn.DoesNotExist:
        messages.error(request, 'مرتجع المبيعات غير موجود')
        return redirect('invoice:sale_return_list')
    
    user = request.user
    is_allowed = (user.is_superuser or sale_return.created_by == user or (sale_return.original_sale and sale_return.original_sale.sale_customer == user))
    if not is_allowed:
        raise PermissionDenied(_("ليس لديك صلاحية لعرض هذا المرتجع"))
    
    return render(request, 'invoice/sale_return/sale_return_detail.html', {'sale_return': sale_return, 'original_sale': sale_return.original_sale})


@login_required
@permission_required('invoice.change_salereturn', raise_exception=True)
def sale_return_update(request, slug):
    """تعديل مرتجع المبيعات"""
    try:
        sale_return = SaleReturn.objects.get(slug=slug)
    except SaleReturn.DoesNotExist:
        messages.error(request, 'مرتجع المبيعات غير موجود')
        return redirect('invoice:sale_return_list')
    
    if sale_return.created_by and sale_return.created_by != request.user and not request.user.is_superuser:
        raise PermissionDenied(_("ليس لديك صلاحية لتعديل هذا المرتجع"))
    
    if request.method == 'POST':
        form = SaleReturnForm(request.POST, request.FILES, instance=sale_return)
        formset = SaleReturnItemFormSet(request.POST, request.FILES, prefix='items', instance=sale_return)
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    sale_return = form.save()
                    formset.save()
                    sale_return.calculate_and_save_totals()
                    messages.success(request, f'تم تحديث مرتجع المبيعات {sale_return.uniqueId} بنجاح')
                    return redirect('invoice:sale_return_detail', slug=sale_return.slug)
            except Exception as e:
                logger.error(f"خطأ في تحديث مرتجع المبيعات: {e}", exc_info=True)
                messages.error(request, 'حدث خطأ غير متوقع أثناء تحديث المرتجع')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = SaleReturnForm(instance=sale_return)
        formset = SaleReturnItemFormSet(prefix='items', instance=sale_return)
    
    return render(request, 'invoice/sale_return/sale_return_form.html', {'form': form, 'formset': formset, 'original_sale': sale_return.original_sale, 'sale_return': sale_return, 'title': f'تعديل مرتجع {sale_return.uniqueId}'})


@login_required
@permission_required('invoice.delete_salereturn', raise_exception=True)
def sale_return_delete(request, slug):
    """حذف مرتجع المبيعات - النسخة الآمنة المتوافقة مع F()"""
    try:
        sale_return = SaleReturn.objects.get(slug=slug)
    except SaleReturn.DoesNotExist:
        messages.error(request, 'مرتجع المبيعات غير موجود')
        return redirect('invoice:sale_return_list')
    
    if sale_return.created_by and sale_return.created_by != request.user and not request.user.is_superuser:
        raise PermissionDenied(_("ليس لديك صلاحية لحذف هذا المرتجع"))
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                for item in sale_return.salereturnitem_set.all():
                    for barcode_item in item.return_item_barcodes.all():
                        barcode = barcode_item.barcode
                        barcode.status = 'sold'
                        barcode.save()
                    
                    if item.product:
                        # استخدام F() لمنع مشاكل التزامن عند حذف المرتجع
                        item.product.current_stock_quantity = F('current_stock_quantity') - item.returned_quantity
                        item.product.save(update_fields=['current_stock_quantity'])
                
                sale_return.delete()
                messages.success(request, f'تم حذف مرتجع المبيعات {sale_return.uniqueId} بنجاح')
                
        except Exception as e:
            logger.error(f"خطأ في حذف مرتجع المبيعات: {e}", exc_info=True)
            messages.error(request, 'حدث خطأ أثناء حذف المرتجع')
            
        return redirect('invoice:sale_return_list')
    
    return render(request, 'invoice/sale_return/sale_return_confirm_delete.html', {'sale_return': sale_return})





@login_required
@permission_required('invoice.view_salereturn', raise_exception=True)
def sale_return_list(request):
    """عرض قائمة مرتجعات المبيعات"""
    from django.db.models import Q
    user = request.user
    
    if user.is_superuser:
        sale_returns = SaleReturn.objects.select_related('original_sale', 'created_by').prefetch_related('salereturnitem_set').all()
    else:
        sale_returns = SaleReturn.objects.filter(Q(created_by=user) | Q(original_sale__sale_customer=user)).distinct().select_related('original_sale', 'created_by').prefetch_related('salereturnitem_set')
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date: sale_returns = sale_returns.filter(return_date__gte=start_date)
    if end_date: sale_returns = sale_returns.filter(return_date__lte=end_date)
    
    search_query = request.GET.get('q')
    if search_query:
        sale_returns = sale_returns.filter(Q(uniqueId__icontains=search_query) | Q(original_sale__uniqueId__icontains=search_query) | Q(original_sale__sale_customer__username__icontains=search_query))
    
    paginator = Paginator(sale_returns, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'invoice/sale/sale_return_list.html', {'page_obj': page_obj, 'search_query': search_query, 'start_date': start_date, 'end_date': end_date})




# يجب النقل الى صفحة الفورم
class POSSaleItemFormSet(SaleItemFormSet):
    extra = 0


@login_required
@permission_required('invoice.add_sale', raise_exception=True)
def pos_sale_create(request):
    """إنشاء فاتورة بيع سريعة (نقطة بيع - POS) بنفس منطق الفاتورة الموسعة."""
    if request.method == 'POST':
        form = SaleForm(request.POST, request.FILES)
        formset = POSSaleItemFormSet(request.POST, request.FILES, prefix='items')
        
        # جعل حقول العميل والشحن غير مطلوبة في نقطة البيع
        if 'sale_customer' in form.fields:
            form.fields['sale_customer'].required = False
        if 'sale_shipping_company' in form.fields:
            form.fields['sale_shipping_company'].required = False
        if 'sale_address' in form.fields:
            form.fields['sale_address'].required = False

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    sale = form.save(commit=False)
                    sale.created_by = request.user
                    
                    if not sale.uniqueId:
                        last_invoice = Sale.objects.order_by('-_last_invoice_number').first()
                        last_number = last_invoice._last_invoice_number if last_invoice else 0
                        new_number = last_number + 1
                        sale._last_invoice_number = new_number
                        # استخدام بادئة PO بدلاً من S
                        sale.uniqueId = f"PO{new_number:04d}"
                        
                    if not sale.slug:
                        sale.slug = slugify(f"sale-{sale.uniqueId}")
                    sale.save()

                    instances = formset.save(commit=False)
                    
                    for i, instance in enumerate(instances):
                        instance.sale = sale
                        product_id_from_form = request.POST.get(f'items-{i}-product')
                        product_search_value = request.POST.get(f'items-{i}-product_search', '')
                        
                        if not instance.product and product_id_from_form and product_id_from_form != '':
                            try:
                                instance.product = Product.objects.get(id=product_id_from_form)
                            except Product.DoesNotExist:
                                pass
                        
                        if not instance.product and product_search_value and product_search_value != "مادة غير محددة":
                            try:
                                instance.product = Product.objects.get(product_name=product_search_value)
                            except (Product.DoesNotExist, Product.MultipleObjectsReturned):
                                instance.product = Product.objects.filter(product_name=product_search_value).first()
                        
                        if not instance.item_name and instance.product:
                            instance.item_name = instance.product.product_name
                        elif not instance.item_name:
                            instance.item_name = product_search_value if product_search_value else "مادة غير محددة"
                        
                        image_field_name = f'items-{i}-sale_item_image'
                        
                        if image_field_name in request.FILES:
                            pass 
                        elif instance.product and hasattr(instance.product, 'product_image') and instance.product.product_image:
                            try:
                                image_path = instance.product.product_image.name
                                if default_storage.exists(image_path):
                                    with default_storage.open(image_path, 'rb') as f:
                                        filename = os.path.basename(image_path)
                                        instance.sale_item_image.save(filename, File(f), save=False)
                            except Exception as e:
                                logger.error(f"خطأ أمني/تقني في نسخ الصورة التلقائية للمنتج {instance.product_id}: {e}")
                        
                        qty_sold_with_barcode = Decimal('0.00')
                        qty_sold_without_barcode = Decimal('0.00')
                        
                        if instance.product:
                            product = instance.product
                            barcodes_key = f'item_{i}_barcodes'
                            submitted_barcodes = request.POST.getlist(barcodes_key)
                            valid_submitted_barcodes = [b.strip() for b in submitted_barcodes if b.strip()]
                            
                            qty_sold_with_barcode = Decimal(str(len(valid_submitted_barcodes)))
                            qty_input_value = request.POST.get(f'items-{i}-sold_quantity', '0')
                            try:
                                manual_qty = Decimal(qty_input_value)
                            except:
                                manual_qty = Decimal('0.00')
                            
                            # في نقطة البيع: إذا لم يتم إدخال باركودات، نعتبر الكمية كلها بدون باركود لنخصمها من المخزون العام
                            if qty_sold_with_barcode == 0:
                                qty_sold_without_barcode = manual_qty
                            elif manual_qty > qty_sold_with_barcode:
                                qty_sold_without_barcode = manual_qty - qty_sold_with_barcode
                            
                            instance.quantity_with_barcode = qty_sold_with_barcode
                            instance.quantity_without_barcode = qty_sold_without_barcode
                            instance.sold_quantity = qty_sold_with_barcode + qty_sold_without_barcode
                            
                            total_stock = product.current_stock_quantity
                            
                            # التحقق من المخزون (مبسط لنقطة البيع - نتحقق من الإجمالي فقط لتسهيل البيع السريع)
                            errors = []
                            if instance.sold_quantity > total_stock:
                                errors.append(f"الكمية المطلوبة ({instance.sold_quantity}) تتجاوز المخزون المتاح ({total_stock})")
                            
                            # التحقق من الباركودات المدخلة فقط إن وجدت
                            if qty_sold_with_barcode > 0:
                                available_barcodes_count = Barcode.objects.filter(product=product, status='active').count()
                                if qty_sold_with_barcode > available_barcodes_count:
                                    errors.append(f"عدد الباركودات المطلوبة ({qty_sold_with_barcode}) يتجاوز المتاح ({available_barcodes_count})")
                            
                            for barcode_value in valid_submitted_barcodes:
                                if not Barcode.objects.filter(barcode_in=barcode_value, product=product, status='active').exists():
                                    errors.append(f"الباركود '{barcode_value}' غير متاح")
                            
                            if errors:
                                raise ValidationError(f"خطأ في بند '{product.product_name}': " + " | ".join(errors))
                        
                        instance.save()
                        
                        if instance.product:
                            instance.update_product_stock()
                        
                        for barcode_value in valid_submitted_barcodes:
                            barcode_value = barcode_value.strip()
                            if barcode_value:
                                try:
                                    barcode_obj = Barcode.objects.get(barcode_in=barcode_value, product=instance.product, status='active')
                                    SaleItemBarcode.objects.create(sale_item=instance, barcode=barcode_obj, quantity_used=Decimal('1.00'), barcode_status='active')
                                    barcode_obj.status = 'sold'
                                    barcode_obj.save()
                                except Barcode.DoesNotExist:
                                    pass
                                except Exception as e:
                                    logger.error(f"خطأ في ربط الباركود {barcode_value}: {e}")
                    
                    for instance in formset.deleted_objects:
                        instance.item_barcodes.all().delete()
                        instance.delete()
                    
                    sale.calculate_and_save_totals()

                    paid_amt = Decimal(str(request.POST.get('paid_amount', '0')))
                    if paid_amt > sale.sale_final_total:
                        raise ValidationError("المبلغ المدفوع لا يمكن أن يتجاوز الإجمالي النهائي للفاتورة")

                    sale.paid_amount = paid_amt
                    sale.balance_due = sale.sale_final_total - sale.paid_amount
                    sale.is_paid = sale.balance_due <= 0
                    sale.save(update_fields=['paid_amount', 'balance_due', 'is_paid'])

                    if sale.paid_amount > 0 and sale.sale_payment_method and sale.sale_payment_method.is_cash:
                        sale.create_cash_transaction()
                    
                    # إذا كان الطلب AJAX (عن طريق F2)، نرجع JSON لنعرض الفاتورة الحرارية
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                        # تنسيق التاريخ ليظهر بشكل واضح في الفاتورة الحرارية
                        sale_date_str = sale.sale_date.strftime('%Y-%m-%d %H:%M') if hasattr(sale.sale_date, 'hour') else sale.sale_date.strftime('%Y-%m-%d')
                        
                        return JsonResponse({
                            'success': True, 
                            'invoice_uid': sale.uniqueId,
                            'sale_date': sale_date_str
                        })
                    
                    # في حال تم الحفظ العادي (بدون AJAX)
                    messages.success(request, f'تم إنشاء فاتورة نقطة البيع بنجاح! رقم الفاتورة: {sale.uniqueId}')
                    return redirect('invoice:pos_sale_create')
                    
            except ValidationError as e:
                error_msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg}, status=400)
                messages.error(request, error_msg)
            except Exception as e:
                logger.error(f"خطأ في إنشاء فاتورة نقطة البيع: {e}", exc_info=True)
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'حدث خطأ غير متوقع في الخادم'}, status=500)
                messages.error(request, 'حدث خطأ غير متوقع أثناء إنشاء الفاتورة')
        else:
            error_messages = ["يرجى تصحيح الأخطاء التالية:"]
            if form.errors:
                for field, errors in form.errors.items():
                    error_messages.append(f"خطأ في الحقل ({field}): {', '.join(errors)}")
            if formset.errors:
                for i, error_dict in enumerate(formset.errors):
                    if error_dict:
                        for field, errors in error_dict.items():
                            error_messages.append(f"خطأ في البند {i+1} - الحقل ({field}): {', '.join(errors)}")
            if not form.errors and not formset.errors:
                error_messages.append("خطأ غير معروف في النموذج.")
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': " | ".join(error_messages)}, status=400)
            
            messages.error(request, " | ".join(error_messages))
                
    else:
        cash_method = Payment_method.objects.filter(is_cash=True).first()
        initial_data = {
            'sale_date': timezone.now().date(), 
            'paid_amount': 0, 
            'sale_tax_percentage': 0, 
            'sale_discount': 0, 
            'sale_addition': 0,
            'sale_status': 2,
            'sale_payment_method': cash_method.id if cash_method else None
        }
        form = SaleForm(initial=initial_data)
        
        if 'sale_customer' in form.fields:
            form.fields['sale_customer'].required = False
        if 'sale_shipping_company' in form.fields:
            form.fields['sale_shipping_company'].required = False
        if 'sale_address' in form.fields:
            form.fields['sale_address'].required = False

    formset = POSSaleItemFormSet(prefix='items', queryset=SaleItem.objects.none())
    products = Product.objects.all()
    
    return render(request, 'invoice/sale/sale_pos.html', {
        'form': form, 
        'formset': formset, 
        'products': products, 
        'title': 'نقطة بيع سريعة (POS)'
    })




@login_required
@permission_required('invoice.view_sale', raise_exception=True)
def get_sale_items_for_return(request, sale_id):
    """API لجلب بنود الفاتورة الأصلية مع إمكانية تحديد الكميات القابلة للإرجاع"""
    try:
        sale = Sale.objects.get(id=sale_id)
        
        # جلب جميع بنود الفاتورة مع معلومات الإرجاع السابقة
        items = []
        for item in sale.saleitem_set.all():
            # حساب الكمية التي تم إرجاعها سابقاً لهذا البند
            returned_qty = SaleReturnItem.objects.filter(
                original_sale_item=item,
                sale_return__isnull=False
            ).aggregate(total=Sum('returned_quantity'))['total'] or Decimal('0.00')
            
            # الكمية القابلة للإرجاع = الكمية المباعة - الكمية المرتجعة سابقاً
            available_to_return = max(Decimal('0.00'), item.sold_quantity - returned_qty)
            
            # جلب الباركودات الخاصة بهذا البند
            barcodes = []
            if item.product:
                for ib in item.item_barcodes.filter(barcode_status='active'):
                    barcodes.append({
                        'id': ib.barcode.id,
                        'barcode_in': ib.barcode.barcode_in,
                        'status': ib.barcode.status
                    })
            
            items.append({
                'id': item.id,
                'product_id': item.product.id if item.product else None,
                'product_name': item.item_name,
                'sold_quantity': float(item.sold_quantity),
                'returned_quantity': float(returned_qty),
                'available_to_return': float(available_to_return),
                'unit_price': float(item.unit_price),
                'has_barcode': len(barcodes) > 0,
                'barcodes': barcodes
            })
        
        return JsonResponse({
            'success': True,
            'sale_number': sale.uniqueId,
            'items': items,
            'currency': {
                'id': sale.sale_currency.id if sale.sale_currency else None,
                'name': sale.sale_currency.name_ar if sale.sale_currency else 'ليرة سورية'
            }
        })
        
    except Sale.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الفاتورة غير موجودة'}, status=404)
    except Exception as e:
        logger.error(f"خطأ في جلب بنود الفاتورة للإرجاع: {e}", exc_info=True)
        # 🔒 تحسين أمني للـ API
        return JsonResponse({'success': False, 'error': 'حدث خطأ أثناء جلب البيانات'}, status=500)


@login_required
@permission_required('invoice.add_salereturn', raise_exception=True)
def check_barcode_for_return(request, product_id):
    """API للتحقق من صحة الباركود للإرجاع"""
    try:
        product = Product.objects.get(id=product_id)
        barcode_value = request.GET.get('barcode')
        sale_item_id = request.GET.get('sale_item_id')
        
        if not barcode_value:
            return JsonResponse({'success': False, 'error': 'لم يتم إرسال قيمة الباركود'})
        
        # البحث عن الباركود
        try:
            barcode_obj = Barcode.objects.get(barcode_in=barcode_value, product=product)
        except Barcode.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'error': 'الباركود غير موجود لهذا المنتج'
            })
        
        # التحقق من أن هذا الباركود كان مباعاً في هذه الفاتورة
        if barcode_obj.status != 'sold':
            return JsonResponse({
                'success': False,
                'error': f'هذا الباركود غير مباع (حالته: {barcode_obj.get_status_display()})'
            })
        
        # التحقق من أن الباركود تابع لهذا البند (إذا تم تحديد البند)
        if sale_item_id:
            is_in_sale_item = SaleItemBarcode.objects.filter(
                sale_item_id=sale_item_id,
                barcode=barcode_obj,
                barcode_status='active'
            ).exists()
            
            if not is_in_sale_item:
                return JsonResponse({
                    'success': False,
                    'error': 'هذا الباركود ليس من ضمن بنود هذه الفاتورة'
                })
        
        # التحقق من أن الباركود لم يُرجع سابقاً
        already_returned = SaleReturnItemBarcode.objects.filter(
            barcode=barcode_obj,
            barcode_status='returned'
        ).exists()
        
        if already_returned:
            return JsonResponse({
                'success': False,
                'error': 'تم إرجاع هذا الباركود سابقاً'
            })
        
        return JsonResponse({
            'success': True,
            'message': 'باركود صالح للإرجاع',
            'barcode_id': barcode_obj.id,
            'barcode_value': barcode_obj.barcode_in
        })
        
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'المنتج غير موجود'}, status=404)
    except Exception as e:
        logger.error(f"خطأ في التحقق من الباركود للإرجاع: {e}", exc_info=True)
        # 🔒 تحسين أمني للـ API
        return JsonResponse({'success': False, 'error': 'حدث خطأ أثناء التحقق من الباركود'}, status=500)






#================================================
#               المواد  و الباركود            #
# ===============================================



@login_required
@permission_required('invoice.add_product', raise_exception=True)
def product_create(request):
    """إنشاء مادة جديدة - معلومات فقط"""
    print("✅ تم الدخول إلى product_create")
    
    if request.method == 'POST':
        print("✅ الطريقة POST")
        product_name = request.POST.get('product_name')
        main_barcode = request.POST.get('main_barcode', '')
        product_description = request.POST.get('product_description', '')
        product_image = request.FILES.get('product_image')
        
        print(f"✅ اسم المادة: {product_name}")
        print(f"✅ الباركود الأساسي: {main_barcode}")
        
        if not product_name:
            messages.error(request, _('اسم المادة مطلوب'))
            return render(request, 'invoice/products/product_form.html', {
                'title': _('إنشاء مادة جديدة')
            })
        
        try:
            with transaction.atomic():
                product = Product(
                    product_name=product_name,
                    main_barcode=main_barcode if main_barcode else None,
                    product_description=product_description,
                    purch_price=Decimal('0.00'),
                    sale_price=Decimal('0.00'),
                    current_stock_quantity=Decimal('0.00'),
                    average_purchase_cost=Decimal('0.00'),
                    retail_profit_margin=Decimal('25.00'),
                    semi_wholesale_profit_margin=Decimal('20.00'),
                    wholesale_profit_margin=Decimal('15.00'),
                    price_adjustment=Decimal('0.00'),
                    retail_price=Decimal('0.00'),
                    semi_wholesale_price=Decimal('0.00'),
                    wholesale_price=Decimal('0.00')
                )
                
                if product_image:
                    product.product_image = product_image
                
                product.save()
                print(f"✅ تم حفظ المادة: {product.product_name} - ID: {product.id} - Slug: {product.slug}")
                
                messages.success(request, _('تم إنشاء المادة بنجاح'))
                return redirect('invoice:product_list')
                
        except Exception as e:
            print(f"❌ خطأ في الحفظ: {str(e)}")
            messages.error(request, f'حدث خطأ أثناء إنشاء المادة: {str(e)}')
    
    return render(request, 'invoice/products/product_form.html', {
        'title': _('إنشاء مادة جديدة')
    })


@login_required
@permission_required('invoice.view_product', raise_exception=True)
def product_list(request):
    """عرض قائمة المنتجات مع فلترة الباركودات النشطة فقط"""
    products = Product.objects.all().prefetch_related(
        Prefetch('barcodes', queryset=Barcode.objects.filter(status='active'), to_attr='active_barcodes')
    ).order_by('-date_created')
    
    return render(request, 'invoice/products/product_list.html', {
        'products': products,
        'title': _('إدارة المنتجات')
    })


@login_required
@permission_required('invoice.view_product', raise_exception=True)
def product_detail(request, slug):
    """عرض تفاصيل المنتج"""
    product = get_object_or_404(Product, slug=slug)
    barcodes = product.barcodes.all()
    
    return render(request, 'invoice/products/product_detail.html', {
        'product': product,
        'barcodes': barcodes,
        'title': _('تفاصيل المنتج')
    })


@login_required
@permission_required('invoice.delete_product', raise_exception=True)
def product_delete(request, slug):
    """حذف منتج"""
    product = get_object_or_404(Product, slug=slug)
    
    if request.method == 'POST':
        product_name = product.product_name
        product.delete()
        messages.success(request, f'تم حذف المنتج "{product_name}" بنجاح')
        return redirect('invoice:product_list')
    
    return render(request, 'invoice/products/product_confirm_delete.html', {
        'product': product,
        'title': _('تأكيد حذف المنتج')
    })


@login_required
@permission_required('invoice.change_product', raise_exception=True)
def product_edit(request, slug):
    """تعديل مادة موجودة - معلومات فقط"""
    product = get_object_or_404(Product, slug=slug)
    print(f"✅ تعديل المادة: {product.product_name} - Slug: {slug}")
    
    if request.method == 'POST':
        product_name = request.POST.get('product_name')
        main_barcode = request.POST.get('main_barcode', '')
        product_description = request.POST.get('product_description', '')
        product_image = request.FILES.get('product_image')
        remove_image = request.POST.get('remove_image')
        
        if not product_name:
            messages.error(request, _('اسم المادة مطلوب'))
            return render(request, 'invoice/products/product_edit.html', {
                'product': product,
                'title': _('تعديل المادة')
            })
        
        try:
            with transaction.atomic():
                product.product_name = product_name
                product.main_barcode = main_barcode if main_barcode else None
                product.product_description = product_description
                
                if remove_image == 'true':
                    if product.product_image:
                        product.product_image.delete()
                    product.product_image = None
                elif product_image:
                    if product.product_image:
                        product.product_image.delete()
                    product.product_image = product_image
                
                product.save()
                print(f"✅ تم تحديث المادة: {product.product_name}")
                
                messages.success(request, _('تم تحديث المادة بنجاح'))
                return redirect('invoice:product_detail', slug=product.slug)
                
        except Exception as e:
            print(f"❌ خطأ في تحديث المادة: {str(e)}")
            messages.error(request, f'حدث خطأ أثناء تحديث المادة: {str(e)}')
    
    return render(request, 'invoice/products/product_edit.html', {
        'product': product,
        'title': _('تعديل المادة')
    })





#================================================
#           نظام التسعير          #
# ===============================================



@login_required
@permission_required('invoice.change_product', raise_exception=True)
def product_bulk_update(request):
    """تحديث جمعي للأسعار مع نظام مستويات ديناميكي"""
    
    if request.method == 'POST':
        try:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'message': 'خطأ في تنسيق البيانات'}, status=400)

            sensitive_actions = ['bulk_updates', 'save_tiers_settings', 'reset_data']
            if any(action in data for action in sensitive_actions):
                provided_password = data.get('password', '')
                if not verify_pricing_password(provided_password):
                    logger.warning(f"محاولة كلمة مرور خاطئة بواسطة: {request.user.username}")
                    return JsonResponse({'success': False, 'message': 'كلمة المرور غير صحيحة!'}, status=403)

            def to_decimal(val):
                if val is None or val == '':
                    return None
                val_str = str(val).strip()
                if not val_str:
                    return None
                try:
                    return Decimal(val_str)
                except (InvalidOperation, ValueError):
                    return 'INVALID'

            def validate_range(val, min_val, max_val, field_name):
                if val is None:
                    return None, f"{field_name} مطلوب"
                if val == 'INVALID':
                    return None, f"{field_name} يجب أن يكون رقماً صحيحاً"
                if val < min_val or val > max_val:
                    return None, f"{field_name} يجب أن يكون بين {min_val} و {max_val}"
                return val, None

            def validate_non_negative(val, field_name):
                if val is None:
                    return None, None
                if val == 'INVALID':
                    return None, f"{field_name} يجب أن يكون رقماً صحيحاً"
                if val < Decimal('0.00'):
                    return None, f"{field_name} لا يمكن أن يكون سالباً"
                return val, None

            # ==========================================
            # إضافة مستوى تسعير جديد
            # ==========================================
            if 'add_tier' in data:
                name = data.get('tier_name', '').strip()
                if not name:
                    return JsonResponse({'success': False, 'message': 'اسم المستوى مطلوب'}, status=400)
                if len(name) > 100:
                    return JsonResponse({'success': False, 'message': 'اسم المستوى طويل جداً'}, status=400)
                if PricingTier.objects.filter(name=name).exists():
                    return JsonResponse({'success': False, 'message': 'اسم المستوى موجود مسبقاً'}, status=400)
                
                order = PricingTier.objects.count()
                tier = PricingTier.objects.create(name=name, display_order=order)
                return JsonResponse({
                    'success': True,
                    'message': 'تم إضافة المستوى بنجاح',
                    'tier_id': tier.id,
                    'tier_name': tier.name
                })

            # ==========================================
            # حذف مستوى تسعير
            # ==========================================
            if 'delete_tier' in data:
                tier_id = data.get('tier_id')
                if not tier_id:
                    return JsonResponse({'success': False, 'message': 'معرف المستوى مطلوب'}, status=400)

                try:
                    tier = PricingTier.objects.get(id=tier_id)
                    tier.delete()
                except PricingTier.DoesNotExist:
                    return JsonResponse({'success': False, 'message': 'المستوى غير موجود'}, status=404)

                return JsonResponse({'success': True, 'message': 'تم حذف المستوى'})

            # ==========================================
            # جلب صفحة منتجات (AJAX Pagination)
            # ==========================================
            if 'get_page' in data:
                page_number = data.get('page', 1)
                products_qs = Product.objects.all().order_by('id').prefetch_related('tier_prices__tier')
                paginator = Paginator(products_qs, 30)
                
                try:
                    page_obj = paginator.get_page(page_number)
                except Exception:
                    page_obj = paginator.get_page(1)

                products_list = [
                    {
                        'id': p.id,
                        'name': p.product_name,
                        'stock': p.current_stock_quantity,
                        'cost': str(p.average_purchase_cost or 0),
                        'wholesale': str(p.wholesale_price or 0),
                        'tier_prices': {str(tp.tier_id): str(tp.price) for tp in p.tier_prices.all()}
                    } for p in page_obj
                ]

                return JsonResponse({
                    'success': True,
                    'products': products_list,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous(),
                    'current_page': page_obj.number,
                    'total_pages': paginator.num_pages,
                    'total_products': paginator.count
                })

            # ==========================================
            # التحديث الجماعي للأسعار
            # ==========================================
            if 'bulk_updates' in data:
                tiers_data = data.get('tiers', [])
                bulk_updates = data.get('bulk_updates', {})

                margin_raw = to_decimal(data.get('profit_margin'))
                margin, margin_err = validate_range(margin_raw, Decimal('0.00'), Decimal('999.00'), 'نسبة الربح')
                if margin_err:
                    return JsonResponse({'success': False, 'message': margin_err, 'field': 'profit_margin'}, status=400)

                conversion_raw = to_decimal(data.get('conversion_factor'))
                conversion, conversion_err = validate_range(conversion_raw, Decimal('0.01'), Decimal('999999.99'), 'سعر الصرف')
                if conversion_err:
                    return JsonResponse({'success': False, 'message': conversion_err, 'field': 'conversion_factor'}, status=400)

                tier_ids_in_request = [int(t.get('id')) for t in tiers_data if t.get('id')]
                valid_tier_ids = set(PricingTier.objects.filter(id__in=tier_ids_in_request).values_list('id', flat=True))
                missing_tiers = set(tier_ids_in_request) - valid_tier_ids
                if missing_tiers:
                    return JsonResponse({'success': False, 'message': f'مستويات غير موجودة: {missing_tiers}', 'field': 'tier_id'}, status=400)

                tiers_dict = {}
                for t in tiers_data:
                    tier_id = t.get('id')
                    tier_name = t.get('name', '').strip()
                    if not tier_name:
                        return JsonResponse({'success': False, 'message': 'اسم مستوى فارغ', 'field': 'tier_name_' + str(tier_id)}, status=400)
                    
                    percent_raw = to_decimal(t.get('percent'))
                    percent, percent_err = validate_range(percent_raw, Decimal('0.00'), Decimal('100.00'), 'نسبة الخصم لـ "' + tier_name + '"')
                    if percent_err:
                        return JsonResponse({'success': False, 'message': percent_err, 'field': 'tier_percent_' + str(tier_id)}, status=400)
                    
                    tiers_dict[str(tier_id)] = percent

                product_ids = [int(pid) for pid in bulk_updates.keys()]
                valid_product_ids = set(Product.objects.filter(id__in=product_ids).values_list('id', flat=True))
                missing_products = set(product_ids) - valid_product_ids
                if missing_products:
                    return JsonResponse({'success': False, 'message': f'منتجات غير موجودة: {missing_products}'}, status=400)

                validated_prices = {}
                for p_id_str, prices in bulk_updates.items():
                    wholesale_raw = to_decimal(prices.get('wholesale_price'))
                    if wholesale_raw is None:
                        validated_prices[p_id_str] = {'wholesale_price': None}
                    else:
                        wholesale, wholesale_err = validate_non_negative(wholesale_raw, 'سعر الجملة')
                        if wholesale_err:
                            return JsonResponse({'success': False, 'message': wholesale_err + ' للمنتج ' + p_id_str, 'field': 'wholesale_' + p_id_str}, status=400)
                        validated_prices[p_id_str] = {'wholesale_price': wholesale}

                    for tier_id_str, tier_percent in tiers_dict.items():
                        tier_field_name = 'tier_' + tier_id_str
                        tier_price_raw = to_decimal(prices.get(tier_field_name))
                        if tier_price_raw is None:
                            validated_prices[p_id_str][tier_field_name] = None
                        else:
                            tier_price, tier_price_err = validate_non_negative(tier_price_raw, 'سعر المستوى')
                            if tier_price_err:
                                return JsonResponse({'success': False, 'message': tier_price_err + ' للمنتج ' + p_id_str, 'field': tier_field_name + '_' + p_id_str}, status=400)
                            validated_prices[p_id_str][tier_field_name] = tier_price

                with transaction.atomic():
                    settings_obj = PricingSetting.get_settings()
                    settings_obj.profit_margin = margin
                    settings_obj.conversion_factor = conversion
                    settings_obj.save()

                    for t in tiers_data:
                        PricingTier.objects.filter(id=t['id']).update(
                            name=t['name'].strip(),
                            discount_percent=tiers_dict[str(t['id'])]
                        )

                    products_qs = Product.objects.filter(id__in=product_ids)
                    existing_tier_prices = ProductPriceTier.objects.filter(product_id__in=product_ids)
                    existing_tier_prices_dict = {(etp.product_id, etp.tier_id): etp for etp in existing_tier_prices}

                    products_to_update = []
                    tier_prices_to_update = []
                    tier_prices_to_create = []

                    for product in products_qs:
                        base_cost = product.average_purchase_cost or Decimal('0.00')
                        calculated_wholesale = base_cost * (1 + margin / Decimal('100.00'))
                        
                        p_id_str = str(product.id)
                        frontend_wholesale = validated_prices[p_id_str]['wholesale_price']
                        final_wholesale = calculated_wholesale if frontend_wholesale is None else frontend_wholesale
                        
                        product.wholesale_price = final_wholesale
                        products_to_update.append(product)

                        for tier_id_str, tier_percent in tiers_dict.items():
                            tier_field_name = 'tier_' + tier_id_str
                            calculated_tier_price = Decimal('0.00')
                            if tier_percent > 0:
                                calculated_tier_price = final_wholesale * (1 - tier_percent / Decimal('100.00'))

                            frontend_tier_price = validated_prices[p_id_str].get(tier_field_name)
                            final_tier_price = calculated_tier_price if frontend_tier_price is None else frontend_tier_price

                            key = (product.id, int(tier_id_str))
                            if key in existing_tier_prices_dict:
                                existing_obj = existing_tier_prices_dict[key]
                                if existing_obj.price != final_tier_price:
                                    existing_obj.price = final_tier_price
                                    tier_prices_to_update.append(existing_obj)
                            else:
                                tier_prices_to_create.append(ProductPriceTier(
                                    product_id=product.id,
                                    tier_id=int(tier_id_str),
                                    price=final_tier_price
                                ))

                    if products_to_update:
                        Product.objects.bulk_update(products_to_update, ['wholesale_price'])
                    if tier_prices_to_update:
                        ProductPriceTier.objects.bulk_update(tier_prices_to_update, ['price'])
                    if tier_prices_to_create:
                        ProductPriceTier.objects.bulk_create(tier_prices_to_create)

                return JsonResponse({'success': True, 'message': 'تم التحديث الجماعي بنجاح'})

            # ==========================================
            # إعادة ضبط كاملة للنظام
            # ==========================================
            if 'reset_data' in data:
                with transaction.atomic():
                    affected_products = Product.objects.count()
                    deleted_tier_prices = ProductPriceTier.objects.count()
                    affected_tiers = PricingTier.objects.count()
                    
                    settings_obj = PricingSetting.get_settings()
                    settings_obj.profit_margin = Decimal('0.00')
                    settings_obj.conversion_factor = Decimal('0.00')
                    settings_obj.save()

                    Product.objects.all().update(wholesale_price=F('average_purchase_cost'))
                    ProductPriceTier.objects.all().delete()
                    PricingTier.objects.all().delete()

                return JsonResponse({
                    'success': True,
                    'message': f'تم تصفير {affected_products} منتج وحذف {deleted_tier_prices} سعر وحذف {affected_tiers} مستوى'
                })

            return JsonResponse({'success': False, 'message': 'طلب غير معروف'}, status=400)

        except Exception as e:
            logger.error(f"خطأ بواسطة {request.user.username}: {e}", exc_info=True)
            return JsonResponse({'success': False, 'message': 'خطأ في السيرفر'}, status=500)

    # ==========================================
    # عرض الصفحة الأولي (GET)
    # ==========================================
    products_qs = Product.objects.all().order_by('id').prefetch_related('tier_prices__tier')
    paginator = Paginator(products_qs, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    
    settings = PricingSetting.get_settings()
    tiers_qs = PricingTier.objects.all().order_by('display_order')
    
    tiers_list = [{'id': t.id, 'name': t.name, 'percent': float(t.discount_percent or 0)} for t in tiers_qs]
    products_list = [
        {
            'id': p.id,
            'name': p.product_name,
            'stock': p.current_stock_quantity,
            'cost': str(p.average_purchase_cost or 0),
            'wholesale': str(p.wholesale_price or 0),
            'tier_prices': {str(tp.tier_id): str(tp.price) for tp in p.tier_prices.all()}
        } for p in page_obj
    ]

    return render(request, 'invoice/products/product_bulk_update.html', {
        'products': products_list,
        'tiers': tiers_list,
        'settings': settings,
        'title': 'تحديث جماعي للمواد',
        'pagination_info': {
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_products': paginator.count,
        },
    })


    

#================================================
#                  الباركود                    #
# ===============================================


@login_required
@permission_required('invoice.add_barcode', raise_exception=True)
def barcode_create(request, product_slug):
    """إضافة باركود لمنتج"""
    product = get_object_or_404(Product, slug=product_slug)
    
    if request.method == 'POST':
        form = BarcodeForm(request.POST)
        if form.is_valid():
            try:
                barcode = form.save(commit=False)
                barcode.product = product
                
                if barcode.is_primary:
                    Barcode.objects.filter(product=product, is_primary=True).update(is_primary=False)
                
                barcode.save()
                messages.success(request, _('تم إضافة الباركود بنجاح'))
                return redirect('invoice:product_detail', slug=product.slug)
                
            except IntegrityError:
                messages.error(request, _('هذا الباركود موجود مسبقاً'))
            except Exception as e:
                messages.error(request, _('حدث خطأ أثناء إضافة الباركود، يرجى المحاولة مرة أخرى.'))
        else:
            messages.error(request, _('بيانات غير صحيحة. يرجى التصحيح والمحاولة مرة أخرى.'))
    else:
        form = BarcodeForm(initial={'product': product, 'status': 'active'})
    
    return render(request, 'invoice/barcode_form.html', {
        'form': form,
        'product': product,
        'title': _('إضافة باركود للمنتج')
    })


@login_required
@permission_required('invoice.view_barcode', raise_exception=True)
def barcode_manage(request, product_slug):
    """إدارة باركودات منتج"""
    product = get_object_or_404(Product, slug=product_slug)
    barcodes = product.barcodes.all()
    
    return render(request, 'invoice/barcode_manage.html', {
        'product': product,
        'barcodes': barcodes,
        'title': _('إدارة باركودات المنتج')
    })


@login_required
@permission_required('invoice.delete_barcode', raise_exception=True)
def barcode_delete(request, barcode_id):
    """حذف باركود"""
    barcode = get_object_or_404(Barcode, id=barcode_id)
    product_slug = barcode.product.slug
    
    if request.method == 'POST':
        try:
            barcode.delete()
            messages.success(request, _('تم حذف الباركود بنجاح'))
        except Exception as e:
            messages.error(request, _('حدث خطأ أثناء حذف الباركود، يرجى المحاولة مرة أخرى.'))
    
    return redirect('invoice:product_detail', slug=product_slug)



@login_required
@permission_required('invoice.view_barcode', raise_exception=True)
def api_barcode_search(request, barcode):
    """API للبحث بالباركود"""
    try:
        barcode_obj = Barcode.objects.get(barcode_in=barcode)
        product = barcode_obj.product
        return JsonResponse({
            'product_id': product.id,
            'product_name': product.product_name,
            'purch_price': str(product.purch_price),
            'sale_price': str(product.sale_price),
            'current_stock': str(product.current_stock_quantity),
        })
    except Barcode.DoesNotExist:
        return JsonResponse({'error': 'الباركود غير موجود'}, status=404)






#================================================
#                  ادارة الصندوق                    #
# ===============================================

@login_required
@permission_required('invoice.view_cashtransaction', raise_exception=True)
def cash_dashboard(request):
    """عرض لوحة تحكم الصندوق"""
    total_in = CashTransaction.objects.aggregate(total=Sum('amount_in'))['total'] or Decimal('0.00')
    total_out = CashTransaction.objects.aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')
    current_balance = total_in - total_out

    recent_transactions = CashTransaction.objects.all().order_by('-transaction_date')[:10]

    today = timezone.now().date()
    today_in = CashTransaction.objects.filter(
        transaction_date__date=today
    ).aggregate(total=Sum('amount_in'))['total'] or Decimal('0.00')
    today_out = CashTransaction.objects.filter(
        transaction_date__date=today
    ).aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')

    context = {
        'title': 'لوحة تحكم الصندوق',
        'total_in': total_in,
        'total_out': total_out,
        'current_balance': current_balance,
        'today_in': today_in,
        'today_out': today_out,
        'recent_transactions': recent_transactions,
    }
    return render(request, 'invoice/cashbox/cash_dashboard.html', context)



@login_required
@permission_required('invoice.view_cashtransaction', raise_exception=True)
def cash_transaction_list(request):
    """عرض قائمة حركات الصندوق"""
    
    transaction_type = request.GET.get('type', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    search_query = request.GET.get('q', '')

    # ★ تحسين الأداء: إضافة select_related لجلب البيانات المرتبطة في استعلام واحد ★
    transactions_qs = CashTransaction.objects.select_related(
        'sale_invoice__sale_customer',
        'sale_return__original_sale__sale_customer',
        'purchase_invoice__purch_supplier',
        'purchase_return__original_purchase__purch_supplier',
        'created_by',
        'payment_method'
    ).all().order_by('-transaction_date')
    
    if transaction_type:
        transactions_qs = transactions_qs.filter(transaction_type=transaction_type)
    
    if start_date:
        parsed_start = parse_date(start_date)
        if parsed_start:
            start_dt = timezone.make_aware(datetime.datetime.combine(parsed_start, datetime.time.min))
            transactions_qs = transactions_qs.filter(transaction_date__gte=start_dt)
            
    if end_date:
        parsed_end = parse_date(end_date)
        if parsed_end:
            end_dt = timezone.make_aware(datetime.datetime.combine(parsed_end, datetime.time.max))
            transactions_qs = transactions_qs.filter(transaction_date__lte=end_dt)

    if search_query:
        transactions_qs = transactions_qs.filter(notes__icontains=search_query)

    # تصدير CSV
    if 'export' in request.GET and request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="cash_transactions.csv"'
        writer = csv.writer(response)
        # ★ إضافة عمود "الطرف الآخر" في التصدير ★
        writer.writerow(['التاريخ', 'النوع', 'المبلغ الداخل', 'المبلغ الخارج', 'البيان', 'أجرى العملية', 'الطرف الآخر'])
        for trans in transactions_qs:
            writer.writerow([
                trans.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
                trans.get_transaction_type_display(),
                trans.amount_in,
                trans.amount_out,
                trans.notes or '',
                trans.created_by.username if trans.created_by else '-',
                trans.get_partner_name(),  # ★ استخدام الدالة الجديدة ★
            ])
        return response

    paginator = Paginator(transactions_qs, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    total_in = transactions_qs.aggregate(total=Sum('amount_in'))['total'] or Decimal('0.00')
    total_out = transactions_qs.aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')
    net_total = total_in - total_out

    page_total_in = sum(item.amount_in for item in page_obj)
    page_total_out = sum(item.amount_out for item in page_obj)
    page_total_net = page_total_in - page_total_out

    overall_balance = CashTransaction.get_cash_balance()
    is_balance_negative = overall_balance < 0

    today = timezone.now().date()
    start_of_today = timezone.make_aware(datetime.datetime.combine(today, datetime.time.min))
    end_of_today = timezone.make_aware(datetime.datetime.combine(today, datetime.time.max))
    today_transactions = CashTransaction.objects.filter(
        transaction_date__gte=start_of_today,
        transaction_date__lte=end_of_today
    )
    today_in = today_transactions.aggregate(total=Sum('amount_in'))['total'] or Decimal('0.00')
    today_out = today_transactions.aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')
    today_net = today_in - today_out

    # ★★ إضافة اسم الطرف الآخر لكل حركة في الصفحة ★★
    for trans in page_obj:
        trans.partner_name = trans.get_partner_name()

    context = {
        'title': 'حركات الصندوق',
        'CashTransaction': CashTransaction,
        'page_obj': page_obj,
        'total_in': total_in,
        'total_out': total_out,
        'net_total': net_total,
        'page_total_in': page_total_in,
        'page_total_out': page_total_out,
        'page_total_net': page_total_net,
        'overall_balance': overall_balance,
        'is_balance_negative': is_balance_negative,
        'today_in': today_in,
        'today_out': today_out,
        'today_net': today_net,
        'current_filter': {
            'type': transaction_type,
            'start_date': start_date,
            'end_date': end_date,
            'q': search_query,
        }
    }
    return render(request, 'invoice/cashbox/cash_transaction_list.html', context)


@login_required
@permission_required('invoice.add_cashtransaction', raise_exception=True)
def cash_transaction_create(request):
    """إنشاء حركة صندوق جديدة"""
    total_in = CashTransaction.objects.aggregate(total=Sum('amount_in'))['total'] or Decimal('0.00')
    total_out = CashTransaction.objects.aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')
    current_balance = total_in - total_out

    if request.method == 'POST':
        form = CashTransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.created_by = request.user
            transaction.transaction_date = timezone.now()
            if transaction.transaction_type in ['withdrawal', 'expense']:
                try:
                    cash_payment_method = Payment_method.objects.get(name='نقداً')
                    transaction.payment_method = cash_payment_method
                except Payment_method.DoesNotExist:
                    pass
            transaction.save()
            return redirect('invoice:cash_transaction_list')
    else:
        form = CashTransactionForm()
    
    context = {
        'title': 'إضافة حركة صندوق جديدة',
        'form': form,
        'current_balance': current_balance,
    }
    return render(request, 'invoice/cashbox/cash_transaction_create.html', context)


@login_required
@permission_required('invoice.view_cashtransaction', raise_exception=True)
def cash_transaction_detail(request, pk):
    """عرض تفاصيل حركة صندوق"""
    transaction = get_object_or_404(CashTransaction, pk=pk)
    
    context = {
        'title': 'تفاصيل حركة الصندوق',
        'transaction': transaction,
    }
    return render(request, 'invoice/cashbox/cash_transaction_detail.html', context)




@login_required
@permission_required('invoice.view_cashtransaction', raise_exception=True)
@require_GET
def get_cash_balance(request):
    """جلب رصيد الصندوق الحالي"""
    try:
        balance = CashTransaction.get_cash_balance()
        return JsonResponse({'balance': str(balance)})
    except Exception as e:
        return JsonResponse({'error': 'حدث خطأ أثناء جلب رصيد الصندوق'}, status=500)



# =================================================
#  APIs خاصة بطرق الدفع
# =================================================

@login_required
@permission_required('invoice.change_payment_method', raise_exception=True)
@csrf_exempt
@require_POST
def update_payment_method_cash(request, pk):
    """تحديث حالة is_cash في طريقة الدفع"""
    try:
        payment_method = get_object_or_404(Payment_method, pk=pk)
        data = json.loads(request.body)
        is_cash = data.get('is_cash', False)
        
        payment_method.is_cash = is_cash
        payment_method.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        # 🔒 تحسين أمني
        return JsonResponse({'success': False, 'error': 'حدث خطأ أثناء التحديث'})


@login_required
@permission_required('invoice.view_payment_method', raise_exception=True)
@require_GET
def get_payment_method(request, pk):
    """جلب بيانات طريقة الدفع (يُستدعى من داخل نماذج الفواتير)"""
    try:
        payment_method = get_object_or_404(Payment_method, pk=pk)
        return JsonResponse({
            'id': payment_method.id,
            'name': payment_method.name,
            'is_cash': payment_method.is_cash
        })
    except Exception as e:
        return JsonResponse({'error': 'حدث خطأ أثناء جلب البيانات'}, status=404)


# =================================================
#  أدوات مساعدة عامة (تُستدعى من الواجهة الأمامية)
# =================================================

@require_GET
@login_required
def convert_amount_to_words_api(request):
    """API لتحويل المبلغ إلى كلمات"""
    from num2words import num2words
    amount = request.GET.get('amount', '0')
    currency_id = request.GET.get('currency_id', '')
    
    try:
        amount_decimal = Decimal(amount)
        if amount_decimal <= Decimal('0'):
            return JsonResponse({
                'success': False,
                'error': 'المبلغ يجب أن يكون أكبر من صفر'
            })
        
        currency_data = {
            'code': 'SYP',
            'symbol': 'ل.س',
            'name_ar': 'ليرة سورية',
            'singular': 'ليرة سورية',
            'dual': 'ليرتان سوريتان',
            'plural': 'ليرات سورية',
            'fraction': 'قرش',
            'fraction_dual': 'قرشان',
            'fraction_plural': 'قروش',
            'decimals': 2
        }
        
        if currency_id:
            try:
                currency = Currency.objects.get(id=currency_id)
                currency_data = {
                    'code': currency.code,
                    'symbol': currency.symbol,
                    'name_ar': currency.name_ar,
                    'singular': currency.singular_ar,
                    'dual': currency.dual_ar,
                    'plural': currency.plural_ar,
                    'fraction': currency.fraction_name_ar,
                    'fraction_dual': currency.fraction_dual_ar,
                    'fraction_plural': currency.fraction_plural_ar,
                    'decimals': currency.decimals
                }
            except Currency.DoesNotExist:
                logger.warning(f"العملة غير موجودة: {currency_id}")
        
        amount_float = float(amount_decimal)
        integer_part = int(amount_float)
        fractional_part = int(round((amount_float - integer_part) * (10 ** currency_data['decimals'])))
        
        integer_words = num2words(integer_part, lang='ar')
        fraction_words = num2words(fractional_part, lang='ar') if fractional_part > 0 else ''
        
        def clean_arabic_text(text):
            corrections = {
                'مئة': 'مائة',
                'مئتان': 'مئتان',
                'مئتين': 'مئتين',
                'واحد': 'واحد',
                'اثنان': 'اثنان',
                'اثنين': 'اثنين',
                'ثلاثة': 'ثلاثة',
                'أربعة': 'أربعة',
                'خمسة': 'خمسة',
                'ستة': 'ستة',
                'سبعة': 'سبعة',
                'ثمانية': 'ثمانية',
                'تسعة': 'تسعة',
                'عشرة': 'عشرة'
            }
            
            for wrong, correct in corrections.items():
                text = text.replace(wrong, correct)
            
            return text
        
        integer_words = clean_arabic_text(integer_words)
        
        if integer_part == 0:
            currency_word = ""
        elif integer_part == 1:
            currency_word = currency_data['singular']
        elif integer_part == 2:
            currency_word = currency_data['dual']
        elif integer_part <= 10:
            currency_word = currency_data['singular']
        else:
            currency_word = currency_data['plural']
        
        result_parts = []
        if integer_words and currency_word:
            result_parts.append(f"{integer_words} {currency_word}")
        elif integer_words:
            result_parts.append(integer_words)
        
        if fractional_part > 0 and fraction_words:
            fraction_words = clean_arabic_text(fraction_words)
            
            if fractional_part == 1:
                fraction_currency = currency_data['fraction']
            elif fractional_part == 2:
                fraction_currency = currency_data['fraction_dual']
            elif fractional_part <= 10:
                fraction_currency = currency_data['fraction']
            else:
                fraction_currency = currency_data['fraction_plural']
            
            if fraction_words and fraction_currency:
                result_parts.append(f"{fraction_words} {fraction_currency}")
        
        if not result_parts:
            result = "صفر"
        else:
            result = " و".join(result_parts)
        
        result += " فقط لا غير"
        
        return JsonResponse({
            'success': True,
            'amount_in_words': result,
            'amount_numeric': f"{amount_float:,.2f}",
            'currency': currency_data,
            'parts': {
                'integer': integer_part,
                'fraction': fractional_part,
                'integer_words': integer_words,
                'fraction_words': fraction_words
            }
        })
        
    except Exception as e:
        logger.error(f"خطأ في تحويل المبلغ إلى كلمات: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'حدث خطأ في التحويل'
        })


@require_GET
@login_required
def get_current_amount_in_words(request):
    """API للحصول على المبلغ الحالي للفاتورة مكتوباً (يُستدعى من الواجهة)"""
    from num2words import num2words
    
    purchase_id = request.GET.get('purchase_id')
    amount = request.GET.get('amount')
    currency_id = request.GET.get('currency_id')
    
    try:
        if purchase_id:
            purchase = Purch.objects.get(id=purchase_id)
            amount_in_words = purchase.get_total_in_words()
            amount_numeric = purchase.purch_final_total
            currency_data = purchase.get_currency_info() if purchase.purch_currency else {
                'code': 'SYP',
                'symbol': 'ل.س',
                'name_ar': 'ليرة سورية'
            }
        elif amount:
            amount_decimal = Decimal(amount)
            currency_info = {}
            
            if currency_id:
                try:
                    currency = Currency.objects.get(id=currency_id)
                    currency_info = {
                        'code': currency.code,
                        'symbol': currency.symbol,
                        'name_ar': currency.name_ar
                    }
                except Currency.DoesNotExist:
                    currency_info = {
                        'code': 'SYP',
                        'symbol': 'ل.س',
                        'name_ar': 'ليرة سورية'
                    }
            
            try:
                if currency_id:
                    currency = Currency.objects.get(id=currency_id)
                    currency_info = {
                        'singular': currency.singular_ar,
                        'dual': currency.dual_ar,
                        'plural': currency.plural_ar,
                        'fraction': currency.fraction_name_ar,
                        'fraction_dual': currency.fraction_dual_ar,
                        'fraction_plural': currency.fraction_plural_ar,
                        'decimals': currency.decimals
                    }
                else:
                    currency_info = {
                        'singular': 'ليرة سورية',
                        'dual': 'ليرتان سوريتان',
                        'plural': 'ليرات سورية',
                        'fraction': 'قرش',
                        'fraction_dual': 'قرشان',
                        'fraction_plural': 'قروش',
                        'decimals': 2
                    }
                
                amount_float = float(amount_decimal)
                integer_part = int(amount_float)
                fractional_part = int(round((amount_float - integer_part) * (10 ** currency_info['decimals'])))
                
                integer_words = num2words(integer_part, lang='ar')
                integer_words = integer_words.replace('مئة', 'مائة')
                
                if integer_part == 0:
                    currency_word = currency_info['singular']
                elif integer_part == 1:
                    currency_word = currency_info['singular']
                elif integer_part == 2:
                    currency_word = currency_info['dual']
                elif integer_part <= 10:
                    currency_word = currency_info['singular']
                else:
                    currency_word = currency_info['plural']
                
                result = f"{integer_words} {currency_word}".strip()
                
                if fractional_part > 0:
                    fraction_words = num2words(fractional_part, lang='ar')
                    fraction_words = fraction_words.replace('مئة', 'مائة')
                    
                    if fractional_part == 1:
                        fraction_currency = currency_info['fraction']
                    elif fractional_part == 2:
                        fraction_currency = currency_info['fraction_dual']
                    elif fractional_part <= 10:
                        fraction_currency = currency_info['fraction']
                    else:
                        fraction_currency = currency_info['fraction_plural']
                    
                    if integer_part == 0:
                        result = f"{fraction_words} {fraction_currency}"
                    else:
                        result += f" و{fraction_words} {fraction_currency}"
                
                result += " فقط لا غير"
                amount_in_words = result
                
            except Exception as e:
                logger.error(f"خطأ في التحويل المباشر: {e}")
                amount_in_words = f"{amount} فقط لا غير"
            
            amount_numeric = amount_decimal
            currency_data = currency_info
        else:
            return JsonResponse({
                'success': False,
                'error': 'يجب تقديم purchase_id أو amount'
            })
        
        return JsonResponse({
            'success': True,
            'amount_in_words': amount_in_words,
            'amount_numeric': f"{amount_numeric:,.2f}",
            'currency': currency_data
        })
        
    except Purch.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'الفاتورة غير موجودة'
        })
    except Exception as e:
        logger.error(f"خطأ في جلب المبلغ المكتوب: {e}")
        # 🔒 تحسين أمني
        return JsonResponse({
            'success': False,
            'error': 'حدث خطأ أثناء جلب البيانات'
        })



#================================================
#               دوال البحث (APIs)              #
# ===============================================



@require_GET
@login_required
def search_suppliers(request):
    """بحث عن الموردين للإكمال التلقائي (مُحسَّن لجلب بيانات Profile)"""
    query = request.GET.get('q', '')
    suppliers = []
    
    if query:
        # --- التعديل الرئيسي هنا ---
        # 1. نستخدم select_related لجلب بيانات المرتبطة (Profile) بكفاءة في استعلام واحد.
        # 2. هذا يمنع حدوث مشكلة N+1 queries ويحسن الأداء بشكل كبير.
        supplier_users = User.objects.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        ).select_related('profile').distinct()[:10]
        
        for user in supplier_users:
            # --- التعديل الثاني هنا ---
            # نحاول الوصول إلى بيانات الملف الشخصي (Profile) بأمان.
            # hasattr() تتحقق مما إذا كان الكائن 'user' يحتوي على علاقة 'profile'.
            # هذا يمنع حدوث خطأ DoesNotExist إذا كان مستخدم بدون ملف شخصي.
            if hasattr(user, 'profile'):
                profile = user.profile
                phone = profile.phone_number or ''
                address = profile.address or ''
            else:
                # إذا لم يكن هناك ملف شخصي، نستخدم قيم فارغة.
                phone = ''
                address = ''
            
            suppliers.append({
                'id': user.id,
                'text': f"{user.get_full_name() or user.username}",
                # نستخدم القيم التي حصلنا عليها من Profile
                'phone': phone,
                'address': address,
            })
    
    # لم نتغير في شيء هنا، الـ JSON يبقى بنفس الشكل
    return JsonResponse({'results': suppliers})


@require_GET
@login_required
def search_products(request):
    """بحث عن المنتجات للإكمال التلقائي"""
    query = request.GET.get('q', '')
    products = []
    
    if query:
        try:
            product_results = Product.objects.filter(
                Q(product_name__icontains=query) |
                Q(product_description__icontains=query) |
                Q(main_barcode__icontains=query)
            ).distinct()[:10]
            
            for product in product_results:
                purchase_price = getattr(product, 'purch_price', '0.00')
                price = getattr(product, 'retail_price', '0.00')
                final_price = purchase_price or price or '0.00'
                
                image_url = None
                if product.product_image:
                    image_url = product.product_image.url
                
                # تحسين نص العرض ليتضمن الباركود إذا كان موجوداً
                display_text = product.product_name
                if product.main_barcode:
                    display_text = f"{product.product_name} - {product.main_barcode}"
                
                products.append({
                    'id': product.id,
                    'text': display_text, # النص الذي يظهر في القائمة المنسدلة
                    'price': str(final_price),
                    'image_url': image_url,
                    'barcode': product.main_barcode # إضافة الباركود كبيانات إضافية إن احتجتها في الجافاسكريبت
                })
                
        except Exception as e:
            logger.error(f"Error in product search: {e}")
            try:
                product_results = Product.objects.filter(
                    Q(product_name__icontains=query) |
                    Q(main_barcode__icontains=query)
                )[:10]
                
                for product in product_results:
                    purchase_price = getattr(product, 'purch_price', '0.00')
                    price = getattr(product, 'retail_price', '0.00')
                    final_price = purchase_price or price or '0.00'
                    
                    image_url = None
                    if product.product_image:
                        image_url = product.product_image.url
                    
                    display_text = product.product_name
                    if product.main_barcode:
                        display_text = f"{product.product_name} - {product.main_barcode}"
                    
                    products.append({
                        'id': product.id,
                        'text': display_text,
                        'price': str(final_price),
                        'image_url': image_url,
                        'barcode': product.main_barcode
                    })
            except Exception as e2:
                logger.error(f"Error in fallback search: {e2}")
                products = []
    
    return JsonResponse({'results': products})





@login_required
@permission_required('invoice.view_sale', raise_exception=True)
def get_sale_items_for_return(request, sale_id):
    """API لجلب بنود الفاتورة الأصلية مع إمكانية تحديد الكميات القابلة للإرجاع"""
    try:
        sale = Sale.objects.get(id=sale_id)
        
        # جلب جميع بنود الفاتورة مع معلومات الإرجاع السابقة
        items = []
        for item in sale.saleitem_set.all():
            # حساب الكمية التي تم إرجاعها سابقاً لهذا البند
            returned_qty = SaleReturnItem.objects.filter(
                original_sale_item=item,
                sale_return__isnull=False
            ).aggregate(total=Sum('returned_quantity'))['total'] or Decimal('0.00')
            
            # الكمية القابلة للإرجاع = الكمية المباعة - الكمية المرتجعة سابقاً
            available_to_return = max(Decimal('0.00'), item.sold_quantity - returned_qty)
            
            # جلب الباركودات الخاصة بهذا البند
            barcodes = []
            if item.product:
                for ib in item.item_barcodes.filter(barcode_status='active'):
                    barcodes.append({
                        'id': ib.barcode.id,
                        'barcode_in': ib.barcode.barcode_in,
                        'status': ib.barcode.status
                    })
            
            items.append({
                'id': item.id,
                'product_id': item.product.id if item.product else None,
                'product_name': item.item_name,
                'sold_quantity': float(item.sold_quantity),
                'returned_quantity': float(returned_qty),
                'available_to_return': float(available_to_return),
                'unit_price': float(item.unit_price),
                'has_barcode': len(barcodes) > 0,
                'barcodes': barcodes
            })
        
        return JsonResponse({
            'success': True,
            'sale_number': sale.uniqueId,
            'items': items,
            'currency': {
                'id': sale.sale_currency.id if sale.sale_currency else None,
                'name': sale.sale_currency.name_ar if sale.sale_currency else 'ليرة سورية'
            }
        })
        
    except Sale.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'الفاتورة غير موجودة'}, status=404)
    except Exception as e:
        logger.error(f"خطأ في جلب بنود الفاتورة للإرجاع: {e}", exc_info=True)
        # 🔒 تحسين أمني للـ API
        return JsonResponse({'success': False, 'error': 'حدث خطأ أثناء جلب البيانات'}, status=500)


@login_required
@permission_required('invoice.add_salereturn', raise_exception=True)
def check_barcode_for_return(request, product_id):
    """API للتحقق من صحة الباركود للإرجاع"""
    try:
        product = Product.objects.get(id=product_id)
        barcode_value = request.GET.get('barcode')
        sale_item_id = request.GET.get('sale_item_id')
        
        if not barcode_value:
            return JsonResponse({'success': False, 'error': 'لم يتم إرسال قيمة الباركود'})
        
        # البحث عن الباركود
        try:
            barcode_obj = Barcode.objects.get(barcode_in=barcode_value, product=product)
        except Barcode.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'error': 'الباركود غير موجود لهذا المنتج'
            })
        
        # التحقق من أن هذا الباركود كان مباعاً في هذه الفاتورة
        if barcode_obj.status != 'sold':
            return JsonResponse({
                'success': False,
                'error': f'هذا الباركود غير مباع (حالته: {barcode_obj.get_status_display()})'
            })
        
        # التحقق من أن الباركود تابع لهذا البند (إذا تم تحديد البند)
        if sale_item_id:
            is_in_sale_item = SaleItemBarcode.objects.filter(
                sale_item_id=sale_item_id,
                barcode=barcode_obj,
                barcode_status='active'
            ).exists()
            
            if not is_in_sale_item:
                return JsonResponse({
                    'success': False,
                    'error': 'هذا الباركود ليس من ضمن بنود هذه الفاتورة'
                })
        
        # التحقق من أن الباركود لم يُرجع سابقاً
        already_returned = SaleReturnItemBarcode.objects.filter(
            barcode=barcode_obj,
            barcode_status='returned'
        ).exists()
        
        if already_returned:
            return JsonResponse({
                'success': False,
                'error': 'تم إرجاع هذا الباركود سابقاً'
            })
        
        return JsonResponse({
            'success': True,
            'message': 'باركود صالح للإرجاع',
            'barcode_id': barcode_obj.id,
            'barcode_value': barcode_obj.barcode_in
        })
        
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'المنتج غير موجود'}, status=404)
    except Exception as e:
        logger.error(f"خطأ في التحقق من الباركود للإرجاع: {e}", exc_info=True)
        # 🔒 تحسين أمني للـ API
        return JsonResponse({'success': False, 'error': 'حدث خطأ أثناء التحقق من الباركود'}, status=500)






#================================================
#  الجداول المساعدة 
# ===============================================


# ================ عملات ================
class CurrencyListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Currency
    template_name = 'invoice/Currency/currency_list.html'
    context_object_name = 'currencies'
    paginate_by = 10
    permission_required = 'invoice.view_currency'

    def get_queryset(self):
        return Currency.objects.all().order_by('code')

class CurrencyDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Currency
    template_name = 'invoice/Currency/currency_detail.html'
    context_object_name = 'currency'
    permission_required = 'invoice.view_currency'

class CurrencyCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Currency
    form_class = CurrencyForm
    template_name = 'invoice/Currency/currency_form.html'
    success_url = reverse_lazy('invoice:currency_list')
    permission_required = 'invoice.add_currency'

    def form_valid(self, form):
        messages.success(self.request, _('تمت إضافة العملة بنجاح'))
        return super().form_valid(form)

class CurrencyUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Currency
    form_class = CurrencyForm
    template_name = 'invoice/Currency/currency_form.html'
    success_url = reverse_lazy('invoice:currency_list')
    permission_required = 'invoice.change_currency'

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث العملة بنجاح'))
        return super().form_valid(form)

class CurrencyDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Currency
    template_name = 'invoice/Currency/currency_confirm_delete.html'
    success_url = reverse_lazy('invoice:currency_list')
    permission_required = 'invoice.delete_currency'

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, _('تم حذف العملة بنجاح'))
        return super().delete(request, *args, **kwargs)


# ================ طرق الدفع ================
class PaymentMethodListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Payment_method
    template_name = 'invoice/Payment_method/payment_method_list.html'
    context_object_name = 'payment_methods'
    paginate_by = 10
    permission_required = 'invoice.view_payment_method'

    def get_queryset(self):
        return Payment_method.objects.all().order_by('name')

class PaymentMethodDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Payment_method
    template_name = 'invoice/Payment_method/payment_method_detail.html'
    context_object_name = 'payment_method'
    permission_required = 'invoice.view_payment_method'

class PaymentMethodCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Payment_method
    form_class = PaymentMethodForm
    template_name = 'invoice/Payment_method/payment_method_form.html'
    success_url = reverse_lazy('invoice:payment_method_list')
    permission_required = 'invoice.add_payment_method'

    def form_valid(self, form):
        messages.success(self.request, _('تمت إضافة طريقة الدفع بنجاح'))
        return super().form_valid(form)

class PaymentMethodUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Payment_method
    form_class = PaymentMethodForm
    template_name = 'invoice/Payment_method/payment_method_form.html'
    success_url = reverse_lazy('invoice:payment_method_list')
    permission_required = 'invoice.change_payment_method'

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث طريقة الدفع بنجاح'))
        return super().form_valid(form)

class PaymentMethodDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Payment_method
    template_name = 'invoice/Payment_method/payment_method_confirm_delete.html'
    success_url = reverse_lazy('invoice:payment_method_list')
    permission_required = 'invoice.delete_payment_method'

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, _('تم حذف طريقة الدفع بنجاح'))
        return super().delete(request, *args, **kwargs)


# ================ شركات الشحن ================
class ShippingCompanyListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Shipping_com_m
    template_name = 'invoice/Shipping_com_m/shipping_company_list.html'
    context_object_name = 'shipping_companies'
    paginate_by = 10
    permission_required = 'invoice.view_shipping_com_m'

    def get_queryset(self):
        return Shipping_com_m.objects.all().order_by('name')

class ShippingCompanyDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Shipping_com_m
    template_name = 'invoice/Shipping_com_m/shipping_company_detail.html'
    context_object_name = 'shipping_company'
    permission_required = 'invoice.view_shipping_com_m'

class ShippingCompanyCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Shipping_com_m
    form_class = ShippingCompanyForm
    template_name = 'invoice/Shipping_com_m/shipping_company_form.html'
    success_url = reverse_lazy('invoice:shipping_company_list')
    permission_required = 'invoice.add_shipping_com_m'

    def form_valid(self, form):
        messages.success(self.request, _('تمت إضافة شركة الشحن بنجاح'))
        return super().form_valid(form)

class ShippingCompanyUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Shipping_com_m
    form_class = ShippingCompanyForm
    template_name = 'invoice/Shipping_com_m/shipping_company_form.html'
    success_url = reverse_lazy('invoice:shipping_company_list')
    permission_required = 'invoice.change_shipping_com_m'

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث شركة الشحن بنجاح'))
        return super().form_valid(form)

class ShippingCompanyDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Shipping_com_m
    template_name = 'invoice/Shipping_com_m/shipping_company_confirm_delete.html'
    success_url = reverse_lazy('invoice:shipping_company_list')
    permission_required = 'invoice.delete_shipping_com_m'

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, _('تم حذف شركة الشحن بنجاح'))
        return super().delete(request, *args, **kwargs)


# ================ الحالات ================
class StatusListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Status
    template_name = 'invoice/Status/status_list.html'
    context_object_name = 'statuses'
    paginate_by = 10
    permission_required = 'invoice.view_status'

    def get_queryset(self):
        return Status.objects.all().order_by('name')

class StatusDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Status
    template_name = 'invoice/Status/status_detail.html'
    context_object_name = 'status'
    permission_required = 'invoice.view_status'

class StatusCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Status
    form_class = StatusForm
    template_name = 'invoice/Status/status_form.html'
    success_url = reverse_lazy('invoice:status_list')
    permission_required = 'invoice.add_status'

    def form_valid(self, form):
        messages.success(self.request, _('تمت إضافة الحالة بنجاح'))
        return super().form_valid(form)

class StatusUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Status
    form_class = StatusForm
    template_name = 'invoice/Status/status_form.html'
    success_url = reverse_lazy('invoice:status_list')
    permission_required = 'invoice.change_status'

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث الحالة بنجاح'))
        return super().form_valid(form)

class StatusDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Status
    template_name = 'invoice/Status/status_confirm_delete.html'
    success_url = reverse_lazy('invoice:status_list')
    permission_required = 'invoice.delete_status'

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, _('تم حذف الحالة بنجاح'))
        return super().delete(request, *args, **kwargs)


# ================ أنواع الأسعار ================
class PriceTypeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = PriceType
    template_name = 'invoice/PriceType/price_type_list.html'
    context_object_name = 'price_types'
    paginate_by = 10
    permission_required = 'invoice.view_pricetype'

    def get_queryset(self):
        return PriceType.objects.all().order_by('name')

class PriceTypeDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = PriceType
    template_name = 'invoice/PriceType/price_type_detail.html'
    context_object_name = 'price_type'
    permission_required = 'invoice.view_pricetype'

class PriceTypeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = PriceType
    form_class = PriceTypeForm
    template_name = 'invoice/PriceType/price_type_form.html'
    success_url = reverse_lazy('invoice:price_type_list')
    permission_required = 'invoice.add_pricetype'

    def form_valid(self, form):
        messages.success(self.request, _('تمت إضافة نوع السعر بنجاح'))
        return super().form_valid(form)

class PriceTypeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = PriceType
    form_class = PriceTypeForm
    template_name = 'invoice/PriceType/price_type_form.html'
    success_url = reverse_lazy('invoice:price_type_list')
    permission_required = 'invoice.change_pricetype'

    def form_valid(self, form):
        messages.success(self.request, _('تم تحديث نوع السعر بنجاح'))
        return super().form_valid(form)

class PriceTypeDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = PriceType
    template_name = 'invoice/PriceType/price_type_confirm_delete.html'
    success_url = reverse_lazy('invoice:price_type_list')
    permission_required = 'invoice.delete_pricetype'

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, _('تم حذف نوع السعر بنجاح'))
        return super().delete(request, *args, **kwargs)



@login_required
@permission_required('invoice.view_barcode', raise_exception=True)
def get_product_barcodes(request, product_id):
    """
    API ذكي لجلب الباركودات المتاحة للبيع والتحقق منها.
    يعالج حالات إنشاء فاتورة جديدة (active فقط) وتعديل فاتورة قديمة (active + المرتبطة بالبند الحالي).
    """
    try:
        product = Product.objects.get(id=product_id)
        
        # معاملات اختيارية تأتي من الجافاسكربت
        check_barcode = request.GET.get('check_barcode')
        sale_item_id = request.GET.get('sale_item_id')
        
        # ============================================
        # السيناريو 1: التحقق من باركود محدد (عند الكتابة في الحقل)
        # ============================================
        if check_barcode:
            try:
                barcode_obj = Barcode.objects.get(barcode_in=check_barcode, product=product)
                
                # باركود نشط -> متاح للبيع
                if barcode_obj.status == 'active':
                    return JsonResponse({'is_valid': True, 'message': 'باركود متاح'})
                
                # باركود مباع -> نتحقق إن كان ملكاً لبند الفاتورة الحالي (في حالة التعديل)
                elif barcode_obj.status == 'sold':
                    # SaleItemBarcode يجب أن يكون مستوردا في أعلى الملف
                    is_owner = SaleItemBarcode.objects.filter(
                        barcode=barcode_obj, 
                        sale_item_id=sale_item_id
                    ).exists()
                    
                    if is_owner:
                        return JsonResponse({'is_valid': True, 'message': 'موجود في الفاتورة الحالية'})
                    else:
                        return JsonResponse({'is_valid': False, 'message': 'هذا الباركود مباع مسبقاً لفاتورة أخرى'})
                
                # حالات أخرى (تالف، مرتجع، إلخ)
                else:
                    return JsonResponse({'is_valid': False, 'message': f'حالة الباركود غير متاحة: {barcode_obj.get_status_display()}'})
                    
            except Barcode.DoesNotExist:
                return JsonResponse({'is_valid': False, 'message': 'الباركود غير موجود أو لا ينتمي لهذا المنتج'})
        
        # ============================================
        # السيناريو 2: جلب قائمة الباركودات (عند فتح قائمة الباركودات)
        # ============================================
        else:
            # جلب الباركودات النشطة فقط (غير المباعة)
            barcodes_qs = Barcode.objects.filter(
                product=product, 
                status='active'
            ).order_by('barcode_in')
            
            # تحويلها إلى قائمة قاموسات
            barcodes_list = list(barcodes_qs.values('id', 'barcode_in', 'barcode_out'))
            
            # في حالة تعديل الفاتورة، نضيف الباركودات المرتبطة بالبند الحالي حتى لو كانت (sold)
            # حتى يتمكن المستخدم من رؤيتها وتعديلها
            if sale_item_id:
                item_barcodes = SaleItemBarcode.objects.filter(
                    sale_item_id=sale_item_id
                ).select_related('barcode')
                
                # نجمع IDs الباركودات النشطة لمنع التكرار
                active_ids = set(b['id'] for b in barcodes_list)
                
                for ib in item_barcodes:
                    if ib.barcode_id not in active_ids:
                        barcodes_list.append({
                            'id': ib.barcode_id,
                            'barcode_in': ib.barcode.barcode_in,
                            'barcode_out': ib.barcode.barcode_out,
                            'is_current_item': True  # علامة للجافاسكربت أنه باركود خاص بالبند الحالي
                        })
            
            return JsonResponse({
                'success': True,
                'product_name': product.product_name,
                'barcodes': barcodes_list,
                'count': len(barcodes_list),
                'has_barcodes': len(barcodes_list) > 0
            })
            
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'المنتج غير موجود'}, status=404)
    except Exception as e:
        logger.error(f"خطأ في جلب باركودات المنتج: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'حدث خطأ أثناء جلب الباركودات'}, status=500)





# **********************************************************************************
#                       التقارير      REPORT
# ******************************************************************************






# **********************************************************************************
# ==================== القسم الأول: دوال مساعدة ================================
# **********************************************************************************

class Date(Func):
    function = 'DATE'
    output_field = CharField()


def get_email_settings():
    obj, created = EmailSetting.objects.get_or_create(pk=1)
    return obj


def send_custom_email(subject, message, recipient_list):
    config = get_email_settings()
    
    try:
        send_mail(
            subject,
            message,
            config.default_from_email,
            recipient_list,
            fail_silently=False,
            auth_user=config.email_host_user,
            auth_password=config.email_host_password,
            connection=None 
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


# **********************************************************************************
# ==================== القسم الثاني: تقارير الحسابات والفواتير ==================
# **********************************************************************************




@login_required
@permission_required('invoice.view_report', raise_exception=True)
def statement_report_view(request):
    context = {}
    statement_data = []
    total_debit = Decimal('0.00')  
    total_credit = Decimal('0.00') 
    running_balance = Decimal('0.00')
    
    selected_user = None
    user_type = None

    customer_ids = Sale.objects.values_list('sale_customer_id', flat=True).distinct()
    supplier_ids = Purch.objects.values_list('purch_supplier_id', flat=True).distinct()
    
    context['customers'] = User.objects.filter(id__in=customer_ids)
    context['suppliers'] = User.objects.filter(id__in=supplier_ids)

    if request.method == 'GET' and 'user_id' in request.GET:
        user_id = request.GET.get('user_id')
        
        try:
            selected_user = User.objects.get(id=user_id)
            raw_transactions = []

            is_customer = Sale.objects.filter(sale_customer=selected_user).exists()
            is_supplier = Purch.objects.filter(purch_supplier=selected_user).exists()
            
            if is_customer: 
                user_type = 'customer'
            elif is_supplier: 
                user_type = 'supplier'

            # ============================================
            # 1. فواتير المبيعات (للعملاء)
            # ============================================
            if is_customer:
                sales = Sale.objects.filter(sale_customer=selected_user).order_by('sale_date')
                for sale in sales:
                    paid_amount = CashTransaction.objects.filter(
                        sale_invoice=sale,
                        transaction_type='sale_receipt'
                    ).aggregate(total=Sum('amount_in'))['total'] or Decimal('0.00')
                    
                    raw_transactions.append({
                        'trans_date': sale.sale_date,
                        'trans_type': 'invoice_sale',
                        'ref_number': sale.uniqueId,
                        'slug': sale.slug,
                        'debit_amount': sale.sale_final_total,
                        'credit_amount': paid_amount,
                        'note': f"فاتورة مبيعات" + (f" - المدفوع: {paid_amount}" if paid_amount > 0 else "")
                    })

            # ============================================
            # 2. فواتير المشتريات (للموردين)
            # ============================================
            if is_supplier:
                purchases = Purch.objects.filter(purch_supplier=selected_user).order_by('purch_date')
                for purch in purchases:
                    paid_amount = CashTransaction.objects.filter(
                        purchase_invoice=purch,
                        transaction_type='purchase_payment'
                    ).aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')
                    
                    raw_transactions.append({
                        'trans_date': purch.purch_date,
                        'trans_type': 'invoice_purch',
                        'ref_number': purch.uniqueId,
                        'slug': purch.slug,
                        'debit_amount': paid_amount,
                        'credit_amount': purch.purch_final_total,
                        'note': f"فاتورة مشتريات" + (f" - المدفوع: {paid_amount}" if paid_amount > 0 else "")
                    })

            # ============================================
            # 3. مرتجعات المبيعات (جلب البيانات من الصندوق)
            # ============================================
            if is_customer:
                sale_returns = SaleReturn.objects.filter(
                    original_sale__sale_customer=selected_user
                ).select_related('original_sale')
                
                for ret in sale_returns:
                    refunded_amount = CashTransaction.objects.filter(
                        sale_return=ret,
                        transaction_type='sale_return'
                    ).aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')
                    
                    raw_transactions.append({
                        'trans_date': ret.return_date,
                        'trans_type': 'return_sale',
                        'ref_number': ret.uniqueId,
                        'slug': ret.slug,
                        'original_ref': ret.original_sale.uniqueId,
                        'original_slug': ret.original_sale.slug,
                        'debit_amount': refunded_amount,               
                        'credit_amount': ret.return_final_total,       
                        'note': f"مرتجع مبيعات - عن فاتورة {ret.original_sale.uniqueId}" + (f" - المردود للعميل: {refunded_amount}" if refunded_amount > 0 else "")
                    })

            # ============================================
            # 4. مرتجعات المشتريات (جلب البيانات من الصندوق)
            # ============================================
            if is_supplier:
                purchase_returns = PurchaseReturn.objects.filter(
                    original_purchase__purch_supplier=selected_user
                ).select_related('original_purchase')
                
                for ret in purchase_returns:
                    received_amount = CashTransaction.objects.filter(
                        purchase_return=ret,
                        transaction_type='purchase_return'
                    ).aggregate(total=Sum('amount_in'))['total'] or Decimal('0.00')
                    
                    raw_transactions.append({
                        'trans_date': ret.return_date,
                        'trans_type': 'return_purch',
                        'ref_number': ret.uniqueId,
                        'slug': ret.slug,
                        'original_ref': ret.original_purchase.uniqueId,
                        'original_slug': ret.original_purchase.slug,
                        'debit_amount': ret.return_final_total,         
                        'credit_amount': received_amount,               
                        'note': f"مرتجع مشتريات - عن فاتورة {ret.original_purchase.uniqueId}" + (f" - المستلم من المورد: {received_amount}" if received_amount > 0 else "")
                    })

            # ============================================
            # 5. الترتيب والحساب النهائي
            # ============================================
            def get_sort_date(x):
                d = x.get('trans_date')
                if d is None:
                    return datetime.datetime.min
                if isinstance(d, datetime.date) and not isinstance(d, datetime.datetime):
                    return datetime.datetime.combine(d, datetime.time.min)
                return d

            raw_transactions.sort(key=get_sort_date)

            total_debit = Decimal('0.00')
            total_credit = Decimal('0.00')
            running_balance = Decimal('0.00')
            statement_data = []

            for trans in raw_transactions:
                debit = trans['debit_amount'] if trans['debit_amount'] else Decimal('0.00')
                credit = trans['credit_amount'] if trans['credit_amount'] else Decimal('0.00')
                
                total_debit += debit
                total_credit += credit
                
                if user_type == 'customer':
                    running_balance = total_debit - total_credit
                elif user_type == 'supplier':
                    running_balance = total_credit - total_debit
                else:
                    running_balance = total_debit - total_credit
                
                trans['balance'] = running_balance
                statement_data.append(trans)

            context['statement_data'] = statement_data
            context['total_debit'] = total_debit
            context['total_credit'] = total_credit
            context['final_balance'] = running_balance
            
        except User.DoesNotExist:
            messages.error(request, "المستخدم غير موجود")
        except Exception as e:
            messages.error(request, "حدث خطأ أثناء تحميل كشف الحساب")
            import traceback
            traceback.print_exc()

    context['selected_user'] = selected_user
    context['user_type'] = user_type
    return render(request, 'invoice/reports/statement_report.html', context)



@login_required
@permission_required('invoice.view_report', raise_exception=True)
def barcode_statement_view(request):
    context = {}
    movements = []
    barcode_obj = None
    product_obj = None
    search_query = request.GET.get('q', '').strip()

    if search_query:
        # 1. البحث أولاً في جدول الباركودات
        barcode_obj = Barcode.objects.filter(barcode_in=search_query).select_related('product').first()

        # 2. إذا لم يتم إيجاده، نبحث في حقل main_barcode بجدول المواد
        if not barcode_obj:
            product_obj = Product.objects.filter(main_barcode=search_query).prefetch_related('barcodes').first()

        # تحديد قائمة الباركودات التي سنبحث عن حركتها
        if barcode_obj:
            target_barcodes = [barcode_obj]
        elif product_obj:
            # جلب جميع الباركودات المرتبطة بالمادة
            target_barcodes = list(product_obj.barcodes.all())
        else:
            target_barcodes = []

        # إذا وجدنا باركودات، نبحث عن حركاتها
        if target_barcodes:
            barcode_ids = [b.pk for b in target_barcodes]

            # شراء
            purchase_items = PurchItemBarcode.objects.filter(
                barcode_id__in=barcode_ids
            ).select_related('purch_item__purch', 'purch_item__product', 'barcode')

            for item in purchase_items:
                movements.append({
                    'date': item.purch_item.purch.purch_date,
                    'type': 'purchase',
                    'type_display': 'فاتورة شراء',
                    'reference': item.purch_item.purch.uniqueId,
                    'detail': f"شراء - {item.purch_item.product.product_name if item.purch_item.product else item.purch_item.item_name}",
                    'quantity': item.quantity_used,
                    'status_display': 'نشط (Active)',
                    'status_class': 'status-active',
                    'barcode_in': item.barcode.barcode_in, # لإظهار رقم الباركود في الجدول
                })

            # مرتجع شراء
            return_items = PurchaseReturnItemBarcode.objects.filter(
                barcode_id__in=barcode_ids
            ).select_related('purchase_return_item__purchase_return', 'purchase_return_item__product', 'barcode')

            for item in return_items:
                movements.append({
                    'date': item.purchase_return_item.purchase_return.return_date,
                    'type': 'purchase_return',
                    'type_display': 'مرتجع شراء',
                    'reference': item.purchase_return_item.purchase_return.uniqueId,
                    'detail': f"إرجاع للمورد - {item.purchase_return_item.product.product_name if item.purchase_return_item.product else item.purchase_return_item.item_name}",
                    'quantity': item.quantity_used,
                    'status_display': 'مرتجع للمورد',
                    'status_class': 'status-returned',
                    'barcode_in': item.barcode.barcode_in,
                })

            # مبيعات
            sale_items = SaleItemBarcode.objects.filter(
                barcode_id__in=barcode_ids
            ).select_related('sale_item__sale', 'sale_item__product', 'barcode')

            for item in sale_items:
                movements.append({
                    'date': item.sale_item.sale.sale_date,
                    'type': 'sale',
                    'type_display': 'فاتورة بيع',
                    'reference': item.sale_item.sale.uniqueId,
                    'detail': f"بيع - {item.sale_item.product.product_name if item.sale_item.product else item.sale_item.item_name}",
                    'quantity': item.quantity_used,
                    'status_display': 'مباع (Sold)',
                    'status_class': 'status-sold',
                    'barcode_in': item.barcode.barcode_in,
                })

            # مرتجع مبيعات
            sale_return_items = SaleReturnItemBarcode.objects.filter(
                barcode_id__in=barcode_ids
            ).select_related('sale_return_item__sale_return', 'sale_return_item__product', 'barcode')

            for item in sale_return_items:
                movements.append({
                    'date': item.sale_return_item.sale_return.return_date,
                    'type': 'sale_return',
                    'type_display': 'مرتجع بيع',
                    'reference': item.sale_return_item.sale_return.uniqueId,
                    'detail': f"إرجاع من العميل - {item.sale_return_item.product.product_name if item.sale_return_item.product else item.sale_return_item.item_name}",
                    'quantity': item.quantity_used,
                    'status_display': 'مرتجع (Returned)',
                    'status_class': 'status-returned',
                    'barcode_in': item.barcode.barcode_in,
                })

            # ترتيب الحركات حسب التاريخ
            movements.sort(key=lambda x: x['date'] or datetime.date.min)

        # رسالة التنبيه إذا لم يتم إيجاد الباركود في الجدولين
        if not barcode_obj and not product_obj:
            messages.error(request, "الباركود غير موجود في نظام الباركودات ولا كباركود رئيسي للمواد")

    context['movements'] = movements
    context['barcode_obj'] = barcode_obj
    context['product_obj'] = product_obj # أضفنا هذا المتغير للقالب
    context['search_query'] = search_query
    return render(request, 'invoice/reports/barcode_statement.html', context)


@login_required
@permission_required('invoice.view_report', raise_exception=True)
def unpaid_sales_report(request):
    """تقرير فواتير المبيعات غير المدفوعة بالكامل (متابعة الديون)"""
    invoices = Sale.objects.filter(
        Q(balance_due__gt=0) | Q(is_paid=False)
    ).select_related('sale_customer').order_by('-sale_date')

    period_ranges = [
        (0, 30, 'حديث'),
        (31, 60, 'متأخر'),
        (61, 90, 'متأخر جداً'),
        (91, 9999, 'متعثر'),
    ]

    report_data = []
    grand_total_balance = 0
    today = timezone.now().date()

    for invoice in invoices:
        days_overdue = (today - invoice.sale_date).days
        category = "غير محدد"
        for start, end, label in period_ranges:
            if start <= days_overdue <= end:
                category = label
                break
        
        report_data.append({
            'invoice': invoice,
            'customer': invoice.sale_customer,
            'date': invoice.sale_date,
            'total': invoice.sale_final_total,
            'paid': invoice.paid_amount,
            'balance': invoice.balance_due,
            'days_overdue': days_overdue,
            'category': category,
        })
        
        grand_total_balance += invoice.balance_due

    context = {
        'title': 'تقرير الفواتير الغير مدفوعة ',
        'report_data': report_data,
        'grand_total_balance': grand_total_balance,
    }
    
    return render(request, 'invoice/reports/unpaid_sales_report.html', context)


@login_required
@permission_required('invoice.view_report', raise_exception=True)
def dead_stock_report(request):
    """تقرير المنتجات الراكدة (موجودة ولم يتم بيعها منذ فترة)"""
    days_threshold = int(request.GET.get('days', 60))
    date_threshold = timezone.now().date() - timedelta(days=days_threshold)

    products = Product.objects.filter(
        current_stock_quantity__gt=0
    ).order_by('product_name')

    dead_items = []

    for product in products:
        last_sale_item = SaleItem.objects.filter(
            product=product
        ).order_by('-sale__sale_date').first()
        
        last_sale_date = None
        if last_sale_item and last_sale_item.sale:
            last_sale_date = last_sale_item.sale.sale_date
        
        has_recent_sales = SaleItem.objects.filter(
            product=product,
            sale__sale_date__gte=date_threshold
        ).exists()

        if not has_recent_sales:
            cost_price = product.average_purchase_cost or product.purch_price or Decimal('0.00')
            stock_value = product.current_stock_quantity * cost_price
            
            dead_items.append({
                'product': product,
                'stock': product.current_stock_quantity,
                'last_sale_date': last_sale_date,
                'value': stock_value,
            })

    total_dead_value = sum(item['value'] for item in dead_items)

    context = {
        'title': f'تقرير المواد الراكدة (أكثر من {days_threshold} يوم)',
        'dead_items': dead_items,
        'days_threshold': days_threshold,
        'total_dead_value': total_dead_value,
    }
    
    return render(request, 'invoice/reports/dead_stock_report.html', context)

import datetime
from django.contrib.auth.decorators import login_required, permission_required
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from django.shortcuts import render
# تأكد من استيراد الموديلات (Sale, SaleReturn, SaleItem, CashTransaction)

@login_required
@permission_required('invoice.view_report', raise_exception=True)
def profit_report_view(request):
    """تقرير الأرباح والخسائر - مصحح محاسبياً وزمنياً"""
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    context = {
        'start_date': start_date_str,
        'end_date': end_date_str,
        'show_results': False,
    }

    if start_date_str and end_date_str:
        try:
            # تحويل النصوص إلى كائنات تاريخ
            start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            # في حال إدخال تاريخ خاطئ
            return render(request, 'invoice/reports/profit_report.html', context)

        # ==========================================
        # 1. المبيعات والخصومات (بافتراض أن sale_date هو DateField)
        # ==========================================
        sales_qs = Sale.objects.filter(sale_date__range=[start_date, end_date])
        total_sales = sales_qs.aggregate(total=Sum('sale_final_total'))['total'] or Decimal('0.00')
        total_sales_discount = sales_qs.aggregate(total=Sum('sale_discount'))['total'] or Decimal('0.00')
        
        # ==========================================
        # 2. مرتجعات المبيعات
        # ==========================================
        sales_returns_qs = SaleReturn.objects.filter(return_date__range=[start_date, end_date])
        total_sales_returns = sales_returns_qs.aggregate(total=Sum('return_final_total'))['total'] or Decimal('0.00')

        # صافي المبيعات
        net_sales = total_sales - total_sales_discount - total_sales_returns

        # ==========================================
        # 3. تكلفة البضائع المباعة (COGS)
        # ==========================================
        sold_items = SaleItem.objects.filter(sale__in=sales_qs).select_related('product')
        total_cost = Decimal('0.00')
        for item in sold_items:
            cost_price = item.product.average_purchase_cost if item.product and item.product.average_purchase_cost else (item.product.purch_price if item.product else Decimal('0.00'))
            total_cost += (item.sold_quantity * cost_price)
        
        # ==========================================
        # 4. المصاريف التشغيلية والسحوبات (إصلاح مشكلة Timezone)
        # ==========================================
        # تحويل الفترة الزمنية إلى DateTime مدرك للتوقيت
        start_datetime_naive = datetime.datetime.combine(start_date, datetime.time.min)
        end_datetime_naive = datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min)
        
        start_datetime = timezone.make_aware(start_datetime_naive, timezone.get_current_timezone())
        end_datetime = timezone.make_aware(end_datetime_naive, timezone.get_current_timezone())

        operational_expenses_qs = CashTransaction.objects.filter(
            transaction_date__gte=start_datetime,
            transaction_date__lt=end_datetime,
            transaction_type='expense'
        )
        total_expenses = operational_expenses_qs.aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')

        withdrawals_qs = CashTransaction.objects.filter(
            transaction_date__gte=start_datetime,
            transaction_date__lt=end_datetime,
            transaction_type='withdrawal'
        )
        total_withdrawals = withdrawals_qs.aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')

        # ==========================================
        # 5. الحسابات النهائية للأرباح
        # ==========================================
        gross_profit = net_sales - total_cost
        net_operating_profit = gross_profit - total_expenses
        net_profit = net_operating_profit - total_withdrawals

        context.update({
            'total_sales': total_sales,
            'total_sales_discount': total_sales_discount,
            'total_sales_returns': total_sales_returns,
            'net_sales': net_sales,
            'total_cost': total_cost,
            'gross_profit': gross_profit,
            'total_expenses': total_expenses,
            'total_withdrawals': total_withdrawals,
            'net_operating_profit': net_operating_profit,
            'net_profit': net_profit,
            'show_results': True,
        })

    return render(request, 'invoice/reports/profit_report.html', context)


@login_required
@permission_required('invoice.view_report', raise_exception=True)
def sales_by_customer_report(request):
    """تقرير يوضح إجمالي مبيعات كل عميل وعدد الفواتير"""
    search_query = request.GET.get('q', '')

    queryset = Sale.objects.values(
        'sale_customer__id',
        'sale_customer__username',
        'sale_customer__first_name',
        'sale_customer__last_name'
    ).annotate(
        total_amount=Sum('sale_final_total'),
        paid_amount=Sum('paid_amount'),
        invoice_count=Count('id')
    ).order_by('-total_amount')

    if search_query:
        queryset = queryset.filter(
            Q(sale_customer__username__icontains=search_query) |
            Q(sale_customer__first_name__icontains=search_query) |
            Q(sale_customer__last_name__icontains=search_query)
        )

    grand_total = sum(item['total_amount'] or 0 for item in queryset)
    total_invoices = sum(item['invoice_count'] or 0 for item in queryset)

    context = {
        'title': 'تقرير المبيعات حسب العميل',
        'report_data': queryset,
        'grand_total': grand_total,
        'total_invoices': total_invoices,
        'search_query': search_query,
    }
    
    return render(request, 'invoice/reports/sales_by_customer_report.html', context)










@login_required
@permission_required('invoice.view_report', raise_exception=True)
def purchases_by_supplier_report(request):
    """تقرير يوضح إجمالي مشتريات كل مورد وعدد الفواتير"""
    search_query = request.GET.get('q', '')

    queryset = Purch.objects.values(
        'purch_supplier__id',
        'purch_supplier__username',
        'purch_supplier__first_name',
        'purch_supplier__last_name'
    ).annotate(
        total_amount=Sum('purch_final_total'),
        paid_amount=Sum('paid_amount'),
        invoice_count=Count('id')
    ).order_by('-total_amount')

    if search_query:
        queryset = queryset.filter(
            Q(purch_supplier__username__icontains=search_query) |
            Q(purch_supplier__first_name__icontains=search_query) |
            Q(purch_supplier__last_name__icontains=search_query)
        )

    # حساب المجاميع الكلية
    grand_total = sum(item['total_amount'] or 0 for item in queryset)
    grand_paid = sum(item['paid_amount'] or 0 for item in queryset)
    grand_balance = grand_total - grand_paid
    total_invoices = sum(item['invoice_count'] or 0 for item in queryset)
    
    # حساب عدد الموردين الذين لديهم ديون
    suppliers_with_debt = 0
    suppliers_paid = 0

    # إضافة المتبقي لكل صف
    report_data = []
    for item in queryset:
        total = item['total_amount'] or 0
        paid = item['paid_amount'] or 0
        balance = total - paid
        
        if balance > 0:
            suppliers_with_debt += 1
        elif balance == 0:
            suppliers_paid += 1
            
        report_data.append({
            'purch_supplier__id': item['purch_supplier__id'],
            'purch_supplier__username': item['purch_supplier__username'],
            'purch_supplier__first_name': item['purch_supplier__first_name'],
            'purch_supplier__last_name': item['purch_supplier__last_name'],
            'total_amount': total,
            'paid_amount': paid,
            'balance_due': balance,
            'invoice_count': item['invoice_count'],
        })

    context = {
        'title': 'تقرير المشتريات حسب المورد',
        'report_data': report_data,
        'grand_total': grand_total,
        'grand_paid': grand_paid,
        'grand_balance': grand_balance,
        'total_invoices': total_invoices,
        'search_query': search_query,
        'suppliers_with_debt': suppliers_with_debt,      # إضافة
        'suppliers_paid': suppliers_paid,                # إضافة
        'total_suppliers': len(report_data),             # إضافة
    }
    
    return render(request, 'invoice/reports/purchases_by_supplier_report.html', context)



import datetime
from django.contrib.auth.decorators import login_required, permission_required
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from django.shortcuts import render
# تأكد من استيراد الموديلات (Sale, CashTransaction) في أعلى الملف

@login_required
@permission_required('invoice.view_report', raise_exception=True)
def daily_sales_summary_report(request):
    """ملخص مبيعات يومي"""
    today = timezone.now().date()
    selected_date_str = request.GET.get('date')
    
    if selected_date_str:
        try:
            selected_date = timezone.datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
    else:
        selected_date = today

    # 1. المبيعات
    sales_today = Sale.objects.filter(sale_date=selected_date)
    total_sales = sales_today.aggregate(total=Sum('sale_final_total'))['total'] or Decimal('0.00')
    cash_received = sales_today.aggregate(total=Sum('paid_amount'))['total'] or Decimal('0.00')
    invoices_count = sales_today.count()

    # 2. المصروفات (الحل النهائي النظيف)
    start_of_day_naive = datetime.datetime.combine(selected_date, datetime.time.min)
    end_of_day_naive = datetime.datetime.combine(selected_date + datetime.timedelta(days=1), datetime.time.min)
    
    # تحويل الأوقات إلى توقيت مُدرك (Timezone aware) لتجنب تحذيرات جانجو
    start_of_day = timezone.make_aware(start_of_day_naive, timezone.get_current_timezone())
    end_of_day = timezone.make_aware(end_of_day_naive, timezone.get_current_timezone())

    expenses_today = CashTransaction.objects.filter(
        transaction_date__gte=start_of_day,
        transaction_date__lt=end_of_day,
        transaction_type__in=['expense', 'withdrawal']
    )
    total_expenses = expenses_today.aggregate(total=Sum('amount_out'))['total'] or Decimal('0.00')
    
    net_cash = cash_received - total_expenses

    context = {
        'title': 'ملخص المبيعات اليومي',
        'selected_date': selected_date,
        'total_sales': total_sales,
        'cash_received': cash_received,
        'invoices_count': invoices_count,
        'total_expenses': total_expenses,
        'net_cash': net_cash,
    }
    
    return render(request, 'invoice/reports/daily_sales_summary.html', context)


@login_required
@permission_required('invoice.view_report', raise_exception=True)
def unpaid_invoices_report(request):
    """تقرير الفواتير غير المسددة - يعرض الفواتير والمرتجعات كسطور منفصلة"""
    
    from django.db.models import Q, Sum, F, OuterRef, Subquery, Value, DecimalField
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    from django.urls import reverse
    from collections import defaultdict

    all_transactions = []
    total_customers_debt = Decimal('0.00')
    total_suppliers_debt = Decimal('0.00')
    total_sale_returns = Decimal('0.00')
    total_purchase_returns = Decimal('0.00')

    # ==========================================
    # 1. المبيعات غير المسددة (فواتير)
    # ==========================================
    unpaid_sales = Sale.objects.filter(
        Q(balance_due__gt=0) | Q(sale_returns__isnull=False)
    ).distinct().select_related(
        'sale_customer',
        'sale_customer__profile',
        'sale_payment_method',
        'sale_currency'
    ).order_by('-sale_date')

    for sale in unpaid_sales:
        customer_name = "—"
        customer_phone = "—"
        if sale.sale_customer:
            customer_name = sale.sale_customer.get_full_name() or sale.sale_customer.username
            if hasattr(sale.sale_customer, 'profile') and sale.sale_customer.profile:
                customer_phone = sale.sale_customer.profile.phone_number or "—"
        
        # الرصيد المتبقي للفاتورة = (إجمالي الفاتورة - المدفوع)
        # ملاحظة: رصيد الفاتورة يتم حسابه بشكل مستقل عن المرتجعات
        invoice_balance = sale.sale_final_total - sale.paid_amount
        
        all_transactions.append({
            'type': 'sale',
            'type_icon': '📄',
            'type_label': 'فاتورة مبيعات',
            'invoice': sale,
            'return_obj': None,
            'party_name': customer_name,
            'party_phone': customer_phone,
            'date': sale.sale_date,
            'original_total': sale.sale_final_total,
            'paid_amount': sale.paid_amount,
            'balance': invoice_balance,
            'balance_display': f"{invoice_balance:,.2f}",
            'has_returns': sale.sale_returns.exists(),
            'return_amount': None, # لا نضع مبلغ المرتجع هنا لأنه سطر منفصل
            'is_return': False,
            'is_debit': False,
            'url': reverse('invoice:sale_detail', args=[sale.slug]),
            'invoice_number': sale.uniqueId,
            'return_number': None,
            'display_number': sale.uniqueId,
            'original_invoice_number': None,
            'party_type': 'customer',
            'has_return_transactions': sale.sale_returns.exists(),
        })
        
        if invoice_balance > 0:
            total_customers_debt += invoice_balance

    # ==========================================
    # 2. مرتجعات المبيعات (سطر منفصل)
    # ==========================================
    sale_returns = SaleReturn.objects.filter(
        return_final_total__gt=0
    ).select_related(
        'original_sale',
        'original_sale__sale_customer',
        'original_sale__sale_customer__profile',
        'return_payment_method',
        'return_currency'
    ).order_by('-return_date')

    for return_obj in sale_returns:
        customer_name = "—"
        customer_phone = "—"
        if return_obj.original_sale and return_obj.original_sale.sale_customer:
            customer = return_obj.original_sale.sale_customer
            customer_name = customer.get_full_name() or customer.username
            if hasattr(customer, 'profile') and customer.profile:
                customer_phone = customer.profile.phone_number or "—"
        
        # رصيد المرتجع = قيمة المرتجع - المدفوع (قد يكون رصيد دائن أو مدين)
        return_balance = return_obj.return_final_total - return_obj.paid_amount
        
        # إضافة إلى إجمالي المرتجعات
        if return_balance > 0:
            total_sale_returns += return_balance
            
        original_number = return_obj.original_sale.uniqueId if return_obj.original_sale else ""
        # نعرض كل رقم بسطر منفصل في الخلية، لا ندمجهم
        display_number = return_obj.uniqueId
        
        all_transactions.append({
            'type': 'sale_return',
            'type_icon': '🔄',
            'type_label': 'مرتجع مبيعات',
            'invoice': return_obj.original_sale,
            'return_obj': return_obj,
            'party_name': customer_name,
            'party_phone': customer_phone,
            'date': return_obj.return_date,
            'original_total': return_obj.return_final_total,
            'paid_amount': return_obj.paid_amount,
            'balance': return_balance,
            'balance_display': f"{return_balance:,.2f}",
            'has_returns': False,
            'return_amount': return_obj.return_final_total,
            'is_return': True,
            'is_debit': False,
            'url': reverse('invoice:sale_return_detail', args=[return_obj.slug]) if hasattr(return_obj, 'slug') else '#',
            'invoice_number': original_number,
            'return_number': return_obj.uniqueId,
            'display_number': display_number,
            'original_invoice_number': original_number,
            'party_type': 'customer',
            'has_return_transactions': False,
        })

    # ==========================================
    # 3. المشتريات غير المسددة (فواتير)
    # ==========================================
    unpaid_purchases = Purch.objects.filter(
        Q(balance_due__gt=0) | Q(purchase_returns__isnull=False)
    ).distinct().select_related(
        'purch_supplier',
        'purch_supplier__profile',
        'purch_payment_method',
        'purch_currency'
    ).order_by('-purch_date')

    for purch in unpaid_purchases:
        supplier_name = "—"
        supplier_phone = "—"
        if purch.purch_supplier:
            supplier_name = purch.purch_supplier.get_full_name() or purch.purch_supplier.username
            if hasattr(purch.purch_supplier, 'profile') and purch.purch_supplier.profile:
                supplier_phone = purch.purch_supplier.profile.phone_number or "—"
        
        # رصيد فاتورة الشراء بشكل مستقل
        invoice_balance = purch.purch_final_total - purch.paid_amount
        
        all_transactions.append({
            'type': 'purchase',
            'type_icon': '📄',
            'type_label': 'فاتورة مشتريات',
            'invoice': purch,
            'return_obj': None,
            'party_name': supplier_name,
            'party_phone': supplier_phone,
            'date': purch.purch_date,
            'original_total': purch.purch_final_total,
            'paid_amount': purch.paid_amount,
            'balance': invoice_balance,
            'balance_display': f"{invoice_balance:,.2f}",
            'has_returns': purch.purchase_returns.exists(),
            'return_amount': None,
            'is_return': False,
            'is_debit': False,
            'url': reverse('invoice:purch_detail', args=[purch.slug]),
            'invoice_number': purch.uniqueId,
            'return_number': None,
            'display_number': purch.uniqueId,
            'original_invoice_number': None,
            'party_type': 'supplier',
            'has_return_transactions': purch.purchase_returns.exists(),
        })
        
        if invoice_balance > 0:
            total_suppliers_debt += invoice_balance

    # ==========================================
    # 4. مرتجعات المشتريات (سطر منفصل)
    # ==========================================
    purchase_returns = PurchaseReturn.objects.filter(
        return_final_total__gt=0
    ).select_related(
        'original_purchase',
        'original_purchase__purch_supplier',
        'original_purchase__purch_supplier__profile',
        'purch_currency'
    ).order_by('-return_date')

    for return_obj in purchase_returns:
        supplier_name = "—"
        supplier_phone = "—"
        if return_obj.original_purchase and return_obj.original_purchase.purch_supplier:
            supplier = return_obj.original_purchase.purch_supplier
            supplier_name = supplier.get_full_name() or supplier.username
            if hasattr(supplier, 'profile') and supplier.profile:
                supplier_phone = supplier.profile.phone_number or "—"
        
        return_balance = return_obj.return_final_total - return_obj.paid_amount
        
        if return_balance > 0:
            total_purchase_returns += return_balance
            
        original_number = return_obj.original_purchase.uniqueId if return_obj.original_purchase else ""
        display_number = return_obj.uniqueId
        
        all_transactions.append({
            'type': 'purchase_return',
            'type_icon': '🔄',
            'type_label': 'مرتجع مشتريات',
            'invoice': return_obj.original_purchase,
            'return_obj': return_obj,
            'party_name': supplier_name,
            'party_phone': supplier_phone,
            'date': return_obj.return_date,
            'original_total': return_obj.return_final_total,
            'paid_amount': return_obj.paid_amount,
            'balance': return_balance,
            'balance_display': f"{return_balance:,.2f}",
            'has_returns': False,
            'return_amount': return_obj.return_final_total,
            'is_return': True,
            'is_debit': False,
            'url': reverse('invoice:purchase_return_detail', args=[return_obj.slug]) if hasattr(return_obj, 'slug') else '#',
            'invoice_number': original_number,
            'return_number': return_obj.uniqueId,
            'display_number': display_number,
            'original_invoice_number': original_number,
            'party_type': 'supplier',
            'has_return_transactions': False,
        })

    # ==========================================
    # 5. ترتيب المعاملات حسب التاريخ
    # ==========================================
    all_transactions.sort(key=lambda x: x['date'], reverse=True)

    # ==========================================
    # 6. حساب صافي الرصيد والإحصائيات (دون دمج الأرصدة، بل عرض مجاميع)
    # ==========================================
    net_balance = total_customers_debt - total_suppliers_debt
    
    # حساب صافي الديون بعد المرتجعات (للتذييل فقط)
    net_customer_debt = total_customers_debt + total_sale_returns
    net_supplier_debt = total_suppliers_debt + total_purchase_returns
    
    # ==========================================
    # 7. تجميع المعاملات حسب الطرف
    # ==========================================
    party_groups = defaultdict(lambda: {
        'party_name': '',
        'party_type': '',
        'transactions': [],
        'total_balance': Decimal('0.00'),
        'sale_count': 0,
        'purchase_count': 0,
        'return_count': 0,
    })
    
    for transaction in all_transactions:
        party_name = transaction['party_name']
        if party_name == "—":
            party_name = "غير محدد"
        
        group = party_groups[party_name]
        group['party_name'] = party_name
        group['party_type'] = transaction['party_type']
        group['transactions'].append(transaction)
        group['total_balance'] += transaction['balance']
        
        if transaction['type'] in ['sale', 'purchase']:
            if transaction['type'] == 'sale':
                group['sale_count'] += 1
            else:
                group['purchase_count'] += 1
        else:
            group['return_count'] += 1
    
    party_groups_list = []
    for party_name, group_data in party_groups.items():
        group_data['transactions'].sort(key=lambda x: x['date'], reverse=True)
        party_groups_list.append(group_data)
    
    party_groups_list.sort(key=lambda x: abs(x['total_balance']), reverse=True)

    context = {
        'title': 'تقرير الفواتير غير المسددة',
        'transactions': all_transactions,
        'total_customers_debt': total_customers_debt,
        'total_suppliers_debt': total_suppliers_debt,
        'net_balance': net_balance,
        'total_sale_returns': total_sale_returns,
        'total_purchase_returns': total_purchase_returns,
        'net_customer_debt': net_customer_debt,
        'net_supplier_debt': net_supplier_debt,
        'has_transactions': bool(all_transactions),
        'sales_count': len([t for t in all_transactions if t['type'] == 'sale']),
        'purchases_count': len([t for t in all_transactions if t['type'] == 'purchase']),
        'sale_returns_count': len([t for t in all_transactions if t['type'] == 'sale_return']),
        'purchase_returns_count': len([t for t in all_transactions if t['type'] == 'purchase_return']),
        'total_returns_count': len([t for t in all_transactions if t['is_return']]),
        'party_groups': party_groups_list,
        'unique_parties': len(party_groups_list),
        'transactions_with_returns': len([t for t in all_transactions if t.get('has_return_transactions', False)]),
    }
    
    return render(request, 'invoice/reports/unpaid_invoices_report.html', context)



@login_required
@permission_required('invoice.view_report', raise_exception=True)
def dead_stocks_report(request):
    """تقرير المنتجات الراكدة (موجودة ولم يتم بيعها منذ فترة)"""
    days_threshold = int(request.GET.get('days', 60))
    date_threshold = timezone.now().date() - timedelta(days=days_threshold)

    products = Product.objects.filter(current_stock_quantity__gt=0).order_by('product_name')

    dead_items = []

    for product in products:
        last_sale_item = SaleItem.objects.filter(product=product).order_by('-sale__sale_date').first()
        
        last_sale_date = None
        if last_sale_item and last_sale_item.sale:
            last_sale_date = last_sale_item.sale.sale_date
        
        has_recent_sales = SaleItem.objects.filter(
            product=product,
            sale__sale_date__gte=date_threshold
        ).exists()

        if not has_recent_sales:
            dead_items.append({
                'product': product,
                'stock': product.current_stock_quantity,
                'last_sale_date': last_sale_date,
            })

    context = {
        'title': f'تقرير المواد الراكدة (أكثر من {days_threshold} يوم)',
        'dead_items': dead_items,
        'days_threshold': days_threshold,
    }
    
    return render(request, 'invoice/reports/dead_stocks_report.html', context)



# **********************************************************************************
# ==================== القسم الثالث: الإعدادات ================================
# **********************************************************************************

@login_required
@permission_required('invoice.change_emailsetting', raise_exception=True)
def email_settings_view(request):
    """عرض وتعديل إعدادات البريد الإلكتروني"""
    setting = get_email_settings()

    if request.method == 'POST':
        form = EmailSettingForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم حفظ إعدادات البريد الإلكتروني بنجاح.')
            return redirect('invoice:email_settings')
    else:
        form = EmailSettingForm(instance=setting)

    context = {
        'title': 'إعدادات البريد الإلكتروني',
        'form': form,
        'setting': setting,
    }
    return render(request, 'invoice/settings/email_settings.html', context)






# shooping 


# **********************************************************************************
# ==================== القسم الأول: واجهة المتجر (للزبون) ====================
# ==================== لا يحتاج تسجيل دخول أو صلاحيات ========================
# **********************************************************************************




def check_rate_limit(key, max_requests, window_seconds):
    """
    تقييد عدد الطلبات لكل IP في فترة زمنية محددة
    يرجع True إذا مسموح، False إذا تجاوز الحد
    """
    cache_key = f'rate_limit_{key}'
    request_data = cache.get(cache_key, {'count': 0, 'start_time': time.time()})

    now = time.time()
    
    # إذا انتهت نافذة الوقت، نبدأ عداد جديد
    if now - request_data['start_time'] >= window_seconds:
        request_data = {'count': 1, 'start_time': now}
        cache.set(cache_key, request_data, window_seconds)
        return True

    # إذا لم تنتهِ النافذة، نتحقق من العداد
    if request_data['count'] >= max_requests:
        return False

    # زيادة العداد وحفظه
    request_data['count'] += 1
    remaining_time = int(window_seconds - (now - request_data['start_time']))
    cache.set(cache_key, request_data, remaining_time)
    return True


def get_client_ip(request):
    """جلب IP الزائر بشكل آمن"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip or 'unknown'

# ===============================================
#  دوال مساعدة (Helpers)
# ======================================******=========







def get_product_price(product):
    """
    تحديد السعر النهائي للمنتج في المتجر
    1. تبحث في تصنيف المنتج (إذا كان مربوطاً بمستوى تسعير).
    2. إذا لم تجد، ترجع لسعر الجملة.
    """
    if hasattr(product, 'category') and product.category and hasattr(product.category, 'pricing_tier') and product.category.pricing_tier:
        tier_id = product.category.pricing_tier.id
        try:
            tier_price = ProductPriceTier.objects.get(product=product, tier_id=tier_id)
            if tier_price.price and tier_price.price > 0:
                return tier_price.price
        except ProductPriceTier.DoesNotExist:
            pass

    return product.wholesale_price or Decimal('0.00')


def prepare_product_data(product, setting=None):
    """تجهيز بيانات المنتج للعرض في لوحة التحكم"""
    if setting is None:
        from .models import ProductStoreSetting
        setting, _ = ProductStoreSetting.objects.get_or_create(product=product)
    
    final_price = get_product_price(product)
    
    # استخدام الدالة الموجودة get_product_image_url
    product_image_url = get_product_image_url(product)
    
    # استخراج badge_url بأمان
    badge_url = ""
    if hasattr(setting, 'badge_image') and setting.badge_image:
        try:
            badge_url = setting.badge_image.url
        except Exception:
            badge_url = ""
    
    show_old_price = False
    if product.wholesale_price:
        show_old_price = (final_price < product.wholesale_price)
    
    return {
        'id': product.id,
        'name': product.product_name,
        'image': product_image_url,
        'price_old': f"{product.wholesale_price:.2f}" if product.wholesale_price else "0.00",
        'price_new': f"{final_price:.2f}",
        'store_section': setting.store_section,
        'display_order': setting.display_order,
        'is_visible': setting.is_visible,
        'badge_url': badge_url,
        'show_old_price': show_old_price,
        'category_id': product.category_id if product.category_id else None,
    }


def get_product_image_url(product):
    """جلب رابط صورة المنتج بأمان"""
    if product.product_image:
        try:
            return product.product_image.url
        except Exception as e:
            logger.warning(f"خطأ في جلب رابط صورة المنتج {product.id}: {e}")
    return "/static/images/no-image.png"



def get_or_create_cart(request):
    """جلب سلة التسوق الحالية أو إنشاء جديدة مع دمج سلة الزائر عند تسجيل الدخول"""
    user = request.user if request.user.is_authenticated else None
    session_key = request.session.session_key
    
    if not session_key:
        request.session.create()
        session_key = request.session.session_key

    if user:
        # جلب أو إنشاء سلة المستخدم
        cart, created = Cart.objects.get_or_create(user=user)
        
        # دمج سلة الزائر مع سلة المستخدم عند تسجيل الدخول
        if not created:
            guest_cart = Cart.objects.filter(session_key=session_key, user__isnull=True).first()
            if guest_cart:
                # دمج العناصر
                for guest_item in guest_cart.items.all():
                    cart_item, item_created = CartItem.objects.get_or_create(
                        cart=cart, 
                        product=guest_item.product,
                        defaults={'quantity': guest_item.quantity}
                    )
                    if not item_created:
                        # جمع الكميات إذا كان المنتج موجوداً بالفعل
                        cart_item.quantity += guest_item.quantity
                        cart_item.save()
                
                # حذف سلة الزائر بعد الدمج
                guest_cart.delete()
    else:
        # سلة الزائر
        cart, _ = Cart.objects.get_or_create(session_key=session_key, user__isnull=True)

    return cart


def prepare_section_data(section):
    """تجهيز بيانات القسم الديناميكي للعرض في لوحة التحكم"""
    items_data = []
    
    for item in section.items.select_related('product').all():
        product = item.product
        if not product:
            continue
        
        try:
            final_price = get_product_price(product)
            wholesale_price = product.wholesale_price if product.wholesale_price else 0
            
            # استخدام الدالة الموجودة get_product_image_url
            product_image = get_product_image_url(product)
            
            items_data.append({
                'item_id': item.id,
                'name': product.product_name,
                'image': product_image,
                'price': f"{final_price:.2f}",
                'old_price': f"{wholesale_price:.2f}" if wholesale_price > 0 else None,
                'show_old_price': (final_price < wholesale_price) if wholesale_price > 0 else False
            })
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error preparing item {item.id} in section {section.id}: {e}")
            continue
    
    return {
        'id': section.id,
        'name': section.name,
        'style_type': section.style_type,
        'is_active': section.is_active,
        'category_id': section.category_id,
        'category_name': section.category.name if section.category else None,
        'display_order': section.display_order,
        'items': items_data,
    }


#================================================
#           إدارة تصنيفات المتجر               #
# ===============================================


@login_required
@permission_required('invoice.view_category', raise_exception=True)
def manage_categories(request):
    """صفحة إدارة تصنيفات المتجر"""
    categories = Category.objects.all().select_related('pricing_tier').order_by('display_order')
    tiers = PricingTier.objects.all()
    return render(request, 'invoice/store/manage_categories.html', {
        'categories': categories,
        'tiers': tiers,
        'title': 'إدارة تصنيفات المتجر'
    })


@login_required
@permission_required('invoice.add_category', raise_exception=True)
@require_POST
def api_add_category(request):
    """إنشاء تصنيف جديد"""
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'success': False, 'message': 'اسم التصنيف مطلوب'}, status=400)
        
        category = Category.objects.create(
            name=name,
            pricing_tier_id=data.get('tier_id') or None,
            display_order=Category.objects.count()
        )
        return JsonResponse({'success': True, 'message': 'تم إنشاء التصنيف'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء إنشاء التصنيف'}, status=500)


@login_required
@permission_required('invoice.change_category', raise_exception=True)
@require_POST
def api_update_category(request, cat_id):
    """تحديث بيانات التصنيف"""
    try:
        data = json.loads(request.body)
        category = get_object_or_404(Category, id=cat_id)
        category.name = data.get('name', category.name)
        category.pricing_tier_id = data.get('tier_id') or None
        category.is_active = data.get('is_active', category.is_active)
        category.save()
        return JsonResponse({'success': True, 'message': 'تم التحديث'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء تحديث التصنيف'}, status=500)


@login_required
@permission_required('invoice.delete_category', raise_exception=True)
@require_POST
def api_delete_category(request, cat_id):
    """حذف تصنيف"""
    try:
        get_object_or_404(Category, id=cat_id).delete()
        return JsonResponse({'success': True, 'message': 'تم الحذف'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء حذف التصنيف'}, status=500)



@login_required
@permission_required('invoice.view_product', raise_exception=True)
def get_product_details(request, product_id):
    """الحصول على تفاصيل المنتج"""
    try:
        product = Product.objects.get(id=product_id)
        data = {
            'product_name': product.product_name,
            'purch_price': str(product.purch_price),
            'sale_price': str(product.sale_price),
            'current_stock': str(product.current_stock_quantity),
        }
        return JsonResponse(data)
    except Product.DoesNotExist:
        return JsonResponse({'error': _('المنتج غير موجود')}, status=404)





# ===============================================
#  واجهة المتجر (للزبون) - النسخة المحسنة
# =======================================*****========

def store_front(request):
    """عرض واجهة المتجر الرئيسية - تدعم الفلاش المقسم تلقائياً"""
    from django.db.models import Q, Prefetch, F
    
    cart = get_or_create_cart(request)
    
    # ==========================================
    # 1. الأقسام الديناميكية (تم تطبيق الفلترة والترتيب على مستوى قاعدة البيانات)
    # ==========================================
    # نجلب فقط العناصر التي تملك منتجات ظاهرة، ونرتبها مباشرة
    visible_items_qs = ProductSectionItem.objects.filter(
        Q(product__store_setting__isnull=True) | 
        Q(product__store_setting__is_visible=True)
    ).select_related(
        'product__store_setting', 'product__category__pricing_tier'
    ).order_by(
        F('product__store_setting__display_order').asc(nulls_last=True), 
        'display_order'
    )

    dynamic_sections = StoreSection.objects.filter(is_active=True).prefetch_related(
        Prefetch('items', queryset=visible_items_qs)
    ).order_by('display_order')

    sections_data = []
    for section in dynamic_sections:
        section_items = []
        for item in section.items.all():
            # بما أننا فلترنا في قاعدة البيانات، العناصر المخفية لن تأتي أصلاً
            product = item.product
            if not product:
                continue

            price = get_product_price(product)
            show_old_price = (price < product.wholesale_price) and item.show_old_price

            # جلب رابط شارة المنتج (Badge)
            product_badge_url = ""
            if hasattr(product, 'store_setting') and product.store_setting and product.store_setting.badge_image:
                try:
                    product_badge_url = product.store_setting.badge_image.url
                except Exception:
                    product_badge_url = ""

            section_items.append({
                'id': product.id,
                'name': product.product_name,
                'image': get_product_image_url(product),
                'price_new': f"{price:.2f}",
                'price_old': f"{product.wholesale_price:.2f}" if show_old_price else "",
                'stock': int(product.current_stock_quantity),
                'show_old_price': show_old_price,
                'custom_badge': item.custom_badge.url if item.custom_badge else None,
                'product_badge_url': product_badge_url,
                'display_order': product.store_setting.display_order if hasattr(product, 'store_setting') and product.store_setting else 0,
                'item_display_order': item.display_order,
                'category_id': product.category_id,
                'category_name': product.category.name if product.category else "",
            })

        sections_data.append({
            'id': section.id,
            'name': section.name,
            'style_type': section.style_type,
            'category_id': section.category_id,
            'is_offers_style': section.is_offers_style,
            'items': section_items
        })

    # ==========================================
    # 2. التصنيفات
    # ==========================================
    categories = Category.objects.filter(is_active=True).order_by('display_order')
    categories_data = []
    for cat in categories:
        # جلب المنتجات الظاهرة فقط وترتيبها في قاعدة البيانات مباشرة
        visible_products = Product.objects.filter(
            category=cat
        ).filter(
            Q(store_setting__isnull=True) | Q(store_setting__is_visible=True)
        ).select_related('store_setting').order_by(
            F('store_setting__display_order').asc(nulls_last=True), 'id'
        )
        
        prods = []
        for p in visible_products:
            price = get_product_price(p)
            
            badge_url = ""
            if hasattr(p, 'store_setting') and p.store_setting and p.store_setting.badge_image:
                try:
                    badge_url = p.store_setting.badge_image.url
                except Exception:
                    badge_url = ""
            
            prods.append({
                'id': p.id,
                'name': p.product_name,
                'image': get_product_image_url(p),
                'price_new': f"{price:.2f}",
                'price_old': f"{p.wholesale_price:.2f}" if price < p.wholesale_price else "",
                'stock': int(p.current_stock_quantity),
                'badge_url': badge_url,
            })
        categories_data.append({
            'id': cat.id,
            'name': cat.name,
            'icon': cat.icon.url if cat.icon else None,
            'products': prods,
        })

    # ==========================================
    # 3. إحصائيات المتجر
    # ==========================================
    store_stats = {
        'total_products': Product.objects.filter(
            Q(store_setting__isnull=True) | Q(store_setting__is_visible=True)
        ).count(),
        'total_orders': WebsiteOrder.objects.count(),
        'total_categories': categories.count(),
    }

    # ==========================================
    # 4. الطلبات الحديثة
    # ==========================================
    recent_orders_data = []
    for order in WebsiteOrder.objects.prefetch_related('items').order_by('-order_date')[:20]:
        first_item = order.items.first()
        name = order.full_name.split()[0] if order.full_name else 'عميل'
        try:
            name = name.encode('ascii', 'ignore').decode('ascii').strip()
            if len(name) < 2: name = 'عميل'
        except: name = 'عميل'
        
        product = 'منتج'
        if first_item:
            try:
                product = first_item.product_name.encode('ascii', 'ignore').decode('ascii').strip()
                if len(product) < 2: product = 'منتج'
            except: product = 'منتج'
        
        recent_orders_data.append({
            'name': name,
            'product': product,
            'time': order.order_date.strftime('%Y-%m-%d %H:%M'),
        })

    # ==========================================
    # 5. عتبة المخزون المنخفض
    # ==========================================
    LOW_STOCK_THRESHOLD = 5

    # ==========================================
    # 6. منطق الفلاش الذكي (مقسم أو فردي)
    # ==========================================
    active_flash_deals = FlashDeal.objects.filter(is_active=True).select_related('product__store_setting')[:3]
    
    flashes_data = []
    for deal in active_flash_deals:
        if not deal.is_currently_active():
            continue
        p = deal.product
        
        if hasattr(p, 'store_setting') and p.store_setting and not p.store_setting.is_visible:
            continue
            
        price = get_product_price(p)
        flashes_data.append({
            'id': deal.id,
            'product_id': p.id,
            'product_name': p.product_name,
            'product_image': get_product_image_url(p),
            'original_price': f"{price:.2f}",
            'deal_price': f"{deal.deal_price:.2f}",
            'max_quantity': deal.max_quantity,
            'remaining': deal.remaining_quantity(),
            'percentage': deal.remaining_percentage(),
            'ends_at': deal.ends_at.isoformat(),
            'stock': int(p.current_stock_quantity),
        })

    # ==========================================
    # 7. الشريط العلوي والأيقونات
    # ==========================================
    top_announcements = StoreAnnouncement.objects.filter(is_active=True).order_by('order')
    store_features = StoreFeatureIcon.objects.filter(is_active=True).order_by('order')

    # ==========================================
    # تجميع السياق (Context)
    # ==========================================
    context = {
        'cart_count': cart.items.count(),
        'dynamic_sections': dynamic_sections, # هذا الكائن الآن مفلتر ومرتب بشكل صحيح
        'sections_data': sections_data,
        'top_banners': StoreBanner.objects.filter(is_active=True, position='top').order_by('order'),
        'side_banners': StoreBanner.objects.filter(is_active=True, position='side').order_by('order'),
        'categories': categories,
        'categories_json': categories_data,
        'sections_json': sections_data,
        'store_stats': store_stats,
        'recent_orders_json': recent_orders_data,
        'low_stock_threshold': LOW_STOCK_THRESHOLD,
        'flashes_data': flashes_data,
        'announcements': top_announcements,
        'store_features': store_features,
        'flash_deals_url': '/invoice/api/flash-deals/',
    }
    return render(request, 'invoice/store/store.html', context)

# ===============================================
#  سلة التسوق (API & Pages)
# ===============================================



def add_to_cart(request):
    """إضافة منتج للسلة (AJAX) - نسخة محسنة"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=400)
    
    # تقييد: 30 طلب/دقيقة لكل IP
    if not check_rate_limit(f'cart_add_{get_client_ip(request)}', 30, 60):
        return JsonResponse({
            'success': False, 
            'message': 'طلبات كثيرة جداً، انتظر قليلاً'
        }, status=429)
    
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        quantity = int(data.get('quantity', 1))
        
        if not product_id:
            return JsonResponse({
                'success': False, 
                'message': 'معرف المنتج مطلوب'
            }, status=400)
        
        product = get_object_or_404(Product, id=product_id)
        cart = get_or_create_cart(request)
        
        # التحقق من المخزون
        if product.current_stock_quantity < quantity:
            return JsonResponse({
                'success': False,
                'message': f'الكمية المطلوبة غير متوفرة. المتاح: {product.current_stock_quantity}'
            }, status=400)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, 
            product=product,
            defaults={'quantity': quantity}
        )
        
        if not created:
            new_quantity = cart_item.quantity + quantity
            if product.current_stock_quantity < new_quantity:
                return JsonResponse({
                    'success': False,
                    'message': f'الكمية الإجمالية غير متوفرة. المتاح: {product.current_stock_quantity}'
                }, status=400)
            cart_item.quantity = new_quantity
            cart_item.save()
        
        # حساب الإجمالي الجديد
        total = cart.total_price
        
        return JsonResponse({
            'success': True,
            'message': 'تمت الإضافة للسلة' if created else 'تم تحديث الكمية',
            'cart_count': cart.total_items_count,
            'cart_total': float(total)
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False, 
            'message': 'بيانات غير صالحة'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in add_to_cart: {e}")
        return JsonResponse({
            'success': False, 
            'message': 'حدث خطأ أثناء الإضافة للسلة'
        }, status=500)


def update_cart_item(request):
    """تعديل كمية منتج في السلة (AJAX) - نسخة محسنة"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=400)
    
    try:
        data = json.loads(request.body)
        item_id = data.get('item_id')
        quantity = int(data.get('quantity', 1))
        
        if not item_id:
            return JsonResponse({
                'success': False, 
                'message': 'معرف العنصر مطلوب'
            }, status=400)
        
        cart = get_or_create_cart(request)
        cart_item = get_object_or_404(CartItem, id=item_id)
        
        # التحقق من الملكية
        if cart_item.cart != cart:
            return JsonResponse({
                'success': False, 
                'message': 'غير مصرح'
            }, status=403)
        
        if quantity <= 0:
            # حذف العنصر إذا كانت الكمية 0 أو أقل
            cart_item.delete()
            message = 'تم حذف المنتج'
        else:
            # التحقق من المخزون
            if cart_item.product.current_stock_quantity < quantity:
                return JsonResponse({
                    'success': False,
                    'message': f'الكمية المطلوبة غير متوفرة. المتاح: {cart_item.product.current_stock_quantity}'
                }, status=400)
            
            cart_item.quantity = quantity
            cart_item.save()
            message = 'تم تحديث الكمية'
        
        # حساب الإجمالي الجديد
        total = cart.total_price
        
        return JsonResponse({
            'success': True,
            'message': message,
            'new_total': float(total),
            'cart_count': cart.total_items_count
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False, 
            'message': 'بيانات غير صالحة'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in update_cart_item: {e}")
        return JsonResponse({
            'success': False, 
            'message': 'حدث خطأ أثناء تحديث السلة'
        }, status=500)


def remove_from_cart(request):
    """حذف منتج من السلة (AJAX) - نسخة محسنة"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=400)
    
    try:
        data = json.loads(request.body)
        item_id = data.get('item_id')
        
        if not item_id:
            return JsonResponse({
                'success': False, 
                'message': 'معرف العنصر مطلوب'
            }, status=400)
        
        cart = get_or_create_cart(request)
        cart_item = get_object_or_404(CartItem, id=item_id)
        
        # التحقق من الملكية
        if cart_item.cart != cart:
            return JsonResponse({
                'success': False, 
                'message': 'غير مصرح'
            }, status=403)
        
        # حذف العنصر
        cart_item.delete()
        
        # حساب الإجمالي الجديد
        total = cart.total_price
        
        return JsonResponse({
            'success': True,
            'message': 'تم حذف المنتج',
            'new_total': float(total),
            'cart_count': cart.total_items_count
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False, 
            'message': 'بيانات غير صالحة'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in remove_from_cart: {e}")
        return JsonResponse({
            'success': False, 
            'message': 'حدث خطأ أثناء حذف المنتج'
        }, status=500)


def cart_detail(request):
    """عرض صفحة السلة - نسخة محسنة"""
    cart = get_or_create_cart(request)
    
    # حساب الإجمالي
    total = cart.total_price
    
    context = {
        'cart': cart,
        'cart_items': cart.items.select_related('product').all(),
        'cart_total': total,
        'cart_count': cart.total_items_count,
        'title': 'سلة التسوق'
    }
    
    return render(request, 'invoice/store/order.html', context)


def checkout_view(request):
    """صفحة إتمام الشراء - نسخة محسنة"""
    cart = get_or_create_cart(request)
    
    if cart.total_items_count == 0:
        messages.warning(request, 'سلة التسوق فارغة')
        return redirect('invoice:store_front')
    
    return render(request, 'invoice/store/checkout.html', {
        'cart': cart,
        'cart_items': cart.items.select_related('product').all(),
        'cart_total': cart.total_price,
        'title': 'إتمام الشراء'
    })


def update_cart_item(request):
    """تعديل كمية منتج في السلة (AJAX)"""
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=400)
    
    try:
        data = json.loads(request.body)
        cart = get_or_create_cart(request)
        cart_item = get_object_or_404(CartItem, id=data.get('item_id'))
        
        if cart_item.cart != cart:
            return JsonResponse({'success': False, 'message': 'غير مصرح'}, status=403)
        
        quantity = int(data.get('quantity', 1))
        if quantity > 0:
            cart_item.quantity = quantity
            cart_item.save()
            message = 'تم تحديث الكمية'
        else:
            cart_item.delete()
            message = 'تم حذف المنتج'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'new_total': float(cart.total_price),
            'cart_count': cart.items.count()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء تحديث السلة'}, status=400)


def remove_from_cart(request):
    """حذف منتج من السلة (AJAX)"""
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=400)
    
    try:
        data = json.loads(request.body)
        cart = get_or_create_cart(request)
        cart_item = get_object_or_404(CartItem, id=data.get('item_id'))
        
        if cart_item.cart != cart:
            return JsonResponse({'success': False, 'message': 'غير مصرح'}, status=403)
        
        cart_item.delete()
        return JsonResponse({
            'success': True,
            'message': 'تم الحذف',
            'new_total': float(cart.total_price),
            'cart_count': cart.items.count()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء الحذف'}, status=400)


def cart_detail(request):
    """عرض صفحة السلة"""
    cart = get_or_create_cart(request)
    return render(request, 'invoice/store/order.html', {
        'cart': cart,
        'cart_items': cart.items.select_related('product').all(),
        'title': 'سلة التسوق'
    })


def checkout_view(request):
    """صفحة إتمام الشراء"""
    cart = get_or_create_cart(request)
    if cart.items.count() == 0:
        return redirect('invoice:store_front')
    return render(request, 'invoice/store/checkout.html', {'cart': cart, 'title': 'إتمام الشراء'})



def place_order_view(request):
    """تأكيد الطلب وإنشاءه في قاعدة البيانات"""
    
    # ===== التحقق من الطريقة =====
    if request.method != 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'}, status=405)
        return redirect('invoice:checkout')
    
    cart = get_or_create_cart(request)
    
    # ===== التحقق من السلة =====
    if cart.items.count() == 0:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'السلة فارغة'}, status=400)
        messages.warning(request, 'السلة فارغة')
        return redirect('invoice:cart_detail')

    # ===== تقييد الطلبات =====
    if not check_rate_limit(f'order_place_{get_client_ip(request)}', 5, 60):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False, 
                'message': 'طلبات كثيرة جداً، انتظر دقيقة ثم حاول'
            }, status=429)
        messages.error(request, 'طلبات كثيرة جداً، انتظر دقيقة ثم حاول')
        return redirect('invoice:checkout')

    # ===== استخراج البيانات =====
    full_name = request.POST.get('full_name', '').strip()
    phone = request.POST.get('phone', '').strip()
    address = request.POST.get('address', '').strip()
    notes = request.POST.get('notes', '').strip()

    # ===== التحقق من البيانات =====
    
    # 1. التحقق من الاسم
    if not full_name:
        return JsonResponse({'success': False, 'message': 'الاسم الكامل مطلوب'}, status=400)
    if len(full_name) < 3:
        return JsonResponse({'success': False, 'message': 'الاسم لا يقل عن 3 أحرف'}, status=400)
    if len(full_name) > 100:
        return JsonResponse({'success': False, 'message': 'الاسم طويل جداً (الحد الأقصى 100 حرف)'}, status=400)
    if not re.match(r'^[\u0600-\u06FFa-zA-Z\s]+$', full_name):
        return JsonResponse({'success': False, 'message': 'الاسم يجب أن يحتوي على حروف فقط'}, status=400)

    # 2. التحقق من الهاتف
    if not phone:
        return JsonResponse({'success': False, 'message': 'رقم الهاتف مطلوب'}, status=400)
    phone_clean = re.sub(r'[\s\-\+\(\)]', '', phone)
    if not re.match(r'^[0-9]+$', phone_clean):
        return JsonResponse({'success': False, 'message': 'رقم الهاتف يجب أن يحتوي على أرقام فقط'}, status=400)
    if len(phone_clean) < 7:
        return JsonResponse({'success': False, 'message': 'رقم الهاتف قصير جداً (7 أرقام على الأقل)'}, status=400)
    if len(phone_clean) > 15:
        return JsonResponse({'success': False, 'message': 'رقم الهاتف طويل جداً (الحد الأقصى 15 رقم)'}, status=400)

    # 3. التحقق من العنوان
    if not address:
        return JsonResponse({'success': False, 'message': 'عنوان الشحن مطلوب'}, status=400)
    if len(address) < 5:
        return JsonResponse({
            'success': False, 
            'message': 'عنوان الشحن قصير جداً (5 أحرف على الأقل)'
        }, status=400)
    if len(address) > 500:
        return JsonResponse({'success': False, 'message': 'العنوان طويل جداً (الحد الأقصى 500 حرف)'}, status=400)

    # 4. التحقق من الملاحظات
    if len(notes) > 1000:
        return JsonResponse({'success': False, 'message': 'الملاحظات طويلة جداً (الحد الأقصى 1000 حرف)'}, status=400)

    # ===== معالجة الطلب =====
    try:
        with transaction.atomic():
            # التحقق من المخزون
            product_ids = cart.items.values_list('product_id', flat=True)
            products = Product.objects.select_for_update().filter(id__in=product_ids)
            product_map = {p.id: p for p in products}
            
            for item in cart.items.all():
                product = product_map.get(item.product.id)
                if not product:
                    return JsonResponse({
                        'success': False, 
                        'message': f'المنتج "{item.product.product_name}" غير موجود'
                    }, status=400)
                if product.current_stock_quantity < item.quantity:
                    return JsonResponse({
                        'success': False,
                        'message': f'المنتج "{product.product_name}" غير متوفر بالكمية المطلوبة. المتاح: {product.current_stock_quantity}'
                    }, status=400)

            # إنشاء الطلب
            order = WebsiteOrder.objects.create(
                user=request.user if request.user.is_authenticated else None,
                full_name=full_name,
                phone=phone_clean,
                address=address,
                notes=notes,
                total_amount=cart.total_price,
                status='new'
            )

            # إنشاء عناصر الطلب
            for item in cart.items.all():
                WebsiteOrderItem.objects.create(
                    order=order,
                    product=item.product,
                    product_name=item.product.product_name,
                    price=get_product_price(item.product),
                    quantity=item.quantity
                )
                # خصم المخزون
                item.product.current_stock_quantity = F('current_stock_quantity') - item.quantity
                item.product.save(update_fields=['current_stock_quantity'])

            # تفريغ السلة
            cart.items.all().delete()
            
            # ===== التوجيه لصفحة التأكيد =====
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'تم استلام طلبك! رقم الطلب: #{order.id}',
                    'order_id': order.id,
                    'redirect_url': reverse('invoice:order_confirmation', kwargs={'order_id': order.id})
                })
            
            messages.success(request, f'تم استلام طلبك! رقم الطلب: #{order.id}')
            return redirect('invoice:order_confirmation', order_id=order.id)
            
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False, 
                'message': 'حدث خطأ أثناء معالجة الطلب، يرجى المحاولة مرة أخرى.'
            }, status=500)
        
        messages.error(request, 'حدث خطأ أثناء معالجة الطلب، يرجى المحاولة مرة أخرى.')
        return redirect('invoice:checkout')


@login_required(login_url='accounts:login')
def order_confirmation(request, order_id):
    """صفحة تأكيد الطلب بعد الشراء"""
    order = get_object_or_404(WebsiteOrder, id=order_id)
    
    # التحقق من أن المستخدم هو صاحب الطلب أو مدير
    if order.user and order.user != request.user and not request.user.is_staff:
        messages.error(request, 'غير مصرح لك بعرض هذا الطلب')
        return redirect('invoice:store_front')
    
    context = {
        'order': order,
        'title': f'تأكيد الطلب #{order.id}'
    }
    
    return render(request, 'invoice/store/order_confirmation.html', context)


# ===============================================
#  API: طلب إشعار (من الواجهة)
# ===============================================


def api_request_notification(request):
    """حفظ طلب الإشعار عند نفاد المخزون"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid Request'}, status=405)
    
    # ★ تقييد: 3 طلبات/دقيقة لكل IP + لكل بريد
    client_ip = get_client_ip(request)
    if not check_rate_limit(f'notify_ip_{client_ip}', 3, 60):
        return JsonResponse({'success': False, 'message': 'طلبات كثيرة جداً، انتظر قليلاً'}, status=429)
    
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        email = data.get('email')
        
        if not product_id or not email:
            return JsonResponse({'success': False, 'message': 'البيانات ناقصة'}, status=400)

        # ★ تقييد إضافي: 3 طلبات/دقيقة لكل بريد إلكتروني (منع spam)
        if not check_rate_limit(f'notify_email_{email}', 3, 60):
            return JsonResponse({'success': False, 'message': 'طلبات كثيرة جداً على هذا البريد'}, status=429)

        product = get_object_or_404(Product, id=product_id)

        if product.current_stock_quantity > 0:
            return JsonResponse({'success': False, 'message': 'المنتج متوفر الآن!'})

        notification, created = StockNotification.objects.get_or_create(
            product=product,
            email=email
        )
        
        if created:
            msg = 'تم تسجيل طلبك! سنخبرك فور توفر المادة.'
        else:
            msg = 'أنت مسجل مسبقاً في قائمة الانتظار لهذا المنتج.'
            
        return JsonResponse({'success': True, 'message': msg})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء التسجيل'}, status=500)


# **********************************************************************************
# ==================== القسم الثاني: لوحة تحكم المدير ========================
# ==================== يتطلب تسجيل دخول وصلاحيات دقيقة =====================
# ****************************************************************************************




@login_required
@permission_required('invoice.change_productstoresetting', raise_exception=True)
def control_store(request):
    """لوحة تحكم المتجر الإلكتروني"""
    logger = logging.getLogger(__name__)
    
    # 1. البنرات
    try:
        banners = StoreBanner.objects.all().order_by('order', '-created_at')
    except Exception as e:
        logger.error(f"Error loading banners: {e}")
        banners = []
    
    # 2. المنتجات
    try:
        products = Product.objects.all().order_by('-date_created')
        products_data = []
        for p in products:
            try:
                products_data.append(prepare_product_data(p))
            except Exception as e:
                logger.warning(f"Error preparing product {p.id}: {e}")
                continue
    except Exception as e:
        logger.error(f"Error loading products: {e}")
        products_data = []
    
    # 3. الأقسام
    try:
        sections = StoreSection.objects.all().prefetch_related(
            'items__product'
        ).order_by('display_order')
        sections_list = []
        for sec in sections:
            try:
                sections_list.append(prepare_section_data(sec))
            except Exception as e:
                logger.warning(f"Error preparing section {sec.id}: {e}")
                continue
    except Exception as e:
        logger.error(f"Error loading sections: {e}")
        sections_list = []
    
    # 4. التصنيفات
    try:
        categories = Category.objects.all().order_by('display_order')
    except Exception as e:
        logger.error(f"Error loading categories: {e}")
        categories = []
    
    # 5. الإعلانات
    try:
        announcements = StoreAnnouncement.objects.all().order_by('order')
    except Exception as e:
        logger.error(f"Error loading announcements: {e}")
        announcements = []
    
    # 6. الأيقونات المميزة
    try:
        features = StoreFeatureIcon.objects.all().order_by('order')
    except Exception as e:
        logger.error(f"Error loading features: {e}")
        features = []
    
    # 7. عروض الفلاش
    try:
        flash_deals = FlashDeal.objects.all()
    except Exception as e:
        logger.error(f"Error loading flash deals: {e}")
        flash_deals = []
    
    context = {
        'banners': banners,
        'products_data': products_data,
        'sections_list': sections_list,
        'categories': categories,
        'flash_deals_url': '/invoice/api/flash-deals/',
        'announcements_list': announcements,
        'features_list': features,
        'available_flash_deals': flash_deals,
    }
    
    return render(request, 'invoice/store/control_store.html', context)



# ===============================================
#  API: إعدادات المنتجات
# ===============================================

@login_required
@permission_required('invoice.change_productstoresetting', raise_exception=True)
@require_POST
def api_update_badge_image(request, product_id):
    """تحديث صورة الشعار للمنتج"""
    try:
        product = get_object_or_404(Product, id=product_id)
        settings_obj, _ = ProductStoreSetting.objects.get_or_create(product=product)
        
        if 'badge_image' in request.FILES:
            settings_obj.badge_image = request.FILES['badge_image']
            settings_obj.save()
            return JsonResponse({'success': True, 'image_url': settings_obj.badge_image.url})
        return JsonResponse({'success': False, 'message': 'لم يتم إرسال صورة'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء رفع الصورة'}, status=500)


@login_required
@permission_required('invoice.change_productstoresetting', raise_exception=True)
@require_POST
def api_update_product_store_settings(request, product_id):
    """تحديث إعدادات المتجر للمنتج (الظهور، القسم، الترتيب)"""
    try:
        product = get_object_or_404(Product, id=product_id)
        data = json.loads(request.body)
        field_name, value = data.get('field'), data.get('value')
        
        settings_obj, _ = ProductStoreSetting.objects.get_or_create(product=product)
        
        allowed_fields = ['is_visible', 'store_section', 'show_old_price', 'display_order']
        if field_name in allowed_fields:
            if field_name in ['is_visible', 'show_old_price']:
                value = str(value).lower() in ['true', '1', 'yes']
            elif field_name == 'display_order':
                value = int(value or 0)
            setattr(settings_obj, field_name, value)
            settings_obj.save()
            return JsonResponse({'success': True, 'new_value': value})
        return JsonResponse({'success': False, 'message': 'حقل غير مسموح'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء التحديث'}, status=500)


# ===============================================
#  API: البنرات الإعلانية
# ===============================================

@login_required
@permission_required('invoice.add_storebanner', raise_exception=True)
@require_POST
def api_add_banner(request):
    """إضافة بنر جديد"""
    try:
        image = request.FILES.get('image')
        if not image:
            return JsonResponse({'success': False, 'message': 'الصورة مطلوبة'}, status=400)

        banner = StoreBanner.objects.create(
            title=request.POST.get('title') or image.name.rsplit('.', 1)[0],
            image=image,
            link_url=request.POST.get('link_url') or None,
            position=request.POST.get('position', 'top'),
            order=int(request.POST.get('order', 0)),
            is_active=request.POST.get('is_active') == 'true'
        )
        return JsonResponse({'success': True, 'banner_id': banner.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء إضافة البنر'}, status=500)


@login_required
@permission_required('invoice.change_storebanner', raise_exception=True)
@require_POST
def api_update_banner(request, banner_id):
    """تحديث بنر"""
    try:
        banner = get_object_or_404(StoreBanner, id=banner_id)
        banner.title = request.POST.get('title')
        banner.link_url = request.POST.get('link_url')
        banner.position = request.POST.get('position')
        banner.order = int(request.POST.get('order', 0))
        banner.is_active = request.POST.get('is_active') == 'true'
        
        if 'image' in request.FILES:
            banner.image = request.FILES['image']
        banner.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء تحديث البنر'}, status=500)


@login_required
@permission_required('invoice.delete_storebanner', raise_exception=True)
def delete_banner(request, banner_id):
    """حذف بنر"""
    get_object_or_404(StoreBanner, id=banner_id).delete()
    messages.success(request, 'تم حذف البنر بنجاح')
    return redirect('invoice:control_store')


# ===============================================
#  API: الأقسام الديناميكية
# ===============================================

@login_required
@permission_required('invoice.add_storesection', raise_exception=True)
@require_POST
def api_add_section(request):
    """إنشاء قسم جديد — يدعم الربط بتصنيف"""
    try:
        data = json.loads(request.body)
        category_id = data.get('category_id')
        
        # التحقق: إذا لم يختر تصنيفاً، يجب أن يكتب اسم القسم
        if not category_id and not data.get('name'):
            return JsonResponse({'success': False, 'message': 'اختر تصنيفاً أو اكتب اسم القسم'}, status=400)
        
        section = StoreSection.objects.create(
            name=data.get('name', ''),
            style_type=data.get('style_type', 'grid'),
            display_order=StoreSection.objects.count(),
            category_id=category_id if category_id else None,
        )
        return JsonResponse({
            'success': True, 
            'section_id': section.id,
            'section_name': section.name
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء إنشاء القسم'}, status=400)

@login_required
@permission_required('invoice.change_storesection', raise_exception=True)
@require_POST
def api_update_section(request, section_id):
    """تحديث بيانات القسم"""
    try:
        data = json.loads(request.body)
        section = get_object_or_404(StoreSection, id=section_id)
        section.name = data.get('name', section.name)
        section.style_type = data.get('style_type', section.style_type)
        section.is_active = data.get('is_active', section.is_active)
        section.save()
        return JsonResponse({'success': True})
    except StoreSection.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'القسم غير موجود'}, status=404)


@login_required
@permission_required('invoice.delete_storesection', raise_exception=True)
@require_POST
def api_delete_section(request, section_id):
    """حذف قسم"""
    try:
        get_object_or_404(StoreSection, id=section_id).delete()
        return JsonResponse({'success': True})
    except StoreSection.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'القسم غير موجود'}, status=404)


@login_required
@permission_required('invoice.add_productsectionitem', raise_exception=True)
@require_POST
def api_add_product_to_section(request, section_id):
    """إضافة منتج إلى قسم"""
    try:
        data = json.loads(request.body)
        section = get_object_or_404(StoreSection, id=section_id)
        product = get_object_or_404(Product, id=data.get('product_id'))
        
        item, created = ProductSectionItem.objects.get_or_create(
            section=section,
            product=product,
            defaults={'display_order': section.items.count()}
        )
        
        if created:
            return JsonResponse({'success': True, 'item_id': item.id})
        return JsonResponse({'success': False, 'message': 'المنتج مضاف مسبقاً'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء الإضافة'}, status=400)


@login_required
@permission_required('invoice.delete_productsectionitem', raise_exception=True)
@require_POST
def api_remove_product_from_section(request, section_id, item_id):
    """حذف منتج من قسم"""
    try:
        item = get_object_or_404(ProductSectionItem, id=item_id, section_id=section_id)
        item.delete()
        return JsonResponse({'success': True})
    except ProductSectionItem.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'العنصر غير موجود'}, status=404)



@login_required
@permission_required('invoice.change_product', raise_exception=True)
@require_POST
def api_update_product_category(request, product_id):
    """تحديث تصنيف المنتج"""
    try:
        product = get_object_or_404(Product, id=product_id)
        data = json.loads(request.body)
        
        # السماح بتفريغ التصنيف (إرسال null)
        category_id = data.get('category_id')
        if category_id == '' or category_id is None:
            product.category = None
        else:
            from .models import Category
            product.category = get_object_or_404(Category, id=category_id)
            
        product.save()
        return JsonResponse({'success': True, 'message': 'تم تحديث التصنيف'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء التحديث'}, status=500)

# ===============================================
#  إدارة الطلبات (عرض وتحويل لفاتورة)
# ===============================================



@login_required
@permission_required('invoice.view_websiteorder', raise_exception=True)
def orders_list_view(request):
    """قائمة طلبات المتجر للمدير"""
    return render(request, 'invoice/store/admin_orders_list.html', {
        'orders': WebsiteOrder.objects.all().order_by('-order_date'),
        'title': 'إدارة طلبات المتجر'
    })



@login_required
@permission_required('invoice.view_websiteorder', raise_exception=True)
def order_detail_view(request, order_id):
    """تفاصيل طلب معين"""
    order = get_object_or_404(WebsiteOrder, id=order_id)
    return render(request, 'invoice/store/admin_order_detail.html', {
        'order': order,
        'title': f'تفاصيل الطلب #{order.id}'
    })



@login_required
@permission_required('invoice.change_websiteorder', raise_exception=True)
def convert_order_to_invoice(request, order_id):
    """تحويل طلب المتجر إلى فاتورة بيع في نظام المحاسبة"""
    order = get_object_or_404(WebsiteOrder, id=order_id)

    if order.related_sale:
        messages.warning(request, 'هذا الطلب تم تحويله مسبقاً إلى فاتورة.')
        return redirect('invoice:order_detail', order_id=order.id)

    try:
        with transaction.atomic():
            sale = Sale(
                created_by=request.user,
                sale_customer=order.user,
                sale_date=order.order_date.date(),
                sale_customer_phone=order.phone,
                sale_address=order.address,
                sale_notes=f"طلب متجر رقم #{order.id} - {order.notes or ''}",
                paid_amount=order.total_amount,
                is_paid=True
            )
            sale.save()

            for item in order.items.all():
                sale_item = SaleItem(
                    sale=sale,
                    product=item.product,
                    item_name=item.product_name,
                    sold_quantity=item.quantity,
                    unit_price=item.price
                )
                sale_item.save()
                # تم تعطيل خصم المخزون لأنه يتم الآن آلياً عند الشراء من المتجر لمنع الخصم المزدوج
                # sale_item.update_product_stock()

            sale.calculate_and_save_totals()
            
            CashTransaction.objects.create(
                transaction_date=timezone.now(),
                amount_in=order.total_amount,
                amount_out=Decimal('0.00'),
                transaction_type='sale_receipt',
                sale_invoice=sale,
                notes=f"تحصيل نقد مقابل طلب متجر #{order.id}",
                created_by=request.user
            )

            order.related_sale = sale
            order.status = 'processing'
            order.save()
            
            messages.success(request, f'تم التحويل بنجاح! رقم الفاتورة: {sale.uniqueId}')
            return redirect('invoice:sale_detail', slug=sale.slug)

    except Exception as e:
        messages.error(request, 'حدث خطأ أثناء التحويل، يرجى المحاولة مرة أخرى.')
        return redirect('invoice:order_detail', order_id=order.id)



# ===============================================
#  إدارة: قائمة المنتجات المنتظرة
# ===============================================


@login_required
@permission_required('invoice.view_stocknotification', raise_exception=True)
def admin_stock_notifications(request):
    """
    عرض قائمة بالمنتجات التي ينتظرها أشخاص (فقط الطلبات غير المرسلة)
    """
    # ==========================================
    # التعديل هنا: إضافة .filter(is_sent=False)
    # ==========================================
    raw_stats = StockNotification.objects.filter(is_sent=False).values('product__id', 'product__product_name', 'product__product_image').annotate(
        waiting_count=Count('id')
    ).order_by('-waiting_count')

    # تجهيز البيانات للقالب (مع معالجة رابط الصورة)
    notifications_stats = []
    for item in raw_stats:
        img_path = item.get('product__product_image')
        
        if img_path:
            image_url = f"/media/{img_path}" 
        else:
            image_url = "/static/images/no-image.png"

        notifications_stats.append({
            'id': item['product__id'],
            'name': item['product__product_name'],
            'image_url': image_url,
            'waiting_count': item['waiting_count']
        })

    return render(request, 'invoice/store/admin_notifications.html', {
        'notifications_stats': notifications_stats,
        'title': 'تنبيهات توفر المواد'
    })





# ==========================================================
# دالة إرسال الإشعارات (محدثة لتدعم الأرشيف)
# ==========================================================
@login_required
@permission_required('invoice.change_stocknotification', raise_exception=True)
@require_POST
def admin_send_notification(request, product_id):
    """
    إرسال إيميل للجميع ينتظرون هذا المنتج ثم أرشفة السجلات
    """
    # 1. جلب البيانات والتحقق
    try:
        product = get_object_or_404(Product, id=product_id)
        notifications = StockNotification.objects.filter(product=product)
        
        if notifications.count() == 0:
            return JsonResponse({'success': False, 'message': 'لا يوجد طلبات إشعار لهذا المنتج'})

        # 2. جلب إعدادات البريد الديناميكية (من قاعدة البيانات)
        try:
            connection, from_email = get_active_email_connection()
        except Exception as e:
            return JsonResponse({'success': False, 'message': 'تعذر العثور على إعدادات البريد'})

        if connection and from_email:
            # 3. حفظ الإعدادات الحالية لاستعادتها لاحقاً
            old_host = getattr(settings, 'EMAIL_HOST', None)
            old_port = getattr(settings, 'EMAIL_PORT', None)
            old_user = getattr(settings, 'EMAIL_HOST_USER', None)
            old_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', None)
            old_tls = getattr(settings, 'EMAIL_USE_TLS', None)
            old_from = getattr(settings, 'DEFAULT_FROM_EMAIL', None)

            try:
                # 4. تطبيق إعدادات البريد من قاعدة البيانات على إعدادات النظام مؤقتاً
                settings.EMAIL_HOST = connection.host
                settings.EMAIL_PORT = connection.port
                settings.EMAIL_HOST_USER = connection.username
                settings.EMAIL_HOST_PASSWORD = connection.password
                settings.EMAIL_USE_TLS = connection.use_tls
                settings.DEFAULT_FROM_EMAIL = from_email

                # 5. إرسال الإيميل
                emails_list = list(notifications.values_list('email', flat=True))
                subject = f"عاد التوفر: {product.product_name}"
                
                # تحضير محتوى الإيميل (HTML)
                message_html = render_to_string('invoice/store/email_notification.html', {
                    'product': product,
                    'site_url': request.build_absolute_uri('/')[:-1]
                })

                email = EmailMessage(
                    subject=subject,
                    body=message_html,
                    from_email=from_email,
                    bcc=emails_list, # إرسال نسخة مخفية للجميع
                )
                email.content_subtype = "html" # تحديد المحتوى كـ HTML
                email.send()

                # 6. أرشفة السجلات (تعديل الحقول بدلاً من الحذف)
                # نحتاج لاستيراد timezone من django.utils
                from django.utils import timezone 
                notifications.update(is_sent=True, sent_at=timezone.now())

                return JsonResponse({
                    'success': True, 
                    'message': f'تم إرسال الإشعار لـ {notifications.count()} شخص ونقله للأرشيف.'
                })

            finally:
                # 7. استعادة الإعدادات الأصلية (تنظيف) ضروري جداً
                settings.EMAIL_HOST = old_host
                settings.EMAIL_PORT = old_port
                settings.EMAIL_HOST_USER = old_user
                settings.EMAIL_HOST_PASSWORD = old_pass
                settings.EMAIL_USE_TLS = old_tls
                settings.DEFAULT_FROM_EMAIL = old_from

        else:
            return JsonResponse({'success': False, 'message': 'لم يتم العثور على إعدادات بريد صالحة في قاعدة البيانات'})

    except Exception as e:
        print(f"Error sending notification: {str(e)}")
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء إرسال الإشعار'}, status=500)


@login_required
@permission_required('invoice.view_stocknotification', raise_exception=True)
def admin_notification_archive(request):
    """عرض أرشيف الإشعارات التي تم إرسالها"""
    archive = StockNotification.objects.filter(is_sent=True).select_related('product').order_by('-sent_at')
    
    return render(request, 'invoice/store/notification_archive.html', {
        'archive': archive,
        'title': 'أرشيف إشعارات المخزون'
    })



@login_required
@permission_required('invoice.change_stocknotification', raise_exception=True)
@require_POST
def admin_undo_archive_notification(request):
    """
    إعادة تنبيه من الأرشيف إلى القائمة منتهية
    """
    response_data = {'success': False, 'message': 'حدث خطأ غير متوقع'}
    
    try:
        # محاولة قراءة البيانات
        try:
            data = json.loads(request.body)
            notif_id = data.get('id')
        except json.JSONDecodeError:
            response_data['message'] = 'بيانات غير صالحة'
            return JsonResponse(response_data, status=400)

        # جلب السجل
        try:
            notif = StockNotification.objects.get(id=notif_id, is_sent=True)
        except StockNotification.DoesNotExist:
            response_data['message'] = 'هذا السجل غير موجود أو تم حذفه.'
            return JsonResponse(response_data, status=404)

        # تنفيذ العملية
        notif.is_sent = False
        notif.sent_at = None
        notif.save()

        response_data['success'] = True
        response_data['message'] = 'تم إعادة التنبيه للقائمة منتهية بنجاح.'

    except Exception as e:
        # طباعة الخطأ في السيرفر للتصحيح
        print(f"Error in undo_archive: {str(e)}")
        response_data['message'] = 'خطأ داخلي أثناء استعادة التنبيه'

    return JsonResponse(response_data)





@login_required
@permission_required('invoice.view_flashdeal', raise_exception=True)
def api_flash_deals(request):
    """قائمة عروض الفلاش"""
    try:
        deals = FlashDeal.objects.select_related('product__store_setting').order_by('-created_at')
        data = []
        for deal in deals:
            p = deal.product
            try:
                original = f"{get_product_price(p):.2f}"
            except:
                original = "0.00"
            try:
                remaining = deal.remaining_quantity()
                percentage = deal.remaining_percentage()
            except:
                remaining = deal.max_quantity
                percentage = 100
            try:
                is_active = deal.is_currently_active()
            except:
                is_active = deal.is_active
            try:
                ends_at = deal.ends_at.strftime('%Y-%m-%d %H:%M') if deal.ends_at else ''
            except:
                ends_at = ''
            
            if is_active:
                status = 'نشط'
            elif deal.ends_at and timezone.now() > deal.ends_at:
                status = 'منتهي'
            else:
                status = 'معطّل'
            
            data.append({
                'id': deal.id,
                'product_id': p.id,
                'product_name': p.product_name,
                'product_image': get_product_image_url(p),
                'original_price': original,
                'deal_price': f"{deal.deal_price:.2f}",
                'max_quantity': deal.max_quantity,
                'remaining': remaining,
                'percentage': percentage,
                'ends_at': ends_at,
                'is_active': is_active,
                'status_text': status,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': 'حدث خطأ أثناء جلب العروض'}, status=500)


@login_required
@permission_required('invoice.add_flashdeal', raise_exception=True)
@require_POST
def api_add_flash_deal(request):
    """إضافة عرض فلاش"""
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        if not product_id:
            return JsonResponse({'success': False, 'message': 'المنتج مطلوب'}, status=400)
        
        product = get_object_or_404(Product, id=product_id)
        
        if not hasattr(product, 'store_setting') or not product.store_setting.is_visible:
            return JsonResponse({'success': False, 'message': 'المنتج غير ظاهر في المتجر'}, status=400)
        
        from datetime import timedelta
        hours = int(data.get('hours', 6))
        
        deal = FlashDeal.objects.create(
            product=product,
            deal_price=data.get('deal_price', 0),
            max_quantity=int(data.get('max_quantity', 10)),
            ends_at=timezone.now() + timedelta(hours=hours),
            is_active=data.get('is_active', True),
        )
        return JsonResponse({'success': True, 'message': 'تم إضافة العرض بنجاح', 'deal_id': deal.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء إضافة العرض'}, status=400)




@login_required
@permission_required('invoice.change_flashdeal', raise_exception=True)
@require_POST
def api_toggle_flash_deal(request, deal_id):
    """تفعيل/تعطيل عرض فلاش"""
    try:
        deal = get_object_or_404(FlashDeal, id=deal_id)
        deal.is_active = not deal.is_active
        deal.save()
        return JsonResponse({'success': True, 'is_active': deal.is_active})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء تحديث العرض'}, status=400)


@login_required
@permission_required('invoice.delete_flashdeal', raise_exception=True)
def api_delete_flash_deal(request, deal_id):
    """حذف عرض فلاش"""
    get_object_or_404(FlashDeal, id=deal_id).delete()
    return JsonResponse({'success': True, 'message': 'تم الحذف'})



# ===============================================
#  API: إدارة الشريط العلوي والأيقونات
# ===============================================


@login_required
@permission_required('invoice.add_storeannouncement', raise_exception=True)
@require_POST
def api_add_announcement(request):
    """إضافة إعلان مع دعم اختيار الأيقونة"""
    try:
        data = json.loads(request.body)
        text = data.get('text', '').strip()
        if not text:
            return JsonResponse({'success': False, 'message': 'نص الإعلان مطلوب'}, status=400)
        
        icon_class = data.get('icon_class', 'fa-bullhorn').strip()
        
        StoreAnnouncement.objects.create(
            text=text,
            icon_class=icon_class,
            order=StoreAnnouncement.objects.count()
        )
        return JsonResponse({'success': True, 'message': 'تم إضافة الإعلان بنجاح'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'بيانات غير صالحة'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء إضافة الإعلان'}, status=500)


@login_required
@permission_required('invoice.delete_storeannouncement', raise_exception=True)
@require_POST
def api_delete_announcement(request, ann_id):
    """حذف إعلان - تم إضافة @require_POST ومعالجة أفضل"""
    try:
        announcement = get_object_or_404(StoreAnnouncement, id=ann_id)
        announcement.delete()
        return JsonResponse({'success': True, 'message': 'تم الحذف بنجاح'})
    except StoreAnnouncement.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'الإعلان غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء حذف الإعلان'}, status=500)



@login_required
@permission_required('invoice.change_storefeatureicon', raise_exception=True)
@require_POST
def api_update_feature(request, feature_id):
    """تحديث عنوان الأيقونة"""
    try:
        data = json.loads(request.body)
        feature = get_object_or_404(StoreFeatureIcon, id=feature_id)
        feature.title = data.get('title', feature.title)
        # icon_class يمكن تعديله أيضاً لكن سنكتفي بالعنوان للتبسيط في الواجهة
        feature.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء التحديث'}, status=500)








#================================================
#    من اجل كلمة المرور في نظام التسعير       #
# ===============================================




@require_POST
@login_required
def save_pricing_password(request):
    """حفظ كلمة مرور نظام التسعير من لوحة التحكم"""
    
    if not request.user.is_staff:
        logger.warning(f"محاولة غير مصرح بها لحفظ كلمة مرور التسعير بواسطة: {request.user.username}")
        return JsonResponse({'success': False, 'message': 'هذه العملية للمدير فقط'}, status=403)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'خطأ في تنسيق البيانات'}, status=400)
    
    password = data.get('password', '').strip()
    confirm = data.get('confirm', '').strip()
    
    if not password:
        return JsonResponse({'success': False, 'message': 'كلمة المرور مطلوبة'})
    
    if len(password) < 4:
        return JsonResponse({'success': False, 'message': 'كلمة المرور قصيرة جداً (4 أحرف على الأقل)'})
    
    if len(password) > 50:
        return JsonResponse({'success': False, 'message': 'كلمة المرور طويلة جداً (أقصى 50 حرف)'})
    
    if password != confirm:
        return JsonResponse({'success': False, 'message': 'كلمتا المرور غير متطابقتين'})
    
    settings_obj = PricingSetting.get_settings()
    
    # نمرر كلمة المرور كنص عادي، ودالة save في الموديل ستشفرها تلقائياً
    settings_obj.pricing_password = password
    settings_obj.save()
    
    logger.info(f"تم تغيير كلمة مرور نظام التسعير بواسطة: {request.user.username}")
    
    return JsonResponse({
        'success': True,
        'message': 'تم حفظ كلمة مرور نظام التسعير بنجاح'
    })








#================================================
#            النسخ الاحطياتي       #
# ===============================================


@login_required
def backup_page(request):
    """عرض صفحة النسخ الاحتياطي مع قائمة النسخ المخزنة على السيرفر"""
    server_backups = get_server_backups()
    backups_dir = get_backups_dir()
    
    return render(request, 'invoice/backup_page.html', {
        'server_backups': server_backups,
        'backups_dir_path': backups_dir,
    })


@login_required
def download_backup(request):
    """إنشاء نسخة احتياطية جديدة وتحميلها وحفظها على السيرفر"""
    if request.method == 'POST':
        try:
            note = request.POST.get('backup_note', '')
            
            # 1. إنشاء النسخة في مجلد مؤقت
            temp_backup_path = create_backup(backup_note=note)
            filename = os.path.basename(temp_backup_path)
            
            # 2. حفظ نسخة دائمة على السيرفر (بدون بادئة)
            save_backup_to_server(temp_backup_path, prefix="")
            
            # 3. تحميل الملف للمستخدم
            with open(temp_backup_path, 'rb') as f:
                wrapper = f.read()
            
            response = HttpResponse(wrapper, content_type='application/zip')
            response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"
            return response
            
        except Exception as e:
            return HttpResponse(f"حدث خطأ أثناء إنشاء النسخة الاحتياطية: {str(e)}", status=500)
    
    return redirect('backup_page')


@login_required
def download_server_backup(request, filename):
    """تحميل نسخة احتياطية مخزنة على السيرفر (سواء عادية أو نسخة أمان)"""
    try:
        backups_dir = get_backups_dir()
        filepath = os.path.join(backups_dir, filename)
        
        # التحقق من الأمان
        real_path = os.path.realpath(filepath)
        real_dir = os.path.realpath(backups_dir)
        if not real_path.startswith(real_dir + os.sep) and real_path != real_dir:
            return HttpResponse("مسار غير آمن!", status=403)
        
        if not os.path.exists(filepath):
            return HttpResponse("الملف غير موجود على السيرفر!", status=404)
        
        response = FileResponse(
            open(filepath, 'rb'), 
            content_type='application/zip'
        )
        response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"
        return response
        
    except Exception as e:
        return HttpResponse(f"حدث خطأ: {str(e)}", status=500)


@login_required
def delete_server_backup_view(request):
    """حذف نسخة احتياطية من السيرفر (يُستدعى عبر AJAX)"""
    if request.method == 'POST':
        filename = request.POST.get('filename', '').strip()
        
        if not filename or not filename.endswith('.zip'):
            return JsonResponse({'success': False, 'error': 'اسم ملف غير صالح'}, status=400)
        
        try:
            delete_backup_file(filename)
            return JsonResponse({
                'success': True, 
                'message': 'تم حذف النسخة بنجاح',
                'filename': filename,
            })
        except FileNotFoundError:
            return JsonResponse({'success': False, 'error': 'الملف غير موجود'}, status=404)
        except PermissionError:
            return JsonResponse({'success': False, 'error': 'مسار غير آمن'}, status=403)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'طريقة طلب غير صحيحة'}, status=405)



@login_required
def upload_restore(request):
    """استرجاع نسخة احتياطية من ملف مرفوع"""
    if request.method == 'POST':
        if 'backup_file' not in request.FILES:
            return HttpResponse("لم يتم اختيار أي ملف!", status=400)
        
        uploaded_file = request.FILES['backup_file']
        
        if not uploaded_file.name.endswith('.zip'):
            return HttpResponse("يجب أن يكون الملف بامتداد .zip", status=400)
        
        try:
            # =========================================================
            # 1. فك الضغط عن الملف المرفوع أولاً في مجلد مؤقت للفحص
            # =========================================================
            print("بدء فحص الملف المرفوع...")
            temp_dir = tempfile.mkdtemp()
            temp_zip_path = os.path.join(temp_dir, 'uploaded_backup.zip')
            
            with open(temp_zip_path, 'wb') as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)
            
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # =========================================================
            # 2. التحقق الحاسم (الدرع الواقي)
            # =========================================================
            sql_file = os.path.join(temp_dir, 'database_backup.sql')
            json_file = os.path.join(temp_dir, 'database_backup.json')

            if not os.path.exists(sql_file) and not os.path.exists(json_file):
                # ملف غير صالح - نحذف المجلد المؤقت ونرفض العملية فوراً
                shutil.rmtree(temp_dir)
                print("تم رفض الملف: لا يحتوي على قاعدة بيانات صالحة.")
                return HttpResponse(
                    "<div style='text-align: center; padding: 2rem; font-family: Tajawal, sans-serif; direction: rtl;'>"
                    "<h2 style='color: #e53935;'><i class='fas fa-exclamation-triangle'></i> ملف غير صالح!</h2>"
                    "<p style='font-size: 1.1rem; color: #333;'>الملف الذي قمت برفعه ليس نسخة احتياطية صالحة لنظام BalanceIQ.</p>"
                    "<p style='color: #666;'>نسخ النظام الصحيحة تحتوي بالضرورة على ملفات قاعدة البيانات.</p>"
                    "<br><a href='/invoice/backup/' style='background: #0097a7; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;'>العودة لمركز النسخ الاحتياطي</a>"
                    "</div>",
                    status=400
                )

            # =========================================================
            # 3. قراءة معلومات النسخة لمعرفة طريقة النسخ المستخدمة
            # =========================================================
            info_file = os.path.join(temp_dir, 'backup_info.txt')
            backup_method = 'unknown'
            if os.path.exists(info_file):
                with open(info_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('Backup Method:'):
                            backup_method = line.split(':', 1)[1].strip()
                            break

            # =========================================================
            # 4. أخذ نسخة أمان إجبارية (بعد التأكد من صلاحية الملف)
            # =========================================================
            print("الملف صالح. بدء أخذ نسخة أمان قبل الاسترجاع...")
            safety_backup_path = create_backup()
            
            permanent_safety_path, safety_filename = save_backup_to_server(
                safety_backup_path, 
                prefix="Restore_a_backup_"
            )

            # =========================================================
            # 5. زرع قاعدة البيانات حسب الطريقة المستخدمة
            # =========================================================
            if backup_method == 'mysql_dump' and os.path.exists(sql_file):
                print("بدء زرع قاعدة البيانات (MySQL)...")
                db_settings = settings.DATABASES['default']
                
                command = [
                    'mysql',
                    f'-u{db_settings.get("USER", "root")}',
                    f'-h{db_settings.get("HOST", "localhost")}',
                    f'--port={db_settings.get("PORT", "3306")}',
                    '--default-character-set=utf8mb4',
                ]
                
                if db_settings.get('PASSWORD', ''):
                    command.append(f'-p{db_settings["PASSWORD"]}')
                    
                command.append(db_settings.get('NAME'))

                with open(sql_file, 'rb') as f:
                    process = subprocess.Popen(command, stdin=f, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    _, error = process.communicate(timeout=120)
                    
                    if process.returncode != 0:
                        error_msg = error.decode('utf-8', errors='replace')
                        raise Exception(f"MySQL Import Error: {error_msg}")

                print("تم زرع قاعدة البيانات بنجاح!")
                
            elif backup_method == 'django_json' and os.path.exists(json_file):
                print("بدء زرع قاعدة البيانات (Django loaddata)...")
                from django.core import management
                management.call_command('flush', '--noinput')
                management.call_command('loaddata', json_file)
                print("تم زرع قاعدة البيانات بنجاح!")
            else:
                # محاولة تلقائية إذا لم يتم التعرف على الطريقة
                if os.path.exists(sql_file):
                    db_settings = settings.DATABASES['default']
                    command = [
                        'mysql',
                        f'-u{db_settings.get("USER", "root")}',
                        f'-h{db_settings.get("HOST", "localhost")}',
                        f'--port={db_settings.get("PORT", "3306")}',
                        '--default-character-set=utf8mb4',
                    ]
                    if db_settings.get('PASSWORD', ''):
                        command.append(f'-p{db_settings["PASSWORD"]}')
                    command.append(db_settings.get('NAME'))

                    with open(sql_file, 'rb') as f:
                        process = subprocess.Popen(command, stdin=f, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        _, error = process.communicate(timeout=120)
                        if process.returncode != 0:
                            raise Exception(f"MySQL Import Error: {error.decode('utf-8', errors='replace')}")
                            
                elif os.path.exists(json_file):
                    from django.core import management
                    management.call_command('flush', '--noinput')
                    management.call_command('loaddata', json_file)

            # =========================================================
            # 6. استرجاع الصور والملفات
            # =========================================================
            media_backup_file = os.path.join(temp_dir, 'media_backup.zip')
            
            if os.path.exists(media_backup_file) and hasattr(settings, 'MEDIA_ROOT'):
                print("بدء استرجاع مجلد الميديا (الصور والملفات)...")
                
                if os.path.exists(settings.MEDIA_ROOT):
                    for item in os.listdir(settings.MEDIA_ROOT):
                        item_path = os.path.join(settings.MEDIA_ROOT, item)
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                
                with zipfile.ZipFile(media_backup_file, 'r') as media_zip:
                    media_zip.extractall(settings.MEDIA_ROOT)
                    
                print("تم استرجاع الصور والملفات بنجاح!")

            # =========================================================
            # 7. تسجيل الخروج الإجباري مع رسالة الأمان المحدثة
            # =========================================================
            logout(request)
            
            success_message = mark_safe(
                f'🎉 تم استرجاع النسخة الاحتياطية بنجاح! <br><br>'
                f'🛡️ <strong>إجراء الأمان:</strong> تم حفظ نسخة للوضع السابق باسم: <br>'
                f'<strong style="direction: ltr; display: inline-block; background: #eee; padding: 4px 8px; border-radius: 4px; font-size: 0.9rem;">{safety_filename}</strong><br><br>'
                f'🔑 تم تسجيل خروجك. بعد تسجيل الدخول، اذهب إلى "مركز النسخ الاحتياطي" لتحميل هذه النسخة إن لزم الأمر.'
            )
            messages.warning(request, success_message)
            
            return redirect('/accounts/login/')

        except Exception as e:
            logout(request)
            return HttpResponse(f"حدث خطأ فادح أثناء الاسترجاع: <br><br>{str(e)}", status=500)

    return redirect('backup_page')


@login_required
def factory_reset_system(request):
    """تصفير المصنع - مسح جميع البيانات وإعادة النظام لوضعه الأولي"""
    if not request.user.is_superuser:
        return HttpResponse("ليس لديك صلاحية للقيام بهذا الإجراء.", status=403)

    if request.method == 'POST':
        try:
            from django.apps import apps
            from django.contrib.auth.models import User
            from django.db import models as django_models

            # ==========================================
            # 1. أخذ نسخة أمان إجبارية
            # ==========================================
            print("بدء أخذ نسخة أمان قبل التصفية الشاملة...")
            safety_backup_path = create_backup()
            save_backup_to_server(safety_backup_path, prefix="Before_Reset_")

            # ==========================================
            # 2. مسح جميع بيانات تطبيق Invoice
            # ==========================================
            print("بدء مسح بيانات تطبيق Invoice...")
            invoice_models = apps.get_app_config('invoice').get_models()
            
            for model in invoice_models:
                try:
                    count = model.objects.all().count()
                    if count > 0:
                        model.objects.all().delete()
                        print(f"✅ تم مسح ({count}) سجل من جدول: {model.__name__}")
                except Exception as e:
                    print(f"⚠️ تعذر مسح {model.__name__}: {e}")

            # ==========================================
            # 3. مسح النماذج الحرجة من تطبيقات أخرى
            # ==========================================
            critical_models = ['CompanySettings', 'EmailSetting', 'Profile', 'TrialRequest']
            
            for model_name in critical_models:
                for app_config in apps.get_app_configs():
                    try:
                        Model = apps.get_model(app_config.label, model_name)
                        count = Model.objects.all().count()
                        if count > 0:
                            Model.objects.all().delete()
                            print(f"✅ تم مسح ({count}) سجل من جدول: {model_name} (من تطبيق {app_config.label})")
                        break
                    except LookupError:
                        continue

            # ==========================================
            # 4. حذف المستخدمين التجريبيين
            # ==========================================
            deleted_users_count = User.objects.filter(is_superuser=False).delete()[0]
            print(f"✅ تم حذف ({deleted_users_count}) مستخدم تجريبي.")

            # ==========================================
            # 5. مسح ملفات الميديا
            # ==========================================
            if hasattr(settings, 'MEDIA_ROOT') and os.path.exists(settings.MEDIA_ROOT):
                for item in os.listdir(settings.MEDIA_ROOT):
                    if item not in ['safety_backups', 'server_backups']:
                        item_path = os.path.join(settings.MEDIA_ROOT, item)
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                print("✅ تم مسح ملفات الميديا.")

            # ==========================================
            # 6. مسح كاش النظام
            # ==========================================
            from django.core.cache import cache
            cache.clear()

            # ==========================================
            # 7. ★★★ إعادة إنشاء كل السجلات الأساسية ★★★
            # ==========================================
            print("=" * 60)
            print("بدء إعادة إنشاء السجلات الأساسية اللازمة...")
            print("=" * 60)

            def _safe_create(model_class, **extra_fields):
                """إنشاء سجل افتراضي بأمان"""
                if model_class.objects.exists():
                    return None
                field_values = {}
                for field in model_class._meta.get_fields():
                    fname = field.name
                    if fname in ('id', 'pk'):
                        continue
                    if fname in extra_fields:
                        field_values[fname] = extra_fields[fname]
                        continue
                    if isinstance(field, (django_models.ManyToManyRel,
                                          django_models.OneToOneRel,
                                          django_models.ManyToOneRel)):
                        continue
                    if hasattr(field, 'default') and field.default is not django_models.NOT_PROVIDED:
                        field_values[fname] = field.default
                    elif field.null:
                        field_values[fname] = None
                    elif isinstance(field, django_models.CharField):
                        field_values[fname] = ''
                    elif isinstance(field, django_models.TextField):
                        field_values[fname] = ''
                    elif isinstance(field, (django_models.IntegerField, django_models.FloatField, django_models.DecimalField)):
                        field_values[fname] = 0
                    elif isinstance(field, django_models.BooleanField):
                        field_values[fname] = False
                    elif isinstance(field, (django_models.DateField, django_models.DateTimeField)):
                        field_values[fname] = None
                    elif isinstance(field, django_models.ImageField):
                        field_values[fname] = None
                try:
                    obj = model_class.objects.create(**field_values)
                    print(f"  ✅ تم إنشاء سجل افتراضي: {model_class.__name__}")
                    return obj
                except Exception as e:
                    print(f"  ⚠️ تعذر إنشاء {model_class.__name__}: {e}")
                    return None

            # 7.1 CompanySettings
            for app_config in apps.get_app_configs():
                try:
                    _safe_create(apps.get_model(app_config.label, 'CompanySettings'))
                    break
                except LookupError:
                    continue

            # 7.2 Profile للمدير الأعلى
            superuser = User.objects.filter(is_superuser=True).first()
            if superuser:
                for app_config in apps.get_app_configs():
                    try:
                        ProfileModel = apps.get_model(app_config.label, 'Profile')
                        if not ProfileModel.objects.filter(user=superuser).exists():
                            _safe_create(ProfileModel, user=superuser)
                        break
                    except LookupError:
                        continue

            # 7.3 ★★★ PricingSetting — كان مفقوداً تماماً ★★★
            for app_config in apps.get_app_configs():
                try:
                    _safe_create(apps.get_model(app_config.label, 'PricingSetting'))
                    break
                except LookupError:
                    continue

            # 7.4 ★★★ العملة الافتراضية (SYP) — كان مفقوداً ★★★
            try:
                Currency = apps.get_model('invoice', 'Currency')
                if not Currency.objects.exists():
                    Currency.objects.create(
                        code='SYP', symbol='ل.س', name='Syrian Pound',
                        name_ar='ليرة سورية', singular_ar='ليرة سورية',
                        dual_ar='ليرتان سوريتان', plural_ar='ليرات سورية',
                        fraction_name_ar='قرش', fraction_dual_ar='قرشان',
                        fraction_plural_ar='قروش',
                        exchange_rate=Decimal('1.0000'), decimals=2,
                        is_default=True, is_active=True,
                    )
                    print("  ✅ تم إنشاء العملة الافتراضية: ليرة سورية (SYP)")
            except LookupError:
                pass

            # 7.5 ★★★ طريقة الدفع "نقداً" — كان مفقوداً ★★★
            try:
                PaymentMethod = apps.get_model('invoice', 'Payment_method')
                if not PaymentMethod.objects.exists():
                    PaymentMethod.objects.create(
                        name='نقداً', is_cash=True,
                        notes='طريقة الدفع ',
                    )
                    print("  ✅ تم إنشاء طريقة الدفع: نقداً")
            except LookupError:
                pass

            # 7.6 ★★★ الحالة الافتراضية — كان مفقوداً ★★★
            try:
                StatusModel = apps.get_model('invoice', 'Status')
                if not StatusModel.objects.exists():
                    StatusModel.objects.create(
                        name='منتهية', notes='الحالة الافتراضية  ',
                    )
                    print("  ✅ تم إنشاء الحالة: منتهية")
            except LookupError:
                pass

            # 7.7 ★★★ أي نماذج إضافية قد يحتاجها النظام ★★★
            extra_seed = ['Branch', 'Warehouse', 'CashBox', 'Store', 'Category']
            for model_name in extra_seed:
                for app_config in apps.get_app_configs():
                    try:
                        Model = apps.get_model(app_config.label, model_name)
                        if not Model.objects.exists():
                            _safe_create(Model)
                        break
                    except LookupError:
                        continue

            print("=" * 60)
            print("✅ تم إعادة إنشاء جميع السجلات الأساسية بنجاح.")
            print("=" * 60)

            # ==========================================
            # 8. تسجيل الخروج وإعادة التوجيه
            # ==========================================
            logout(request)
            messages.success(request, "🎉 تم إعادة ضبط المصنع بنجاح! النظام نظيف وجاهز للعمل.")
            return redirect('/accounts/login/')

        except Exception as e:
            logout(request)
            return HttpResponse(f"حدث خطأ أثناء التصفية: <br><br>{str(e)}", status=500)

    return redirect('backup_page')


