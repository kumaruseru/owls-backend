from rest_framework import serializers
from .models import Payment, PaymentRefund


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for payment display."""
    
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    
    class Meta:
        model = Payment
        fields = (
            'id', 'order', 'order_number', 'payment_method', 'payment_method_display',
            'amount', 'currency', 'status', 'status_display',
            'transaction_id', 'payment_url', 'paid_at',
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'transaction_id', 'payment_url', 'paid_at', 'created_at', 'updated_at')


class PaymentCreateSerializer(serializers.Serializer):
    """Serializer for creating a payment."""
    
    order_id = serializers.IntegerField()
    payment_method = serializers.ChoiceField(choices=['stripe', 'vnpay', 'momo', 'cod'])
    return_url = serializers.URLField(required=False)
    cancel_url = serializers.URLField(required=False)
    
    # VNPay specific
    bank_code = serializers.CharField(required=False, allow_blank=True)
    
    # MoMo specific
    request_type = serializers.ChoiceField(
        choices=['captureWallet', 'payWithATM', 'payWithCC'],
        default='captureWallet',
        required=False
    )
    
    def validate_order_id(self, value):
        from apps.orders.models import Order
        try:
            order = Order.objects.get(id=value, user=self.context['request'].user)
            if order.payment_status == 'paid':
                raise serializers.ValidationError("Đơn hàng này đã được thanh toán.")
            if order.status == 'cancelled':
                raise serializers.ValidationError("Đơn hàng này đã bị hủy.")
        except Order.DoesNotExist:
            raise serializers.ValidationError("Đơn hàng không tồn tại.")
        return value


class RefundCreateSerializer(serializers.Serializer):
    """Serializer for creating a refund."""
    
    payment_id = serializers.UUIDField()
    amount = serializers.IntegerField(required=False)
    reason = serializers.CharField()
    
    def validate_payment_id(self, value):
        try:
            payment = Payment.objects.get(id=value, user=self.context['request'].user)
            if payment.status != 'completed':
                raise serializers.ValidationError("Chỉ có thể hoàn tiền cho giao dịch đã hoàn thành.")
        except Payment.DoesNotExist:
            raise serializers.ValidationError("Giao dịch không tồn tại.")
        return value
    
    def validate_amount(self, value):
        if value and value <= 0:
            raise serializers.ValidationError("Số tiền hoàn phải lớn hơn 0.")
        return value


class PaymentRefundSerializer(serializers.ModelSerializer):
    """Serializer for refund display."""
    
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = PaymentRefund
        fields = (
            'id', 'payment', 'amount', 'reason',
            'status', 'status_display', 'refund_id',
            'created_at', 'updated_at'
        )
