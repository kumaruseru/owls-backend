from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Max, Min, F, Case, When, DecimalField, Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
import operator
from functools import reduce

from .models import Category, Product, ProductImage
from .serializers import CategorySerializer, ProductListSerializer, ProductDetailSerializer, ProductCreateSerializer
from .filters import ProductFilter, ProductOrderingFilter
from .services import ProductExportService

class ProductPagination(PageNumberPagination):
    page_size = 9
    page_size_query_param = 'page_size'
    max_page_size = 100

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing and retrieving categories.
    """
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    lookup_field = 'slug'

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for public product listing and details.
    """
    serializer_class = ProductListSerializer
    pagination_class = ProductPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, ProductOrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description', 'brand']
    ordering_fields = ['price', 'created_at', 'name']
    lookup_field = 'slug'

    def get_queryset(self):
        # Use Custom Manager for cleaner logic
        queryset = Product.objects.all() if self.request.user.is_staff else Product.objects.active()
        return queryset.with_effective_price().select_related('category').prefetch_related('images')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

    @action(detail=False, methods=['get'])
    def filters(self, request):
        """
        API endpoint returns filtering options (brands, colors, price range).
        """
        # Start with base active products & Apply Context Filters (Category & Search)
        # We leverage the same SearchFilter backend logic if possible, or simple Q logic if simple.
        # Here we manually apply to ensure we get context-aware facets.
        
        products = Product.objects.active()

        category_slug = request.query_params.get('category__slug')
        if category_slug:
            products = products.filter(category__slug=category_slug)
        
        search_query = request.query_params.get('search')
        if search_query:
            # Replicate search logic consistent with list view
            search_fields = ['name__icontains', 'description__icontains', 'brand__icontains']
            q_objects = [Q(**{field: search_query}) for field in search_fields]
            products = products.filter(reduce(operator.or_, q_objects))

        # Use efficient aggregation with effective_price from Manager if needed, 
        # but aggregate() on annotated queryset works best if annotation is present.
        # Since we started fresh from objects.active(), we need annotation again.
        products = products.with_effective_price()

        # Aggregate price range based on effective price
        price_stats = products.aggregate(
            min_price=Min('effective_price'), 
            max_price=Max('effective_price')
        )
        
        # Get distinct brands and colors based on Context-filtered products
        brands = products.exclude(brand__isnull=True).exclude(brand='').values_list('brand', flat=True).distinct().order_by('brand')
        colors = products.exclude(color__isnull=True).exclude(color='').values_list('color', flat=True).distinct().order_by('color')
        
        return Response({
            'min_price': price_stats['min_price'] or 0,
            'max_price': price_stats['max_price'] or 0,
            'brands': list(brands),
            'colors': list(colors)
        })

class AdminProductViewSet(viewsets.ModelViewSet):
    """
    Admin ViewSet for full CRUD operations on Products.
    """
    permission_classes = [permissions.IsAdminUser]
    queryset = Product.objects.all().order_by('-created_at')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'sku']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProductCreateSerializer
        elif self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        """
        Export products to Excel.
        """
        queryset = self.filter_queryset(self.get_queryset())
        return ProductExportService.export_to_excel(queryset)

class AdminProductImageViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAdminUser]

    @action(detail=True, methods=['post'], url_path='set-primary')
    def set_primary(self, request, pk=None):
        """
        Set an image as primary. PK is the Image ID.
        """
        image = get_object_or_404(ProductImage, pk=pk)
        ProductImage.objects.filter(product=image.product).update(is_primary=False)
        image.is_primary = True
        image.save()
        return Response({'status': 'success', 'message': 'Image set as primary'})
