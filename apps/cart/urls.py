from django.urls import path
from . import views

app_name = 'cart'

urlpatterns = [
    path('', views.CartView.as_view(), name='cart'),
    path('add/', views.AddToCartView.as_view(), name='add_to_cart'),
    path('update/', views.UpdateCartItemView.as_view(), name='update_cart_item'),
    path('remove/', views.RemoveFromCartView.as_view(), name='remove_from_cart'),
    path('clear/', views.ClearCartView.as_view(), name='clear_cart'),
    path('bulk-update/', views.BulkUpdateCartView.as_view(), name='bulk_update_cart'),
]
