# en erp_project/urls.py (Versión Final Limpia)

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Una sola línea para gobernar toda la API.
    path('api/', include('api.urls')),
]