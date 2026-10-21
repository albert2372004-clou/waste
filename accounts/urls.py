from django.urls import path
from . import views


urlpatterns = [

    path(
        'signup/',
        views.signup,
        name='signup'
    ),

    path(
        'login/',
        views.user_login,
        name='login'
    ),

    path(
        'logout/',
        views.user_logout,
        name='logout'
    ),
    path(
        'verify-otp/',
        views.verify_otp,
        name='verify_otp'
    ),
    path(
        'resend-otp/',
        views.resend_otp,
        name='resend_otp'
    ),
    path(
        'switch-mode/<str:mode>/',
        views.switch_mode,
        name='switch_mode'
    ),
    path(
        'dashboard/',
        views.dashboard,
        name='dashboard'
    ),
    path(
        'forgot-password/',
        views.forgot_password,
        name='forgot_password'
    ),
    path(
        'reset-password-otp/',
        views.reset_password_otp,
        name='reset_password_otp'
    ),
    path(
        'set-new-password/',
        views.set_new_password,
        name='set_new_password'
    ),
    path(
        'resend-reset-otp/',
        views.resend_reset_otp,
        name='resend_reset_otp'
    ),
    path(
        'profile/',
        views.profile_view,
        name='profile'
    ),
    # Company Location & Godown / Warehouse Management
    path('locations/', views.location_list, name='location_list'),
    path('locations/create/', views.location_create, name='location_create'),
    path('locations/<int:pk>/edit/', views.location_edit, name='location_edit'),
    path('locations/<int:pk>/delete/', views.location_delete, name='location_delete'),
    path('locations/<int:pk>/set-primary/', views.location_set_primary, name='location_set_primary'),
]
