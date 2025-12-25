from rest_framework import serializers
from .models import Review
from apps.users.serializers import UserSerializer


class ReviewSerializer(serializers.ModelSerializer):
    """Serializer for reviews."""
    
    user_name = serializers.SerializerMethodField()
    user_avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = (
            'id', 'user', 'user_name', 'user_avatar', 'product',
            'rating', 'title', 'comment', 'is_verified_purchase',
            'created_at'
        )
        read_only_fields = ('id', 'user', 'is_verified_purchase', 'created_at')
    
    def get_user_name(self, obj):
        return obj.user.full_name or obj.user.username
    
    def get_user_avatar(self, obj):
        if obj.user.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.user.avatar.url)
        return None


class ReviewCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating reviews."""
    
    class Meta:
        model = Review
        fields = ('product', 'rating', 'title', 'comment')
    
    def validate_product(self, value):
        user = self.context['request'].user
        if Review.objects.filter(user=user, product=value).exists():
            raise serializers.ValidationError("Bạn đã đánh giá sản phẩm này rồi.")
        return value
    
    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Đánh giá phải từ 1 đến 5 sao.")
        return value
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class ReviewUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating reviews."""
    
    class Meta:
        model = Review
        fields = ('rating', 'title', 'comment')
