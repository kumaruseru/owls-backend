from rest_framework import views, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from django.contrib.auth import get_user_model
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from rest_framework_simplejwt.tokens import RefreshToken

from .services_2fa import TwoFactorService
from .serializers_2fa import Confirm2FASerializer, Login2FASerializer, Disable2FASerializer
from .serializers import UserSerializer

User = get_user_model()

class Enable2FAView(views.APIView):
    """
    Step 1: Init 2FA Setup.
    Generates secret and returns QR code.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        if user.is_2fa_enabled:
            return Response({"error": "2FA is already enabled."}, status=status.HTTP_400_BAD_REQUEST)

        # Generate or retrieve pending secret
        if not user.two_factor_secret:
            secret = TwoFactorService.generate_secret()
            user.two_factor_secret = secret
            user.save(update_fields=['two_factor_secret'])
        else:
            secret = user.two_factor_secret

        otp_uri = TwoFactorService.get_provisioning_uri(user, secret)
        qr_code = TwoFactorService.generate_qr_code(otp_uri)

        return Response({
            "secret": secret,
            "qr_code": qr_code,
            "otp_uri": otp_uri
        })

class Confirm2FAView(views.APIView):
    """
    Step 2: Confirm 2FA Setup.
    Verifies code => Enables 2FA => Returns Backup Codes.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = '2fa_confirm'

    def post(self, request):
        serializer = Confirm2FASerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        code = serializer.validated_data['code']

        if not user.two_factor_secret:
            return Response({"error": "No 2FA setup started."}, status=status.HTTP_400_BAD_REQUEST)

        if TwoFactorService.verify_totp(user.two_factor_secret, code):
            # Generate backup codes
            backup_codes = TwoFactorService.generate_backup_codes()
            
            user.is_2fa_enabled = True
            user.two_factor_method = 'totp'
            user.backup_codes = backup_codes # Save backup codes
            user.save(update_fields=['is_2fa_enabled', 'two_factor_method', 'backup_codes'])
            
            return Response({
                "message": "2FA successfully enabled.",
                "backup_codes": backup_codes,
                "warning": "Save these backup codes in a safe place. You won't see them again."
            })
        
        return Response({"error": "Invalid OTP code."}, status=status.HTTP_400_BAD_REQUEST)


class Login2FAView(views.APIView):
    """
    Step 2 of Login: Verify TOTP, Email OTP, or Backup Code.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = '2fa_login'

    def post(self, request):
        serializer = Login2FASerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        temp_token = serializer.validated_data['temp_token']
        code = serializer.validated_data.get('code')
        backup_code = serializer.validated_data.get('backup_code')

        # Verify Session Token
        signer = TimestampSigner()
        try:
            user_id = signer.unsign(temp_token, max_age=300) # 5 mins
            user = User.objects.get(id=user_id)
        except (BadSignature, SignatureExpired, User.DoesNotExist):
            return Response({"error": "Invalid or expired login session."}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_2fa_enabled:
             return Response({"error": "2FA not enabled for this user."}, status=status.HTTP_400_BAD_REQUEST)

        # Verify Credential
        is_valid = False
        
        # 1. Try TOTP or Email OTP (code field used for both)
        if code:
            # Check which method user prefers or try both?
            # Safer to try both or rely on what was expected.
            # But here we just check valid logic.
            
            # Try TOTP first
            if TwoFactorService.verify_totp(user.two_factor_secret, code):
                is_valid = True
            # Try Email OTP
            elif TwoFactorService.verify_email_otp(user, code):
                is_valid = True
            else:
                 return Response({"error": "Invalid authentication code."}, status=status.HTTP_400_BAD_REQUEST)
        
        # 2. Try Backup Code
        elif backup_code:
            if TwoFactorService.verify_backup_code(user, backup_code):
                is_valid = True
            else:
                 return Response({"error": "Invalid or used backup code."}, status=status.HTTP_400_BAD_REQUEST)

        if is_valid:
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
            })
            
        return Response({"error": "Authentication failed."}, status=status.HTTP_400_BAD_REQUEST)


class Send2FAEmailView(views.APIView):
    """
    Request an Email OTP during login or setup.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = '2fa_email'

    def post(self, request):
        temp_token = request.data.get('temp_token')
        
        if not temp_token:
            return Response({"error": "temp_token is required"}, status=status.HTTP_400_BAD_REQUEST)

        signer = TimestampSigner()
        try:
            user_id = signer.unsign(temp_token, max_age=300)
            user = User.objects.get(id=user_id)
        except (BadSignature, SignatureExpired, User.DoesNotExist):
            return Response({"error": "Invalid session."}, status=status.HTTP_400_BAD_REQUEST)

        if TwoFactorService.generate_email_otp(user):
            return Response({"message": "Email OTP sent successfully."})
        
        return Response({"error": "Failed to send email."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BackupCodesView(views.APIView):
    """
    View or regenerate backup codes. Protected by password.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        password = request.data.get('password')
        action = request.data.get('action', 'view') # view or regenerate

        if not password or not request.user.check_password(password):
             return Response({"error": "Invalid password."}, status=status.HTTP_400_BAD_REQUEST)
             
        if not request.user.is_2fa_enabled:
            return Response({"error": "2FA is not enabled."}, status=status.HTTP_400_BAD_REQUEST)

        if action == 'regenerate':
             backup_codes = TwoFactorService.generate_backup_codes()
             request.user.backup_codes = backup_codes
             request.user.save(update_fields=['backup_codes'])
             return Response({"backup_codes": backup_codes, "message": "Backup codes regenerated."})
        
        # Default: view
        return Response({"backup_codes": request.user.backup_codes})


class Disable2FAView(views.APIView):
    """
    Disable 2FA. Requires password confirmation.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = '2fa_disable'

    def post(self, request):
        serializer = Disable2FASerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        user = request.user
        password = serializer.validated_data['password']

        if not user.is_2fa_enabled:
            return Response({"error": "2FA is not enabled."}, status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(password):
            return Response({"error": "Invalid password."}, status=status.HTTP_400_BAD_REQUEST)

        # Reset 2FA fields
        user.is_2fa_enabled = False
        user.two_factor_secret = None
        user.two_factor_method = None
        user.backup_codes = [] # Clear backup codes
        user.save(update_fields=['is_2fa_enabled', 'two_factor_secret', 'two_factor_method', 'backup_codes'])

        return Response({"message": "2FA has been disabled."})
