from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('panel-admin/', views.panel_admin, name='panel_admin'),
    path('panel-conductor/', views.panel_conductor, name='panel_conductor'),
    path('panel-cliente/', views.panel_cliente, name='panel_cliente'),
    path('mapa/', views.mapa_rutas_view, name='mapa_rutas'),
]