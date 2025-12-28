from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from .models import SiteConfig, TeamMember
from .serializers import SiteConfigSerializer, TeamMemberSerializer

class SiteConfigViewSet(viewsets.ModelViewSet):
    queryset = SiteConfig.objects.all()
    serializer_class = SiteConfigSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_object(self):
        return SiteConfig.load()

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return Response(serializer.data)

class TeamMemberViewSet(viewsets.ModelViewSet):
    queryset = TeamMember.objects.filter(is_active=True).order_by('order', 'created_at')
    serializer_class = TeamMemberSerializer
    permission_classes = [AllowAny]
