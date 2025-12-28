from rest_framework import serializers
from .models import Coupon, Banner


class CouponSerializer(serializers.ModelSerializer):
    is_valid = serializers.ReadOnlyField()
    
    class Meta:
        model = Coupon
        fields = ('id', 'code', 'description', 'discount_type', 'discount_value',
                  'min_order_amount', 'max_discount', 'valid_until', 'is_valid')


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = ('id', 'title', 'subtitle', 'image', 'link')
