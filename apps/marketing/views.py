from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Coupon, Banner
from .serializers import CouponSerializer, BannerSerializer


class CouponValidateView(APIView):
    """Validate coupon code and calculate discount."""
    permission_classes = (permissions.IsAuthenticated,)  # Security: require login
    
    def post(self, request):
        code = request.data.get('code')
        order_amount = request.data.get('order_amount', 0)
        
        if not code:
            return Response({'error': 'Mã giảm giá không được để trống'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            coupon = Coupon.objects.get(code=code.upper())
        except Coupon.DoesNotExist:
            # Security: don't reveal if coupon exists or not
            return Response({'error': 'Mã giảm giá không hợp lệ'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not coupon.is_valid:
            return Response({'error': 'Mã đã hết hạn hoặc không còn hiệu lực'}, status=status.HTTP_400_BAD_REQUEST)
        
        discount = coupon.calculate_discount(order_amount)
        
        return Response({
            'coupon': CouponSerializer(coupon).data,
            'discount': discount
        })


class BannerListView(generics.ListAPIView):
    queryset = Banner.objects.filter(is_active=True)
    serializer_class = BannerSerializer
