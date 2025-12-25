from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings

from .serializers import (
    UserRegisterSerializer,
    UserSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
)
from .email_service import EmailService

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """API view for user registration with email verification."""
    
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = UserRegisterSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Send verification email
        uid, token = EmailService.generate_verification_token(user)
        frontend_url = request.data.get('frontend_url', 'http://localhost:3000')
        verification_url = f"{frontend_url}/verify-email/{uid}/{token}/"
        
        try:
            EmailService.send_verification_email(user, verification_url)
        except Exception:
            pass  # Don't fail registration if email fails
        
        # Generate tokens for the new user
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'message': 'Đăng ký thành công! Vui lòng kiểm tra email để xác thực tài khoản.',
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    """API view for email verification."""
    
    permission_classes = (permissions.AllowAny,)
    
    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({
                'error': 'Link xác thực không hợp lệ.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if default_token_generator.check_token(user, token):
            if user.is_email_verified:
                return Response({
                    'message': 'Email đã được xác thực trước đó.'
                })
            
            user.is_email_verified = True
            user.save()
            
            return Response({
                'message': 'Xác thực email thành công!'
            })
        
        return Response({
            'error': 'Link xác thực đã hết hạn hoặc không hợp lệ.'
        }, status=status.HTTP_400_BAD_REQUEST)


class ResendVerificationEmailView(APIView):
    """API view for resending verification email."""
    
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request):
        user = request.user
        
        if user.is_email_verified:
            return Response({
                'message': 'Email đã được xác thực.'
            })
        
        uid, token = EmailService.generate_verification_token(user)
        frontend_url = request.data.get('frontend_url', 'http://localhost:3000')
        verification_url = f"{frontend_url}/verify-email/{uid}/{token}/"
        
        if EmailService.send_verification_email(user, verification_url):
            return Response({
                'message': 'Email xác thực đã được gửi lại.'
            })
        
        return Response({
            'error': 'Không thể gửi email. Vui lòng thử lại sau.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ForgotPasswordView(APIView):
    """API view for requesting password reset."""
    
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request):
        email = request.data.get('email')
        
        if not email:
            return Response({
                'error': 'Vui lòng nhập email.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal if user exists
            return Response({
                'message': 'Nếu email tồn tại, chúng tôi đã gửi link đặt lại mật khẩu.'
            })
        
        uid, token = EmailService.generate_password_reset_token(user)
        frontend_url = request.data.get('frontend_url', 'http://localhost:3000')
        reset_url = f"{frontend_url}/reset-password/{uid}/{token}/"
        
        EmailService.send_password_reset_email(user, reset_url)
        
        return Response({
            'message': 'Nếu email tồn tại, chúng tôi đã gửi link đặt lại mật khẩu.'
        })


class ResetPasswordView(APIView):
    """API view for resetting password with token."""
    
    permission_classes = (permissions.AllowAny,)
    
    def post(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({
                'error': 'Link đặt lại mật khẩu không hợp lệ.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not default_token_generator.check_token(user, token):
            return Response({
                'error': 'Link đặt lại mật khẩu đã hết hạn.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        new_password = request.data.get('new_password')
        new_password2 = request.data.get('new_password2')
        
        if not new_password or not new_password2:
            return Response({
                'error': 'Vui lòng nhập mật khẩu mới.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if new_password != new_password2:
            return Response({
                'error': 'Mật khẩu không khớp.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if len(new_password) < 8:
            return Response({
                'error': 'Mật khẩu phải có ít nhất 8 ký tự.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user.set_password(new_password)
        user.save()
        
        return Response({
            'message': 'Đặt lại mật khẩu thành công! Bạn có thể đăng nhập với mật khẩu mới.'
        })


class ProfileView(generics.RetrieveUpdateAPIView):
    """API view for viewing and updating user profile."""
    
    permission_classes = (permissions.IsAuthenticated,)
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response({
            'message': 'Cập nhật thông tin thành công!',
            'user': UserSerializer(instance).data
        })


class ChangePasswordView(generics.UpdateAPIView):
    """API view for changing password."""
    
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = ChangePasswordSerializer
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = self.get_object()
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        return Response({
            'message': 'Đổi mật khẩu thành công!'
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """API view for logout (blacklist refresh token)."""
    
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return Response({
                'message': 'Đăng xuất thành công!'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'error': 'Token không hợp lệ.'
            }, status=status.HTTP_400_BAD_REQUEST)


class LoginThrottle:
    """Custom throttle for login endpoint to prevent brute force."""
    scope = 'login'


from rest_framework.throttling import AnonRateThrottle
from .serializers import CustomTokenObtainPairSerializer


class LoginAnonRateThrottle(AnonRateThrottle):
    """Strict throttle for login attempts."""
    rate = '5/min'


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Token obtain view with email-based login and strict throttling."""
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginAnonRateThrottle]
