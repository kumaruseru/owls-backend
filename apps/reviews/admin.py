from django.contrib import admin
from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Admin configuration for Review."""
    
    list_display = (
        'product', 'user', 'rating', 'title', 
        'is_verified_purchase', 'is_approved', 'created_at'
    )
    list_filter = ('rating', 'is_verified_purchase', 'is_approved', 'created_at')
    search_fields = ('product__name', 'user__email', 'title', 'comment')
    list_editable = ('is_approved',)
    ordering = ('-created_at',)
    
    readonly_fields = ('is_verified_purchase', 'created_at', 'updated_at')
