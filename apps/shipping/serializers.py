from rest_framework import serializers
from .models import ShippingProvider, Shipment


class ShippingProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingProvider
        fields = ('id', 'name', 'code', 'logo', 'base_fee')


class ShipmentSerializer(serializers.ModelSerializer):
    provider = ShippingProviderSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Shipment
        fields = ('id', 'provider', 'tracking_number', 'status', 'status_display',
                  'shipped_at', 'delivered_at')
