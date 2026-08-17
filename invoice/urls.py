from django.urls import path
from . import views

# استيراد التقارير الجديدة
from .views import (
    profit_report_view, 
    sales_by_customer_report, 
    purchases_by_supplier_report, 
    daily_sales_summary_report, 
    unpaid_invoices_report, dead_stocks_report , api_add_announcement
)

app_name = 'invoice'

urlpatterns = [
    # ================ فواتير الشراء ================
    path('purch/', views.purch_list, name='purch_list'),
    path('purchases/', views.purch_list, name='purchases_list'),
    path('purch/create/', views.purch_create, name='purch_create'),
    path('purchases/create/', views.purch_create, name='purchases_create'),
    path('purch/<slug:slug>/', views.purch_detail, name='purch_detail'),
    path('purchases/<slug:slug>/', views.purch_detail, name='purchases_detail'),
    path('purch/<slug:slug>/edit/', views.purch_edit, name='purch_edit'),
    path('purch/<slug:slug>/delete/', views.purch_delete, name='purch_delete'),
    
    # ================ المنتجات والباركود ================
    path('products/', views.product_list, name='product_list'),
    path('products/bulk-update/', views.product_bulk_update, name='product_bulk_update'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<slug:slug>/', views.product_detail, name='product_detail'),
    path('products/<slug:slug>/delete/', views.product_delete, name='product_delete'),
    path('products/<slug:slug>/edit/', views.product_edit, name='product_edit'),
    path('products/<slug:product_slug>/barcode/create/', views.barcode_create, name='barcode_create'),
    path('barcode/manage/<slug:product_slug>/', views.barcode_manage, name='barcode_manage'),
    path('barcode/delete/<int:barcode_id>/', views.barcode_delete, name='barcode_delete'),
    
    # ================ إدارة الصندوق ================
    path('cash/', views.cash_dashboard, name='cash_dashboard'),
    path('cash/transactions/', views.cash_transaction_list, name='cash_transaction_list'),
    path('cash/transactions/create/', views.cash_transaction_create, name='cash_transaction_create'),
    path('cash/transactions/<int:pk>/', views.cash_transaction_detail, name='cash_transaction_detail'),
    
    # ================ APIs للبحث ================
    path('search-suppliers/', views.search_suppliers, name='search_suppliers'),
    path('search-products/', views.search_products, name='search_products'),
    path('api/product/<int:product_id>/', views.get_product_details, name='get_product_details'),
    path('api/barcode/<str:barcode>/', views.api_barcode_search, name='api_barcode_search'),
    
    # ================ APIs للدفع والصندوق ================
    path('get-payment-method/<int:pk>/', views.get_payment_method, name='get_payment_method'),
    path('update-payment-method-cash/<int:pk>/', views.update_payment_method_cash, name='update_payment_method_cash'),
    path('get-cash-balance/', views.get_cash_balance, name='get_cash_balance'),
    
    # ================ APIs لتحويل المبالغ ================
    path('api/convert-to-words/', views.convert_amount_to_words_api, name='convert_to_words'),
    path('api/get-current-amount/', views.get_current_amount_in_words, name='get_current_amount'),
    
    # ================ مرتجعات المشتريات ================
    path('purchases/<slug:slug>/return/', views.purch_return_create_view, name='purch_return_create'),
    path('purchase-returns/<slug:slug>/', views.purchase_return_detail_view, name='purchase_return_detail'),
    path('purchase-returns/', views.purchase_return_list_view, name='purchase_return_list'),
    path('purchase-returns/<slug:slug>/delete/', views.purchase_return_delete_view, name='purchase_return_delete'),
    
    # ================ العملات ================
    path('currencies/', views.CurrencyListView.as_view(), name='currency_list'),
    path('currencies/create/', views.CurrencyCreateView.as_view(), name='currency_create'),
    path('currencies/<int:pk>/', views.CurrencyDetailView.as_view(), name='currency_detail'),
    path('currencies/<int:pk>/edit/', views.CurrencyUpdateView.as_view(), name='currency_edit'),
    path('currencies/<int:pk>/delete/', views.CurrencyDeleteView.as_view(), name='currency_delete'),
    
    # ================ طرق الدفع ================
    path('payment-methods/', views.PaymentMethodListView.as_view(), name='payment_method_list'),
    path('payment-methods/create/', views.PaymentMethodCreateView.as_view(), name='payment_method_create'),
    path('payment-methods/<int:pk>/', views.PaymentMethodDetailView.as_view(), name='payment_method_detail'),
    path('payment-methods/<int:pk>/edit/', views.PaymentMethodUpdateView.as_view(), name='payment_method_edit'),
    path('payment-methods/<int:pk>/delete/', views.PaymentMethodDeleteView.as_view(), name='payment_method_delete'),
    
    # ================ شركات الشحن ================
    path('shipping-companies/', views.ShippingCompanyListView.as_view(), name='shipping_company_list'),
    path('shipping-companies/create/', views.ShippingCompanyCreateView.as_view(), name='shipping_company_create'),
    path('shipping-companies/<int:pk>/', views.ShippingCompanyDetailView.as_view(), name='shipping_company_detail'),
    path('shipping-companies/<int:pk>/edit/', views.ShippingCompanyUpdateView.as_view(), name='shipping_company_edit'),
    path('shipping-companies/<int:pk>/delete/', views.ShippingCompanyDeleteView.as_view(), name='shipping_company_delete'),
    
    # ================ الحالات ================
    path('statuses/', views.StatusListView.as_view(), name='status_list'),
    path('statuses/create/', views.StatusCreateView.as_view(), name='status_create'),
    path('statuses/<int:pk>/', views.StatusDetailView.as_view(), name='status_detail'),
    path('statuses/<int:pk>/edit/', views.StatusUpdateView.as_view(), name='status_edit'),
    path('statuses/<int:pk>/delete/', views.StatusDeleteView.as_view(), name='status_delete'),
    
    # ================ أنواع الأسعار ================
    path('price-types/', views.PriceTypeListView.as_view(), name='price_type_list'),
    path('price-types/create/', views.PriceTypeCreateView.as_view(), name='price_type_create'),
    path('price-types/<int:pk>/', views.PriceTypeDetailView.as_view(), name='price_type_detail'),
    path('price-types/<int:pk>/edit/', views.PriceTypeUpdateView.as_view(), name='price_type_edit'),
    path('price-types/<int:pk>/delete/', views.PriceTypeDeleteView.as_view(), name='price_type_delete'),
    
    # ================ فواتير المبيعات ================
    path('sales/', views.sale_list, name='sale_list'),
    
    path('pos/create/', views.pos_sale_create, name='pos_sale_create'),


    path('sales/create/', views.sale_create, name='sale_create'),
    path('sale/<slug:slug>/', views.sale_detail, name='sale_detail'),
    path('sale/edit/<slug:slug>/', views.sale_edit, name='sale_edit'),

    # ================ مرتجع المبيعات ================
    path('sale-return/list/', views.sale_return_list, name='sale_return_list'),  # ← أولاً
    path('sale-return/create/<slug:sale_slug>/', views.sale_return_create, name='sale_return_create'),
    path('sale-return/<slug:slug>/', views.sale_return_detail, name='sale_return_detail'),  # ← بعد الثوابت
    path('sale-return/update/<slug:slug>/', views.sale_return_update, name='sale_return_update'),
    path('sale-return/delete/<slug:slug>/', views.sale_return_delete, name='sale_return_delete'),
    
    # APIs للمرتجعات
    path('get-sale-items-for-return/<int:sale_id>/', views.get_sale_items_for_return, name='get_sale_items_for_return'),
    path('check-barcode-for-return/<int:product_id>/', views.check_barcode_for_return, name='check_barcode_for_return'),

    # ================ التقارير (القديمة والجديدة) ================
    path('reports/statement/', views.statement_report_view, name='statement_report'),
    path('reports/barcode/', views.barcode_statement_view, name='barcode_statement'),
    
    # التقارير المهمة (الموجودة سابقاً)
    path('reports/unpaid-sales/', views.unpaid_sales_report, name='unpaid_sales_report'),
    path('reports/dead-stock/', views.dead_stock_report, name='dead_stock_report'),

    # التقارير الجديدة
    path('reports/profit/', profit_report_view, name='profit_report'),
    path('reports/sales-by-customer/', sales_by_customer_report, name='sales_by_customer_report'),
    path('reports/purchases-by-supplier/', purchases_by_supplier_report, name='purchases_by_supplier_report'),
    path('reports/daily-summary/', daily_sales_summary_report, name='daily_sales_summary'),
    path('reports/unpaid-invoices/', unpaid_invoices_report, name='unpaid_invoices_report'),

    path('settings/email/', views.email_settings_view, name='email_settings'),




    # ================ المتجر الإلكتروني ================
    
    # واجهة المتجر
    path('store/', views.store_front, name='store_front'),
    
    # لوحة التحكم
    path('store/control/', views.control_store, name='control_store'),
    
    # سلة التسوق
    path('cart/add/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/', views.update_cart_item, name='update_cart_item'),
    path('cart/remove/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/', views.cart_detail, name='cart_detail'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('place-order/', views.place_order_view, name='place_order'),
    
    # إدارة الطلبات
    path('manage/orders/', views.orders_list_view, name='orders_list'),
    path('manage/order/<int:order_id>/', views.order_detail_view, name='order_detail'),
    path('manage/order/<int:order_id>/convert/', views.convert_order_to_invoice, name='convert_order_to_invoice'),
    
    # API: إعدادات المنتجات
    path('api/product/<int:product_id>/update-badge-image/', views.api_update_badge_image, name='api_update_badge_image'),
    path('api/product/<int:product_id>/update-settings/', views.api_update_product_store_settings, name='api_update_product_store_settings'),
    
    # API: البنرات
    path('api/banner/add/', views.api_add_banner, name='api_add_banner'),
    path('api/banner/<int:banner_id>/update/', views.api_update_banner, name='api_update_banner'),
    path('api/banner/delete/<int:banner_id>/', views.delete_banner, name='delete_banner'),
    
    # API: الأقسام الديناميكية
    path('api/sections/add/', views.api_add_section, name='api_add_section'),
    path('api/sections/<int:section_id>/update/', views.api_update_section, name='api_update_section'),
    path('api/sections/<int:section_id>/delete/', views.api_delete_section, name='api_delete_section'),
    path('api/sections/<int:section_id>/add-product/', views.api_add_product_to_section, name='api_add_product_to_section'),
    path('api/sections/<int:section_id>/remove-product/<int:item_id>/', views.api_remove_product_from_section, name='api_remove_product_from_section'),

    path('store/categories/', views.manage_categories, name='manage_categories'),
    path('api/categories/add/', views.api_add_category, name='api_add_category'),
    path('api/categories/<int:cat_id>/update/', views.api_update_category, name='api_update_category'),
    path('api/categories/<int:cat_id>/delete/', views.api_delete_category, name='api_delete_category'),
    path('api/product/<int:product_id>/update-category/', views.api_update_product_category, name='api_update_product_category'),
    #path('api/product/<int:product_id>/update-category/', views.api_update_product_category, name='api_update_product_category'),

    # من اجل اشعار توفر المادة 
    path('stock-notifications/', views.admin_stock_notifications, name='admin_stock_notifications'),
    path('stock-notifications/send/<int:product_id>/', views.admin_send_notification, name='admin_send_notification'),
    path('api/request-notification/', views.api_request_notification, name='api_request_notification'),

    path('notifications/archive/', views.admin_notification_archive, name='notification_archive'),

    path('notifications/undo/', views.admin_undo_archive_notification, name='undo_notification'),



    path('api/flash-deals/', views.api_flash_deals, name='api_flash_deals'),
    path('api/flash-deals/add/', views.api_add_flash_deal, name='api_add_flash_deal'),
    path('api/flash-deals/<int:deal_id>/toggle/', views.api_toggle_flash_deal, name='api_toggle_flash_deal'),
    path('api/flash-deals/<int:deal_id>/delete/', views.api_delete_flash_deal, name='api_delete_flash_deal'),
    path('api/add-announcement/', api_add_announcement, name='api_add_announcement'),



    path('api/add-announcement/', views.api_add_announcement, name='api_add_announcement'),
    path('api/delete-announcement/<int:ann_id>/', views.api_delete_announcement, name='api_delete_announcement'),
    path('api/update-feature/<int:feature_id>/', views.api_update_feature, name='api_update_feature'),


    path('get-product-barcodes/<int:product_id>/', views.get_product_barcodes, name='get_product_barcodes'),


    
    # من اجل كلمة المرور في نظام التسعير 
    path('save-pricing-password/', views.save_pricing_password, name='save_pricing_password'),
    
    path('save-pricing-password/', views.save_pricing_password, name='save_pricing_password'),

    path('test-backup/', views.download_backup, name='download_backup'),
    path('test-restore/', views.upload_restore, name='upload_restore'),



    # مسارات النسخ الاحتياطي - أضفها مع باقي المسارات
    path('backup/', views.backup_page, name='backup_page'),
    path('backup/download/', views.download_backup, name='download_backup'),
    path('backup/server/download/<str:filename>/', views.download_server_backup, name='download_server_backup'),
    path('backup/server/delete/', views.delete_server_backup_view, name='delete_server_backup'),
    path('backup/restore/', views.upload_restore, name='upload_restore'),

    path('backup/factory-reset/', views.factory_reset_system, name='factory_reset_system'),

    path('order-confirmation/<int:order_id>/', views.order_confirmation, name='order_confirmation'),
    
]



