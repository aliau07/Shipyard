from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

admin.site.site_header = 'Shipyard admin'
admin.site.site_title = 'Shipyard admin'

api_patterns = [
    path('', include('apps.accounts.urls')),
    path('', include('apps.projects.urls')),
    path('', include('apps.releases.urls')),
    path('', include('apps.notifications.urls')),
    path('', include('apps.dashboard.urls')),
    path('', include('apps.core.urls')),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(api_patterns)),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
