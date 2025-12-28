from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth import get_user_model
from rest_framework import views, status, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
import requests
from .models import SocialAccount
from .serializers import UserSerializer

User = get_user_model()

class GithubLoginView(views.APIView):
    """
    Redirects to GitHub's OAuth login page.
    Frontend should link to this endpoint or call it and follow redirect.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        client_id = settings.GITHUB_CLIENT_ID
        # Callback URL registered in GitHub App must match strict redirection
        # Frontend handles the callback, so we tell GitHub to redirect to Frontend
        # But wait, typically OAuth flow redirects browser.
        # If we redirect to Frontend Callback, the URI must match what IS configured in GitHub.
        # Assuming http://localhost:3000/auth/callback is configured.
        redirect_uri = f"{settings.FRONTEND_URL}/auth/callback" 
        scope = "user:email"
        
        github_auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scope}"
            f"&state=github"
        )
        return redirect(github_auth_url)


class GithubCallbackView(views.APIView):
    """
    Exchanges authorization code for access token and logs in/creates user.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        code = request.data.get('code')
        if not code:
            return Response({"error": "Code is required"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Exchange code for access token
        token_url = "https://github.com/login/oauth/access_token"
        token_data = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
        }
        headers = {"Accept": "application/json"}
        
        try:
            token_res = requests.post(token_url, data=token_data, headers=headers)
            token_res.raise_for_status()
            token_json = token_res.json()
        except requests.exceptions.RequestException:
             return Response({"error": "Failed to connect to GitHub"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if "error" in token_json:
            return Response({"error": token_json.get("error_description", "Invalid code")}, status=status.HTTP_400_BAD_REQUEST)

        access_token = token_json.get("access_token")

        # 2. Get User Info
        user_url = "https://api.github.com/user"
        auth_headers = {"Authorization": f"token {access_token}"}
        
        try:
            user_res = requests.get(user_url, headers=auth_headers)
            user_res.raise_for_status()
            user_data = user_res.json()
        except requests.exceptions.RequestException:
             return Response({"error": "Failed to fetch user data from GitHub"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 3. Get User Email (if private)
        email = user_data.get('email')
        if not email:
            try:
                emails_res = requests.get("https://api.github.com/user/emails", headers=auth_headers)
                emails_res.raise_for_status()
                emails = emails_res.json()
                # Find primary verified email
                for e in emails:
                    if e.get('primary') and e.get('verified'):
                        email = e.get('email')
                        break
            except Exception:
                pass

        if not email:
            return Response({"error": "GitHub account must have a verified email."}, status=status.HTTP_400_BAD_REQUEST)

        # 4. Login or Register or Link
        uid = str(user_data.get("id"))
        
        # Check if SocialAccount exists
        try:
            social_account = SocialAccount.objects.get(provider='github', uid=uid)
            user = social_account.user
            
            # If user is already authenticated and trying to link -> confirm it matches?
            if request.user.is_authenticated and request.user != user:
                return Response({"error": "This GitHub account is already linked to another user."}, status=status.HTTP_400_BAD_REQUEST)

        except SocialAccount.DoesNotExist:
            if request.user.is_authenticated:
                # Linking to current user
                user = request.user
            else:
                # Login or Register
                try:
                    user = User.objects.get(email=email)
                    return Response(
                        {"error": "Tài khoản đã được đăng ký với email này rồi vui lòng đăng nhập với email đã được đăng ký"}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except User.DoesNotExist:
                    # Create new user
                    username = user_data.get('login')
                    # Ensure username uniqueness if needed, but email is unique
                    if User.objects.filter(username=username).exists():
                            username = f"{username}_{uid}"

                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        first_name=user_data.get('name') or '',
                        avatar=None # Could fetch avatar url
                    )
                    user.is_email_verified = True # Trusted provider
                    user.save()
                
            SocialAccount.objects.create(
                user=user,
                provider='github',
                uid=uid,
                extra_data=user_data
            )
        
        # 5. Generate Tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data
        })


class GoogleLoginView(views.APIView):
    """
    Redirects to Google's OAuth login page.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        client_id = settings.GOOGLE_CLIENT_ID
        redirect_uri = f"{settings.FRONTEND_URL}/auth/callback" 
        scope = "profile email"
        
        google_auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={scope}"
            f"&access_type=offline"
            f"&prompt=consent"
            f"&state=google"
        )
        return redirect(google_auth_url)


class GoogleCallbackView(views.APIView):
    """
    Exchanges authorization code for access token and logs in/creates/links user.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        code = request.data.get('code')
        # If user is linking account, they should send their current access token in Authorization header 
        # (permissions.AllowAny typically, but we check request.user manually if needed? 
        # Actually standard DRF auth middleware runs before view, so request.user is set if token sent)
        
        if not code:
            return Response({"error": "Code is required"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Exchange code for access token
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": f"{settings.FRONTEND_URL}/auth/callback",
        }
        
        try:
            token_res = requests.post(token_url, data=token_data)
            token_res.raise_for_status()
            token_json = token_res.json()
        except requests.exceptions.RequestException:
             return Response({"error": "Failed to connect to Google"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        access_token = token_json.get("access_token")

        # 2. Get User Info
        user_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            user_res = requests.get(user_url, headers=auth_headers)
            user_res.raise_for_status()
            user_data = user_res.json()
        except requests.exceptions.RequestException:
             return Response({"error": "Failed to fetch user data from Google"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        email = user_data.get('email')
        uid = user_data.get('sub')
        
        if not email:
             return Response({"error": "Google account must have an email."}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Login / Register / Link
        
        # Check if already linked
        try:
            social = SocialAccount.objects.get(provider='google', uid=uid)
            user = social.user
            
            # If user is already authenticated and trying to link -> confirm it matches?
            if request.user.is_authenticated and request.user != user:
                return Response({"error": "This Google account is already linked to another user."}, status=status.HTTP_400_BAD_REQUEST)
                
        except SocialAccount.DoesNotExist:
            if request.user.is_authenticated:
                # Linking to current user
                user = request.user
            else:
                # Login or Register
                try:
                    user = User.objects.get(email=email)
                    return Response(
                        {"error": "Tài khoản đã được đăng ký với email này rồi vui lòng đăng nhập với email đã được đăng ký"}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except User.DoesNotExist:
                     # Create new user
                    username = email.split('@')[0]
                    if User.objects.filter(username=username).exists():
                         username = f"{username}_{uid[-4:]}"
                    
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        first_name=user_data.get('given_name', ''),
                        last_name=user_data.get('family_name', ''),
                        avatar=user_data.get('picture') # Django ImageField expects file, url needs processing. Skip for now or handle string.
                        # Note: User model avatar is specific.
                    )
                    user.is_email_verified = True
                    user.save()
            
            # Create Link
            SocialAccount.objects.create(
                user=user,
                provider='google',
                uid=uid,
                extra_data=user_data
            )

        # 4. Generate Tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data
        })


class SocialAccountListView(views.APIView):
    """
    List connected social accounts for the current user.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        accounts = SocialAccount.objects.filter(user=request.user)
        data = [{
            'provider': acc.provider,
            'created_at': acc.created_at,
            'uid': acc.uid
        } for acc in accounts]
        return Response(data)


class DisconnectSocialAccountView(views.APIView):
    """
    Disconnect a social account.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        provider = request.data.get('provider')
        if not provider:
             return Response({"error": "Provider is required"}, status=status.HTTP_400_BAD_REQUEST)
             
        try:
            account = SocialAccount.objects.get(user=request.user, provider=provider)
            account.delete()
            return Response({"message": f"{provider} account disconnected."})
        except SocialAccount.DoesNotExist:
            return Response({"error": "Account not found or already disconnected."}, status=status.HTTP_404_NOT_FOUND)
