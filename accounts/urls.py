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
]