from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import UserAddress

User = get_user_model()


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ('email', 'username', 'password', 'password2', 'first_name', 'last_name', 'phone')
    
    def validate_email(self, value):
        from apps.utils.security import InputValidator
        
        # Validate email format
        is_valid, email = InputValidator.validate_email(value)
        if not is_valid:
            raise serializers.ValidationError(email)
        
        if User.objects.filter(email=email, is_deleted=False).exists():
            raise serializers.ValidationError('Email đã được sử dụng')
        return email
    
    def validate_username(self, value):
        from apps.utils.security import InputValidator
        
        # Check for XSS
        if InputValidator.detect_xss(value):
            raise serializers.ValidationError('Tên người dùng chứa ký tự không hợp lệ')
        
        # Check if username is taken by an active (non-deleted) user
        if User.objects.filter(username=value, is_deleted=False).exists():
            raise serializers.ValidationError('Tên người dùng đã được sử dụng')
        return value
    
    def validate_first_name(self, value):
        from apps.utils.security import InputValidator
        if value and InputValidator.detect_xss(value):
            raise serializers.ValidationError('Họ chứa ký tự không hợp lệ')
        return InputValidator.sanitize_html(value) if value else value
    
    def validate_last_name(self, value):
        from apps.utils.security import InputValidator
        if value and InputValidator.detect_xss(value):
            raise serializers.ValidationError('Tên chứa ký tự không hợp lệ')
        return InputValidator.sanitize_html(value) if value else value
    
    def validate_phone(self, value):
        from apps.utils.security import InputValidator
        if value:
            is_valid, result = InputValidator.validate_phone(value)
            if not is_valid:
                raise serializers.ValidationError(result)
            return result
        return value
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Mật khẩu không khớp'})
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    full_address = serializers.ReadOnlyField()
    
    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'first_name', 'last_name', 'full_name',
                  'phone', 'avatar', 'address', 'city', 'district', 'ward', 'full_address',
                  'province_id', 'district_id', 'ward_code',
                  'is_email_verified', 'is_staff', 'is_2fa_enabled', 'date_joined')
        read_only_fields = ('id', 'email', 'is_email_verified', 'is_staff', 'date_joined')


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'phone', 'avatar', 'address', 'city', 'district', 'ward',
                  'province_id', 'district_id', 'ward_code')


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # Check if account is locked or deleted
        from .services import AuthService
        
        email = attrs.get('email', '').lower()
        password = attrs.get('password')
        
        user, error = AuthService.authenticate_user(email, password)
        
        if error:
            raise serializers.ValidationError({'detail': error})
            
        self.user = user  # Ensure user is available on serializer instance
        
        # Check for 2FA
        if user.is_2fa_enabled:
            from django.core.signing import TimestampSigner
            signer = TimestampSigner()
            temp_token = signer.sign(str(user.id))
            
            return {
                'requires_2fa': True,
                'temp_token': temp_token,
                'message': 'Two-factor authentication required'
            }
        
        # Get tokens
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data


class UserAddressSerializer(serializers.ModelSerializer):
    full_address = serializers.ReadOnlyField()
    
    class Meta:
        model = UserAddress
        fields = ('id', 'label', 'recipient_name', 'phone', 'address', 
                  'city', 'district', 'ward', 'is_default', 'full_address')
        read_only_fields = ('id',)


class UserAddressMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for checkout."""
    class Meta:
        model = UserAddress
        fields = ('id', 'label', 'recipient_name', 'phone', 'full_address', 'is_default')
