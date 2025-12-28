from django.db import models
from django.core.cache import cache

class SingletonModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super(SingletonModel, self).save(*args, **kwargs)
        self.set_cache()

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        if cache.get(cls.__name__):
            return cache.get(cls.__name__)
        obj, created = cls.objects.get_or_create(pk=1)
        if not created:
            obj.set_cache()
        return obj

    def set_cache(self):
        cache.set(self.__class__.__name__, self)

class SiteConfig(SingletonModel):
    # General
    site_name = models.CharField(max_length=255, default="OWLS")
    site_description = models.TextField(default="Future Tech Store", blank=True)
    logo = models.ImageField(upload_to='site/', null=True, blank=True)
    
    # Contact
    contact_email = models.EmailField(default="support@owls.com")
    phone_number = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    
    # Social - Stored as JSON
    social_links = models.JSONField(default=dict, blank=True)
    
    # System
    maintenance_mode = models.BooleanField(default=False)
    
    # Payment & Shipping (Simple flags for now)
    enable_cod = models.BooleanField(default=True)
    enable_stripe = models.BooleanField(default=False)
    shipping_fee_flat = models.DecimalField(max_digits=10, decimal_places=2, default=50000)
    free_shipping_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=1000000)

    def __str__(self):
        return "Site Configuration"

    class Meta:
        verbose_name = "Site Configuration"

class TeamMember(models.Model):
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=255)
    image = models.ImageField(upload_to='team/', null=True, blank=True)
    order = models.PositiveIntegerField(default=0, help_text="Display order")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Team Member"
        verbose_name_plural = "Team Members"

    def __str__(self):
        return self.name
