from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SiteConfigViewSet, TeamMemberViewSet

app_name = 'core'

router = DefaultRouter()
router.register(r'config', SiteConfigViewSet, basename='config')
router.register(r'team', TeamMemberViewSet, basename='team')

urlpatterns = [
    path('', include(router.urls)),
]
