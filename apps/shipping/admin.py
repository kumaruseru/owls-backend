from django.contrib import admin
from .models import ShippingProvider, Shipment


@admin.register(ShippingProvider)
class ShippingProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'base_fee', 'is_active')
    list_filter = ('is_active',)


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('order', 'provider', 'tracking_number', 'status', 'shipped_at')
    list_filter = ('status', 'provider')
    search_fields = ('order__order_number', 'tracking_number')
