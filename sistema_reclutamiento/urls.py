from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('logistica.urls')), # Conecta tus vistas directamente
    path('', lambda request: redirect('dashboard/')), # Redirige la raíz al dashboard
]