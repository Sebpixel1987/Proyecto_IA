import math
from decimal import Decimal
from logistica.models import Pedido, Camion

def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    """Calcula la distancia en kilómetros entre dos coordenadas geográficas."""
    R = 6371.0 # Radio de la Tierra en km
    lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def optimizar_y_asignar_rutas():
    # Obtener pedidos listos para enrutar que tengan coordenadas válidas
    pedidos_pendientes = list(Pedido.objects.filter(estado='PREVENTA', ubicacion_entrega__latitud__isnull=False))
    camiones_disponibles = list(Camion.objects.all())
    
    # Coordenadas base del Centro de Distribución (Ajustar a la ubicación real)
    lat_bodega, lon_bodega = -36.8201, -73.0444 

    for camion in camiones_disponibles:
        carga_actual = Decimal('0.0')
        paradas_actuales = 0
        lat_actual, lon_actual = lat_bodega, lon_bodega
        orden_secuencia = 1
        
        while pedidos_pendientes and paradas_actuales < 30 and carga_actual < camion.capacidad_max_kg:
            pedido_mas_cercano = None
            distancia_minima = float('inf')
            peso_del_pedido_elegido = 0
            
            # Evaluar el pedido más cercano que quepa en el camión
            for pedido in pedidos_pendientes:
                peso_pedido = sum(detalle.producto.peso_kg * detalle.cantidad for detalle in pedido.detalles.all())
                
                if carga_actual + peso_pedido <= camion.capacidad_max_kg:
                    distancia = calcular_distancia_haversine(lat_actual, lon_actual, pedido.ubicacion_entrega.latitud, pedido.ubicacion_entrega.longitud)
                    
                    if distancia < distancia_minima:
                        distancia_minima = distancia
                        pedido_mas_cercano = pedido
                        peso_del_pedido_elegido = peso_pedido
            
            if not pedido_mas_cercano:
                break # Ningún pedido restante cabe en la capacidad actual de este camión
                
            # Asignar pedido al camión y actualizar estados
            pedido_mas_cercano.camion_asignado = camion
            pedido_mas_cercano.orden_en_ruta = orden_secuencia
            pedido_mas_cercano.estado = 'EN_RUTA' 
            pedido_mas_cercano.save()
            
            # Actualizar las variables del camión para la siguiente iteración
            carga_actual += peso_del_pedido_elegido
            paradas_actuales += 1
            orden_secuencia += 1
            lat_actual = float(pedido_mas_cercano.ubicacion_entrega.latitud)
            lon_actual = float(pedido_mas_cercano.ubicacion_entrega.longitud)
            
            pedidos_pendientes.remove(pedido_mas_cercano)