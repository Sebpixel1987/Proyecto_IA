from django.urls import path
from . import views

urlpatterns = [
    # Página principal y autenticación
    path('', views.home, name='home'),
    path('login/', views.login_rol, name='login_rol'),
    path('logout/', views.logout_rol, name='logout_rol'),
    path('registro-cliente/', views.registro_cliente, name='registro_cliente'),

    # Enrutador y paneles por rol
    path('dashboard/', views.dashboard, name='dashboard'),
    path('panel-admin/', views.panel_admin, name='panel_admin'),
    path('panel-conductor/', views.panel_conductor, name='panel_conductor'),
    path('panel-cliente/', views.panel_cliente, name='panel_cliente'),

    # Acciones operativas
    path('admin-productos/nuevo/', views.crear_producto, name='crear_producto'),
    path('admin-productos/<int:pk>/stock/', views.actualizar_stock_producto, name='actualizar_stock_producto'),
    path('conductor/entregar/<int:pedido_id>/', views.marcar_pedido_entregado, name='marcar_pedido_entregado'),

    # Hoja de Ruta Imprimible / PDF
    path('ruta/imprimir/<int:camion_id>/', views.hoja_ruta_imprimible, name='hoja_ruta_imprimible'),

    # Carga Masiva Excel / CSV
    path('carga-masiva/', views.carga_masiva_datos, name='carga_masiva_datos'),
    path('carga-masiva/plantilla/', views.descargar_plantilla_carga, name='descargar_plantilla_carga'),

    # Rutas existentes del MVP
    path('mapa/', views.mapa_rutas_view, name='mapa_rutas'),
    path('historial/', views.historial_rutas, name='historial_rutas'),
    path('historial/<int:pk>/', views.detalle_ruta_historica, name='detalle_ruta_historica'),
    path('datos/nuevo/', views.registrar_ubicacion_y_pedido, name='registrar_ubicacion_y_pedido'),

    #Manejo de pedidos en la ruta
    path('ruta/pedido/<int:pedido_id>/mover/<str:direccion>/', views.mover_parada_ruta, name='mover_parada_ruta'),
    path('ruta/pedido/<int:pedido_id>/reasignar/', views.reasignar_pedido_camion, name='reasignar_pedido_camion'),
    path('ruta/pedido/<int:pedido_id>/preventa/', views.devolver_pedido_preventa, name='devolver_pedido_preventa'),

    #Marcar pedido
    path('conductor/pedido/<int:pedido_id>/llegada/', views.registrar_llegada_punto, name='registrar_llegada_punto'),
    path('conductor/pedido/<int:pedido_id>/no-entregado/', views.marcar_pedido_no_entregado, name='marcar_pedido_no_entregado'),
    path('comprobante/pedido/<int:pedido_id>/', views.comprobante_entrega_pedido, name='comprobante_entrega_pedido'),

    # Gestión de flota y conductores
    path('flota/camion/crear/', views.crear_camion, name='crear_camion'),
    path('flota/camion/<int:camion_id>/asignar-conductor/', views.asignar_conductor_camion, name='asignar_conductor_camion'),
    path('flota/conductor/crear/', views.crear_conductor, name='crear_conductor'),
    path('conductor/seleccionar-camion/', views.seleccionar_camion_conductor, name='seleccionar_camion_conductor'),
]