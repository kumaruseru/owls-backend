from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # Categories
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('categories/<slug:slug>/', views.CategoryDetailView.as_view(), name='category_detail'),
    path('categories/<slug:slug>/products/', views.CategoryProductsView.as_view(), name='category_products'),
    
    # Products
    path('', views.ProductListView.as_view(), name='product_list'),
    path('featured/', views.FeaturedProductListView.as_view(), name='featured_products'),
    path('<slug:slug>/', views.ProductDetailView.as_view(), name='product_detail'),
]
