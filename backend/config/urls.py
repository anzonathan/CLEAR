"""URL configuration for CLEAR project."""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication endpoints
    path('api/auth/', include('dj_rest_auth.urls')),
    path('api/auth/registration/', include('dj_rest_auth.registration.urls')),
    path('api/auth/google/', include('allauth.socialaccount.urls')),

    # API endpoints
    path('api/users/', include('apps.users.urls')),
    path('api/', include('apps.connections.urls')),
    path('api/', include('apps.videos.urls')),
    path('api/', include('apps.live.urls')),
    path('api/field/', include('apps.field.urls')),
    path('api/admin/', include('apps.users.admin_urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
