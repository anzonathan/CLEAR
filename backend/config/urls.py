"""URL configuration for CLEAR project."""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET


@require_GET
def get_csrf_token(request):
    """Return CSRF token for frontend."""
    return JsonResponse({'csrfToken': get_token(request)})


urlpatterns = [
    path('admin/', admin.site.urls),

    # CSRF token endpoint
    path('api/auth/csrf/', get_csrf_token),

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
