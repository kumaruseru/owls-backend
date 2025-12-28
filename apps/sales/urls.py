from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Cart
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/add/', views.CartAddView.as_view(), name='cart_add'),
    path('cart/clear/', views.CartClearView.as_view(), name='cart_clear'),
    path('cart/items/<int:pk>/', views.CartItemView.as_view(), name='cart_item'),
    
    # Checkout & Orders
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('orders/', views.OrderListView.as_view(), name='order_list'),
    path('orders/<str:order_number>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('orders/<str:order_number>/cancel/', views.OrderCancelView.as_view(), name='order_cancel'),
    
    # Admin
    path('admin/orders/', views.AdminOrderListView.as_view(), name='admin_order_list'),
    path('admin/orders/<str:order_number>/', views.AdminOrderDetailView.as_view(), name='admin_order_detail'),
    path('admin/orders/<str:order_number>/status/', views.AdminOrderStatusUpdateView.as_view(), name='admin_order_status'),
    path('admin/dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
]
