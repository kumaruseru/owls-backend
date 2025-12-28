"""Main URL Configuration for OWLS V0.1 Backend."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API v1
    path('api/auth/', include('apps.identity.urls', namespace='identity')),
    path('api/core/', include('apps.core.urls', namespace='core')),
    path('api/catalog/', include('apps.catalog.urls', namespace='catalog')),
    path('api/', include('apps.sales.urls', namespace='sales')),
    path('api/payments/', include('apps.billing.urls', namespace='billing')),
    path('api/social/', include('apps.social.urls', namespace='social')),
    path('api/shipping/', include('apps.shipping.urls', namespace='shipping')),
    path('api/', include('apps.marketing.urls', namespace='marketing')),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
