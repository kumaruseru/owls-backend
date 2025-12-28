from django.urls import path
from . import views

app_name = 'marketing'

urlpatterns = [
    path('coupons/validate/', views.CouponValidateView.as_view(), name='coupon_validate'),
    path('banners/', views.BannerListView.as_view(), name='banner_list'),
]
