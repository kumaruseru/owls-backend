"""Identity app models - User and authentication related models."""
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Custom User model với UUID primary key và các field bổ sung cho e-commerce."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    
    # Address (text display)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    ward = models.CharField(max_length=100, blank=True)
    
    # GHN Address IDs (for API sync)
    province_id = models.IntegerField(null=True, blank=True, help_text="GHN Province ID")
    district_id = models.IntegerField(null=True, blank=True, help_text="GHN District ID")
    ward_code = models.CharField(max_length=20, blank=True, help_text="GHN Ward Code")
    
    # Verification
    is_email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    
    # Security
    is_2fa_enabled = models.BooleanField(default=False)
    two_factor_secret = models.CharField(max_length=32, blank=True, null=True, help_text="Secret key for TOTP 2FA")
    two_factor_method = models.CharField(
        max_length=10, 
        choices=[('totp', 'Authenticator App'), ('email', 'Email OTP')],
        default='totp',
        null=True,
        blank=True
    )
    backup_codes = models.JSONField(default=list, blank=True, help_text="List of one-time backup codes")
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_password_change = models.DateTimeField(null=True, blank=True)
    
    # Soft delete
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    class Meta:
        verbose_name = 'Người dùng'
        verbose_name_plural = 'Người dùng'
        ordering = ['-date_joined']
    
    def __str__(self):
        return self.email
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username
    
    @property
    def full_address(self):
        parts = [self.address, self.ward, self.district, self.city]
        return ', '.join(filter(None, parts))
    
    @property
    def is_locked(self):
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False
    
    def record_failed_login(self):
        """Record failed login attempt and lock account if threshold exceeded."""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=30)
        self.save(update_fields=['failed_login_attempts', 'locked_until'])
    
    def reset_failed_logins(self):
        """Reset failed login counter on successful login."""
        if self.failed_login_attempts > 0:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.save(update_fields=['failed_login_attempts', 'locked_until'])
    
    def verify_email(self):
        """Mark email as verified."""
        self.is_email_verified = True
        self.email_verified_at = timezone.now()
        self.save(update_fields=['is_email_verified', 'email_verified_at'])
    
    def soft_delete(self):
        """Soft delete user account and anonymize identifiers."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.is_active = False
        # Anonymize email and username to free them for re-registration
        # Format: deleted_UUID@deleted.local
        deleted_suffix = f"deleted_{self.id}"
        self.email = f"{deleted_suffix}@deleted.local"
        self.username = deleted_suffix
        self.save(update_fields=['is_deleted', 'deleted_at', 'is_active', 'email', 'username'])


class UserAddress(models.Model):
    """Multiple shipping addresses for a user."""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=50, default='Home')  # Home, Office, etc.
    recipient_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    ward = models.CharField(max_length=100, blank=True)
    is_default = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Địa chỉ giao hàng'
        verbose_name_plural = 'Địa chỉ giao hàng'
        ordering = ['-is_default', '-created_at']
    
    def __str__(self):
        return f"{self.label} - {self.recipient_name}"
    
    def save(self, *args, **kwargs):
        if self.is_default:
            # Unset other defaults
            UserAddress.objects.filter(user=self.user, is_default=True).update(is_default=False)
        elif not UserAddress.objects.filter(user=self.user).exists():
            # First address is always default
            self.is_default = True
        super().save(*args, **kwargs)
    
    @property
    def full_address(self):
        parts = [self.address, self.ward, self.district, self.city]
        return ', '.join(filter(None, parts))


class SocialAccount(models.Model):
    """Linked social accounts for users."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='social_accounts')
    provider = models.CharField(max_length=20, choices=[('github', 'GitHub'), ('google', 'Google')])
    uid = models.CharField(max_length=255)
    extra_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('provider', 'uid')

    def __str__(self):
        return f"{self.user.email} - {self.provider}"
