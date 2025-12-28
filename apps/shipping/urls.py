from django.urls import path
from . import views

app_name = 'shipping'

urlpatterns = [
    # Basic
    path('providers/', views.ShippingProviderListView.as_view(), name='provider_list'),
    path('track/<str:order_number>/', views.ShipmentTrackingView.as_view(), name='track'),
    
    # GHN Address Data
    path('ghn/provinces/', views.GHNProvincesView.as_view(), name='ghn_provinces'),
    path('ghn/districts/<int:province_id>/', views.GHNDistrictsView.as_view(), name='ghn_districts'),
    path('ghn/wards/<int:district_id>/', views.GHNWardsView.as_view(), name='ghn_wards'),
    
    # GHN Services
    path('ghn/services/', views.GHNServicesView.as_view(), name='ghn_services'),
    path('ghn/calculate-fee/', views.GHNCalculateFeeView.as_view(), name='ghn_calculate_fee'),
    
    # GHN Shipment Management (Admin)
    path('ghn/create/<str:order_number>/', views.GHNCreateShipmentView.as_view(), name='ghn_create'),
    path('ghn/tracking/<str:order_code>/', views.GHNTrackingView.as_view(), name='ghn_tracking'),
    path('ghn/cancel/<str:order_code>/', views.GHNCancelShipmentView.as_view(), name='ghn_cancel'),
    path('ghn/print/<str:order_code>/', views.GHNPrintLabelView.as_view(), name='ghn_print'),
    
    # GHN Webhook (for status sync)
    path('ghn/webhook/', views.GHNWebhookView.as_view(), name='ghn_webhook'),
]
