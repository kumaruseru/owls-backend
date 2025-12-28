import django_filters
from django.db.models import Q
from .models import Product

class ProductFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(method='filter_min_price')
    max_price = django_filters.NumberFilter(method='filter_max_price')
    
    # Custom Filter for comma-separated string IN lookup
    class CharInFilter(django_filters.BaseInFilter, django_filters.CharFilter):
        pass

    brand = CharInFilter(lookup_expr='in')
    category__slug = django_filters.CharFilter(field_name='category__slug')
    stock_status = django_filters.CharFilter(method='filter_stock_status')
    
    class Meta:
        model = Product
        fields = ['category', 'is_active', 'is_featured', 'brand', 'category__slug']

    def filter_min_price(self, queryset, name, value):
        if value is None:
            return queryset
        # If sale_price is set (and > 0), use it; otherwise use price
        return queryset.filter(
            Q(sale_price__gt=0, sale_price__gte=value) | 
            Q(Q(sale_price__isnull=True) | Q(sale_price=0), price__gte=value)
        )

    def filter_max_price(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(
            Q(sale_price__gt=0, sale_price__lte=value) | 
            Q(Q(sale_price__isnull=True) | Q(sale_price=0), price__lte=value)
        )

    def filter_stock_status(self, queryset, name, value):
        if value == 'out_of_stock':
            return queryset.filter(stock=0)
        elif value == 'low_stock':
            return queryset.filter(stock__gt=0, stock__lte=5)
        elif value == 'in_stock':
            return queryset.filter(stock__gt=0)
        return queryset

from rest_framework import filters

class ProductOrderingFilter(filters.OrderingFilter):
    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        
        if ordering:
            new_ordering = []
            for field in ordering:
                if field == 'price':
                    new_ordering.append('effective_price')
                elif field == '-price':
                    new_ordering.append('-effective_price')
                else:
                    new_ordering.append(field)
            return new_ordering
        
        # Default ordering
        return ordering
