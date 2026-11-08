from django.urls import path
from . import views
from .views import mapa_rutas_view

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('admin-logistica/', views.panel_admin, name='panel_admin'),
    path('conductor/', views.panel_conductor, name='panel_conductor'),
    path('cliente/', views.panel_cliente, name='panel_cliente'),
    path('mapa/', mapa_rutas_view, name='mapa_rutas'),
    path('mapa/', mapa_rutas_view, name='mapa_rutas'),
]