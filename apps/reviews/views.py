from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Count

from .models import Review
from .serializers import (
    ReviewSerializer,
    ReviewCreateSerializer,
    ReviewUpdateSerializer,
)
from apps.products.models import Product


class ProductReviewsView(generics.ListAPIView):
    """List reviews for a product."""
    
    permission_classes = (permissions.AllowAny,)
    serializer_class = ReviewSerializer
    
    def get_queryset(self):
        product_id = self.kwargs.get('product_id')
        return Review.objects.filter(
            product_id=product_id,
            is_approved=True
        ).select_related('user')
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Calculate statistics
        stats = queryset.aggregate(
            average_rating=Avg('rating'),
            total_reviews=Count('id')
        )
        
        # Rating distribution
        rating_distribution = {}
        for i in range(1, 6):
            rating_distribution[i] = queryset.filter(rating=i).count()
        
        serializer = self.get_serializer(queryset, many=True)
        
        return Response({
            'statistics': {
                'average_rating': round(stats['average_rating'] or 0, 1),
                'total_reviews': stats['total_reviews'],
                'rating_distribution': rating_distribution,
            },
            'reviews': serializer.data
        })


class ReviewListCreateView(generics.ListCreateAPIView):
    """
    List reviews for a product (public) or create a review (authenticated).
    Supports filtering by 'product' query param (slug or ID).
    """
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ReviewCreateSerializer
        return ReviewSerializer
    
    def get_queryset(self):
        queryset = Review.objects.filter(is_approved=True).select_related('user', 'product')
        
        product_param = self.request.query_params.get('product')
        if product_param:
            # Check if param is ID (digit) or Slug
            if product_param.isdigit():
                queryset = queryset.filter(product_id=product_param)
            else:
                queryset = queryset.filter(product__slug=product_param)
        
        # Helper: Calculate stats if needed, but for list view usually we just return list.
        # ProductReviewsView handles stats, but this view is for simple listing.
        
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        
        return Response({
            'message': 'Đã thêm đánh giá!',
            'review': ReviewSerializer(review, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View, update or delete a review."""
    
    permission_classes = (permissions.IsAuthenticated,)
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ReviewUpdateSerializer
        return ReviewSerializer
    
    def get_queryset(self):
        return Review.objects.filter(user=self.request.user)
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response({
            'message': 'Cập nhật thành công!',
            'review': ReviewSerializer(instance, context={'request': request}).data
        })
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        
        return Response({
            'message': 'Đã xóa đánh giá.'
        }, status=status.HTTP_200_OK)


class MyReviewsView(generics.ListAPIView):
    """List current user's reviews."""
    
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = ReviewSerializer
    
    def get_queryset(self):
        return Review.objects.filter(user=self.request.user).select_related('product')

