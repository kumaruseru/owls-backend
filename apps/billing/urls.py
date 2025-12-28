from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    # Payment callbacks
    path('vnpay/return/', views.VNPayReturnView.as_view(), name='vnpay_return'),
    path('vnpay/verify/', views.VNPayVerifyAPIView.as_view(), name='vnpay_verify'),
    path('vnpay/ipn/', views.VNPayIPNView.as_view(), name='vnpay_ipn'),
    path('momo/return/', views.MoMoReturnView.as_view(), name='momo_return'),
    path('momo/webhook/', views.MoMoWebhookView.as_view(), name='momo_webhook'),
    path('stripe/webhook/', views.StripeWebhookView.as_view(), name='stripe_webhook'),
    
    # Payment status
    path('status/<uuid:payment_id>/', views.PaymentStatusView.as_view(), name='payment_status'),
    path('stripe/secret/<uuid:payment_id>/', views.StripeClientSecretView.as_view(), name='stripe_secret'),
    
    # Refund (Admin)
    path('refund/<uuid:payment_id>/', views.PaymentRefundView.as_view(), name='refund'),
]
