from django.urls import path
from . import views

app_name = 'social'

urlpatterns = [
    path('products/<slug:product_slug>/reviews/', views.ProductReviewListView.as_view(), name='product_reviews'),
    path('reviews/', views.ReviewCreateView.as_view(), name='review_create'),
    path('reviews/<int:pk>/', views.ReviewDetailView.as_view(), name='review_detail'),
]
