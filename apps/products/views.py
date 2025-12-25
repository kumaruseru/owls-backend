from rest_framework import generics, filters
from rest_framework.permissions import AllowAny
from django.db.models import Q

from .models import Category, Product
from .serializers import (
    CategorySerializer,
    CategoryListSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
)


class CategoryListView(generics.ListAPIView):
    """List all active categories."""
    
    permission_classes = (AllowAny,)
    serializer_class = CategoryListSerializer
    
    def get_queryset(self):
        # Return only root categories (no parent)
        return Category.objects.filter(is_active=True, parent__isnull=True)


class CategoryDetailView(generics.RetrieveAPIView):
    """Get category details with products."""
    
    permission_classes = (AllowAny,)
    serializer_class = CategorySerializer
    lookup_field = 'slug'
    
    def get_queryset(self):
        return Category.objects.filter(is_active=True)


class ProductListView(generics.ListAPIView):
    """List all active products with search and filter."""
    
    permission_classes = (AllowAny,)
    serializer_class = ProductListSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'short_description']
    ordering_fields = ['price', 'created_at', 'name']
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True).select_related('category')
        
        # Filter by category
        category_slug = self.request.query_params.get('category')
        if category_slug:
            queryset = queryset.filter(
                Q(category__slug=category_slug) | 
                Q(category__parent__slug=category_slug)
            )
        
        # Filter by price range
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        
        # Filter featured products
        is_featured = self.request.query_params.get('featured')
        if is_featured and is_featured.lower() == 'true':
            queryset = queryset.filter(is_featured=True)
        
        # Filter in-stock only
        in_stock = self.request.query_params.get('in_stock')
        if in_stock and in_stock.lower() == 'true':
            queryset = queryset.filter(stock__gt=0)
        
        # Filter on sale
        on_sale = self.request.query_params.get('on_sale')
        if on_sale and on_sale.lower() == 'true':
            queryset = queryset.filter(sale_price__isnull=False)
        
        return queryset


class ProductDetailView(generics.RetrieveAPIView):
    """Get product details."""
    
    permission_classes = (AllowAny,)
    serializer_class = ProductDetailSerializer
    lookup_field = 'slug'
    
    def get_queryset(self):
        return Product.objects.filter(is_active=True).select_related('category').prefetch_related('images')


class FeaturedProductListView(generics.ListAPIView):
    """List featured products."""
    
    permission_classes = (AllowAny,)
    serializer_class = ProductListSerializer
    
    def get_queryset(self):
        return Product.objects.filter(
            is_active=True, 
            is_featured=True
        ).select_related('category')[:8]


class CategoryProductsView(generics.ListAPIView):
    """List products by category."""
    
    permission_classes = (AllowAny,)
    serializer_class = ProductListSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['price', 'created_at', 'name']
    ordering = ['-created_at']
    
    def get_queryset(self):
        category_slug = self.kwargs.get('slug')
        return Product.objects.filter(
            is_active=True,
            category__slug=category_slug
        ).select_related('category') | Product.objects.filter(
            is_active=True,
            category__parent__slug=category_slug
        ).select_related('category')
