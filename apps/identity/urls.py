from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views, views_2fa, views_social

app_name = 'identity'

urlpatterns = [
    # Auth
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('login/2fa/', views_2fa.Login2FAView.as_view(), name='login_2fa'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Email verification
    path('verify-email/<str:uidb64>/<str:token>/', views.VerifyEmailView.as_view(), name='verify_email'),
    path('resend-verification/', views.ResendVerificationEmailView.as_view(), name='resend_verification'),
    
    # Password
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/<str:uidb64>/<str:token>/', views.ResetPasswordView.as_view(), name='reset_password'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    
    # Profile
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('delete-account/', views.DeleteAccountView.as_view(), name='delete_account'),
    
    # 2FA
    path('2fa/enable/', views_2fa.Enable2FAView.as_view(), name='enable_2fa'),
    path('2fa/send-email/', views_2fa.Send2FAEmailView.as_view(), name='send_2fa_email'),
    path('2fa/backup-codes/', views_2fa.BackupCodesView.as_view(), name='backup_codes'),
    path('2fa/confirm/', views_2fa.Confirm2FAView.as_view(), name='confirm_2fa'),
    path('2fa/disable/', views_2fa.Disable2FAView.as_view(), name='disable_2fa'),

    # Social Auth
    path('social/github/', views_social.GithubLoginView.as_view(), name='github_login'),
    path('social/github/callback/', views_social.GithubCallbackView.as_view(), name='github_callback'),
    
    path('social/google/', views_social.GoogleLoginView.as_view(), name='google_login'),
    path('social/google/callback/', views_social.GoogleCallbackView.as_view(), name='google_callback'),
    
    path('social/accounts/', views_social.SocialAccountListView.as_view(), name='social_account_list'),
    path('social/disconnect/', views_social.DisconnectSocialAccountView.as_view(), name='disconnect_social_account'),
    
    # Addresses
    path('addresses/', views.UserAddressListCreateView.as_view(), name='address_list'),
    path('addresses/<int:pk>/', views.UserAddressDetailView.as_view(), name='address_detail'),
    
    # Admin
    path('admin/users/', views.UserListAdminView.as_view(), name='admin_user_list'),
    path('admin/users/<uuid:pk>/', views.UserDetailAdminView.as_view(), name='admin_user_detail'),
]
