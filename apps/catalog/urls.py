from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'catalog'

router = DefaultRouter()
router.register(r'categories', views.CategoryViewSet, basename='category') # /categories/

# Specific routes must come BEFORE generic slug routes
router.register(r'products/admin', views.AdminProductViewSet, basename='admin-product') # /products/admin/
router.register(r'products/images', views.AdminProductImageViewSet, basename='product-image') # /products/images/

router.register(r'products', views.ProductViewSet, basename='product') # /products/, /products/{slug}/
# This gives /products/images/{pk}/set_primary/ (underscores usually by default)
# We can customize this via @action(url_path='set-primary') which is done.

urlpatterns = [
    path('', include(router.urls)),
]
