from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # Payment management
    path('', views.PaymentListView.as_view(), name='payment_list'),
    path('create/', views.CreatePaymentView.as_view(), name='create_payment'),
    path('<uuid:id>/', views.PaymentDetailView.as_view(), name='payment_detail'),
    path('<uuid:payment_id>/status/', views.PaymentStatusView.as_view(), name='payment_status'),
    
    # Refunds
    path('refund/', views.CreateRefundView.as_view(), name='create_refund'),
    
    # Stripe callbacks
    path('stripe/webhook/', views.StripeWebhookView.as_view(), name='stripe_webhook'),
    
    # VNPay callbacks
    path('vnpay/return/', views.VNPayReturnView.as_view(), name='vnpay_return'),
    path('vnpay/ipn/', views.VNPayIPNView.as_view(), name='vnpay_ipn'),
    
    # MoMo callbacks
    path('momo/return/', views.MoMoReturnView.as_view(), name='momo_return'),
    path('momo/webhook/', views.MoMoWebhookView.as_view(), name='momo_webhook'),
]
