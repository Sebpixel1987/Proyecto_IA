from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('panel-admin/', views.panel_admin, name='panel_admin'),
    path('panel-conductor/', views.panel_conductor, name='panel_conductor'),
    path('panel-cliente/', views.panel_cliente, name='panel_cliente'),
    path('mapa/', views.mapa_rutas_view, name='mapa_rutas'),
    path('historial/', views.historial_rutas, name='historial_rutas'),
    path('historial/<int:pk>/', views.detalle_ruta_historica, name='detalle_ruta_historica'),
    path('datos/nuevo/', views.registrar_ubicacion_y_pedido, name='registrar_ubicacion_y_pedido'),
]