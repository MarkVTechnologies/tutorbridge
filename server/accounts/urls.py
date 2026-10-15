from django.urls import path

from accounts import views

urlpatterns = [
    path("csrf/", views.csrf),
    path("signup/", views.signup),
    path("login/", views.login_view),
    path("login/2fa/", views.two_factor_login),
    path("logout/", views.logout_view),
    path("me/", views.me),
    path("me/export/", views.export_my_data),
    path("verify-email/", views.verify_email),
    path("verify-email/resend/", views.resend_email_verification),
    path("phone/send/", views.send_phone_otp),
    path("phone/verify/", views.verify_phone),
    path("password/forgot/", views.forgot_password),
    path("password/reset/", views.reset_password),
    path("2fa/setup/", views.two_factor_setup),
    path("2fa/enable/", views.two_factor_enable),
    path("2fa/verify/", views.two_factor_verify),
    path("2fa/disable/", views.two_factor_disable),
]
