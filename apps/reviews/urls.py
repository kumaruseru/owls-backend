from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    path('product/<int:product_id>/', views.ProductReviewsView.as_view(), name='product_reviews'),
    path('', views.ReviewListCreateView.as_view(), name='review_list_create'),
    path('my/', views.MyReviewsView.as_view(), name='my_reviews'),
    path('<int:pk>/', views.ReviewDetailView.as_view(), name='review_detail'),
]

