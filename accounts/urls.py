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
        'profile/',
        views.profile_view,
        name='profile'
    ),
]