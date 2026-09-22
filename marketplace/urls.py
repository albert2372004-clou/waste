from django.urls import path
from . import views

urlpatterns = [
    # Catalog & Product Detail
    path("", views.index, name="index"),
    path("marketplace/", views.index, name="marketplace_catalog"),
    path("product/<int:pk>/", views.product_detail, name="product_detail"),

    # Supplier / Seller Dashboard & Listing CRUD
    path("dashboard/", views.dashboard, name="dashboard"),
    path("supplier/dashboard/", views.dashboard, name="supplier_dashboard"),
    path("supplier/listings/create/", views.listing_create, name="listing_create"),
    path("supplier/listings/<int:pk>/edit/", views.listing_edit, name="listing_edit"),
    path("supplier/listings/<int:pk>/delete/", views.listing_delete, name="listing_delete"),
    path("supplier/listings/<int:pk>/apply-rate/", views.apply_recommended_price, name="apply_recommended_price"),
    path("supplier/requests/<int:pk>/respond/", views.request_respond, name="request_respond"),
    path("supplier/certificates/upload/", views.certificate_upload, name="certificate_upload"),

    # Live Pricing API
    path("api/calculate-rate/", views.calculate_price_api, name="calculate_price_api"),

    # Batch Cart & Multi-Supplier Aggregation
    path("cart/", views.cart_view, name="cart_view"),
    path("batch-cart/", views.cart_view, name="batch_cart"),
    path("cart/add/<int:pk>/", views.cart_add, name="cart_add"),
    path("cart/auto-fulfill/", views.cart_auto_fulfill, name="cart_auto_fulfill"),
    path("cart/remove/<int:pk>/", views.cart_remove, name="cart_remove"),
    path("cart/checkout/", views.cart_checkout, name="cart_checkout"),
    path("checkout/<int:pk>/", views.checkout, name="checkout"),

    # Standard Shopping Cart (Flipkart/Amazon Style Multi-Product)
    path("cart/standard/add/<int:pk>/", views.standard_cart_add, name="standard_cart_add"),
    path("cart/standard/update/<int:pk>/", views.standard_cart_update, name="standard_cart_update"),
    path("cart/standard/remove/<int:pk>/", views.standard_cart_remove, name="standard_cart_remove"),
    path("cart/standard/checkout/", views.standard_cart_checkout, name="standard_cart_checkout"),

    # Buyer Orders
    path("buyer/orders/", views.buyer_orders, name="buyer_orders"),

    # Reporting & Fake Listing Detection
    path("report/<int:pk>/", views.report_listing, name="report_listing"),

    # AI / Certificate Extraction API
    path("api/extract-cert/", views.extract_certificate_api, name="extract_certificate_api"),

    # Circular Funding & Innovation Grants
    path("funding/", views.funding_list, name="funding_list"),
    path("funding/<int:pk>/pledge/", views.funding_pledge, name="funding_pledge"),

    # Administration Control Panels
    path("admin-dashboard/", views.custom_admin_dashboard, name="custom_admin_dashboard"),
    path("verification/", views.verification_panel, name="verification_panel"),
]
