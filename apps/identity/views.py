from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.throttling import AnonRateThrottle
from django.contrib.auth import get_user_model
from .serializers import (
    UserRegisterSerializer, UserSerializer, 
    UserUpdateSerializer, ChangePasswordSerializer,
    CustomTokenObtainPairSerializer, UserAddressSerializer
)
from .services import EmailService, AuthService
from .models import UserAddress

User = get_user_model()


class LoginThrottle(AnonRateThrottle):
    """Strict throttle for login attempts."""
    rate = '60/min'


class RegisterThrottle(AnonRateThrottle):
    """Throttle for registration - prevent mass account creation."""
    rate = '10/hour'


class RegisterView(generics.CreateAPIView):
    """User registration with email verification."""
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = UserRegisterSerializer
    throttle_classes = [RegisterThrottle]  # Security: rate limit registration
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Send verification email
        EmailService.send_verification_email(user, request)
        
        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'Đăng ký thành công. Vui lòng kiểm tra email để xác thực tài khoản.',
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    """Login with email and security checks."""
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        # 1. Check Maintenance Mode
        from apps.core.models import SiteConfig
        config = SiteConfig.load()
        
        # 2. If Maintenance is ON, we need to peek at the user before issuing tokens
        if config.maintenance_mode:
            # We can use the serializer to validate credentials without returning tokens yet
            serializer = self.get_serializer(data=request.data)
            
            try:
                serializer.is_valid(raise_exception=True)
                user = serializer.user
                
                if not user.is_staff and not user.is_superuser:
                    return Response(
                        {"detail": "Hệ thống đang bảo trì. Chỉ quản trị viên mới có quyền đăng nhập."},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE
                    )
            except Exception as e:
                # If validation fails (wrong password), let the standard flow handle it or return error
                # But to maintain standard behavior for wrong passwords, we let super().post handle it
                # ONLY if we want to hide that maintenance is on from bad actors? 
                # No, better to fail early if credentials are bad, or fail late if maintenance.
                # Re-raising exception to let standard error handling work
                raise e

        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    """Logout and blacklist refresh token."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return Response({'message': 'Đăng xuất thành công'}, status=status.HTTP_200_OK)
        except Exception:
            return Response({'error': 'Token không hợp lệ'}, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmailView(APIView):
    """Verify email with token."""
    permission_classes = (permissions.AllowAny,)
    
    def get(self, request, uidb64, token):
        user, error = AuthService.verify_email_token(uidb64, token)
        
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
        
        if user.is_email_verified:
            return Response({'message': 'Email đã được xác thực trước đó'})
        
        user.verify_email()
        return Response({'message': 'Xác thực email thành công'})


class ResendVerificationEmailView(APIView):
    """Resend verification email."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def post(self, request):
        user = request.user
        
        if user.is_email_verified:
            return Response({'message': 'Email đã được xác thực'})
        
        success = EmailService.send_verification_email(user, request)
        if success:
            return Response({'message': 'Email xác thực đã được gửi lại'})
        return Response({'error': 'Không thể gửi email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ForgotPasswordView(APIView):
    """Request password reset email."""
    permission_classes = (permissions.AllowAny,)
    throttle_classes = [LoginThrottle]
    
    def post(self, request):
        email = request.data.get('email')
        
        try:
            user = User.objects.get(email=email, is_deleted=False)
            EmailService.send_password_reset_email(user, request)
        except User.DoesNotExist:
            pass  # Don't reveal if email exists
        
        return Response({'message': 'Nếu email tồn tại, bạn sẽ nhận được link đặt lại mật khẩu'})


class ResetPasswordView(APIView):
    """Reset password with token."""
    permission_classes = (permissions.AllowAny,)
    throttle_classes = [LoginThrottle]  # Security: rate limit password reset
    
    def post(self, request, uidb64, token):
        new_password = request.data.get('password')
        
        if not new_password or len(new_password) < 8:
            return Response({'error': 'Mật khẩu phải có ít nhất 8 ký tự'}, status=status.HTTP_400_BAD_REQUEST)
        
        user, error = AuthService.reset_password(uidb64, token, new_password)
        
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({'message': 'Đặt lại mật khẩu thành công'})


class ProfileView(generics.RetrieveUpdateAPIView):
    """View and update user profile."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_object(self):
        return self.request.user


class ChangePasswordView(generics.UpdateAPIView):
    """Change password for authenticated user."""
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = ChangePasswordSerializer
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = self.get_object()
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({'error': 'Mật khẩu cũ không đúng'}, status=status.HTTP_400_BAD_REQUEST)
        
        from django.utils import timezone
        user.set_password(serializer.validated_data['new_password'])
        user.last_password_change = timezone.now()
        user.save()
        
        return Response({'message': 'Đổi mật khẩu thành công'}, status=status.HTTP_200_OK)


class DeleteAccountView(APIView):
    """Soft delete user account."""
    permission_classes = (permissions.IsAuthenticated,)
    
    def delete(self, request):
        password = request.data.get('password')
        
        if not password:
            return Response({'error': 'Vui lòng nhập mật khẩu'}, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        if not user.check_password(password):
            return Response({'error': 'Mật khẩu không đúng'}, status=status.HTTP_400_BAD_REQUEST)
        
        user.soft_delete()
        
        # Blacklist all tokens
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            tokens = OutstandingToken.objects.filter(user=user)
            for token in tokens:
                BlacklistedToken.objects.get_or_create(token=token)
        except Exception:
            pass
        
        return Response({'message': 'Tài khoản đã được xóa'}, status=status.HTTP_200_OK)


# User Address Views
class UserAddressListCreateView(generics.ListCreateAPIView):
    """List and create user addresses."""
    serializer_class = UserAddressSerializer
    permission_classes = (permissions.IsAuthenticated,)
    
    def get_queryset(self):
        return UserAddress.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class UserAddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, delete user address."""
    serializer_class = UserAddressSerializer
    permission_classes = (permissions.IsAuthenticated,)
    
    def get_queryset(self):
        return UserAddress.objects.filter(user=self.request.user)


# Admin Views
class UserListAdminView(generics.ListAPIView):
    """Admin: List all users."""
    queryset = User.objects.filter(is_deleted=False).order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAdminUser,)
    

class UserDetailAdminView(generics.RetrieveUpdateDestroyAPIView):
    """Admin: Manage individual user."""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAdminUser,)
