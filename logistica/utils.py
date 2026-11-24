import math
import random
import unicodedata
from datetime import date
from django.db import transaction
from .models import Pedido, Camion

# Zonificación operativa levantada con Emporio Alemán (Gran Concepción)
ZONAS_OPERATIVAS = {
    'TODAS': {
        'nombre': 'Todas las Zonas (Despacho General)',
        'frecuencia': 'Lunes a Sábado',
        'comunas': None,
    },
    'TALCAHUANO_HUALPEN': {
        'nombre': 'Sector Talcahuano – Hualpén',
        'frecuencia': 'Martes, Jueves y Sábado (M-J-S)',
        'comunas': ['Talcahuano', 'Hualpén'],
    },
    'CONCEPCION_CHIGUAYANTE': {
        'nombre': 'Sector Concepción Centro – Chiguayante',
        'frecuencia': 'Lunes a Sábado',
        'comunas': ['Concepción', 'Chiguayante'],
    },
    'SAN_PEDRO_CORONEL': {
        'nombre': 'Eje San Pedro de la Paz – Coronel – Lota',
        'frecuencia': 'Lunes, Miércoles y Viernes (L-M-V)',
        'comunas': ['San Pedro de la Paz', 'Coronel', 'Lota'],
    },
    'PENCO_LIRQUEN': {
        'nombre': 'Sector Penco – Lirquén',
        'frecuencia': 'Martes y Viernes',
        'comunas': ['Penco', 'Lirquén'],
    },
}

# Cuadrantes geográficos (lat_min, lat_max, lon_min, lon_max) con holgura de borde urbano
LIMITES_COMUNAS = {
    'concepcion': {
        'nombre': 'Concepción',
        'box': (-36.8750, -36.7750, -73.0950, -72.9700),
        'centro': (-36.8270, -73.0503),
    },
    'chiguayante': {
        'nombre': 'Chiguayante',
        'box': (-36.9700, -36.8650, -73.0650, -72.9900),
        'centro': (-36.9250, -73.0250),
    },
    'talcahuano': {
        'nombre': 'Talcahuano',
        'box': (-36.7850, -36.6800, -73.1550, -73.0500),
        'centro': (-36.7250, -73.1140),
    },
    'hualpen': {
        'nombre': 'Hualpén',
        'box': (-36.8250, -36.7550, -73.1450, -73.0550),
        'centro': (-36.7900, -73.0850),
    },
    'san pedro de la paz': {
        'nombre': 'San Pedro de la Paz',
        'box': (-36.9450, -36.8150, -73.1750, -73.0750),
        'centro': (-36.8500, -73.1120),
    },
    'coronel': {
        'nombre': 'Coronel',
        'box': (-37.0650, -36.9400, -73.1900, -73.1000),
        'centro': (-37.0150, -73.1420),
    },
    'lota': {
        'nombre': 'Lota',
        'box': (-37.1400, -37.0550, -73.2000, -73.1100),
        'centro': (-37.0900, -73.1580),
    },
    'penco': {
        'nombre': 'Penco',
        'box': (-36.7750, -36.7150, -73.0250, -72.9650),
        'centro': (-36.7400, -72.9950),
    },
    'lirquen': {
        'nombre': 'Lirquén',
        'box': (-36.7300, -36.6850, -73.0050, -72.9500),
        'centro': (-36.7100, -72.9750),
    },
}

PLANTA_ORIGEN = {
    'id': 'CHIGUAYANTE',
    'lat': -36.9158,
    'lon': -73.0239,
    'comuna': 'Chiguayante',
    'pedido': None,
}

FACTOR_VIAL_URBANO = 1.28
PENALIZACION_INTERCOMUNAL = 1.18
CAPACIDAD_MAX_DEFAULT_KG = 1600.0
MAX_PARADAS_POR_CAMION = 30
VELOCIDAD_PROMEDIO_KMH = 32.0
TIEMPO_SERVICIO_PARADA_MIN = 8.0


def _normalizar_texto(texto):
    texto_limpio = str(texto or '').strip().lower()
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto_limpio)
        if unicodedata.category(c) != 'Mn'
    )


def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    """Calcula la distancia geodésica en línea recta (km)."""
    radio_tierra_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radio_tierra_km * c


def validar_coordenadas_comuna(comuna, latitud, longitud):
    """
    Valida coherencia geográfica entre la comuna declarada y las coordenadas (lat, lon).
    Retorna (True, None) si es válido o (False, mensaje_error) si existe incoherencia.
    """
    if latitud is None or longitud is None:
        return True, None

    try:
        lat = float(latitud)
        lon = float(longitud)
    except (TypeError, ValueError):
        return False, "Las coordenadas ingresadas no tienen un formato numérico válido."

    if not (-37.16 <= lat <= -36.65 and -73.23 <= lon <= -72.90):
        return (
            False,
            f"Las coordenadas ({lat:.4f}, {lon:.4f}) están fuera de la zona de cobertura del Gran Concepción."
        )

    clave = _normalizar_texto(comuna)
    info_comuna = LIMITES_COMUNAS.get(clave)
    if not info_comuna:
        return True, None

    lat_min, lat_max, lon_min, lon_max = info_comuna['box']
    if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
        return True, None

    comuna_cercana = min(
        LIMITES_COMUNAS.values(),
        key=lambda item: calcular_distancia_haversine(lat, lon, item['centro'][0], item['centro'][1])
    )['nombre']

    return (
        False,
        f"Incoherencia geográfica: las coordenadas ({lat:.4f}, {lon:.4f}) no corresponden a "
        f"{info_comuna['nombre']} (sector más cercano: {comuna_cercana})."
    )


def calcular_costo_tramo(nodo_a, nodo_b):
    """
    Calcula el costo ponderado entre dos nodos combinando distancia vial estimada
    y penalización por cruce intercomunal para compactar sectores de reparto.
    """
    distancia = calcular_distancia_haversine(nodo_a['lat'], nodo_a['lon'], nodo_b['lat'], nodo_b['lon'])
    cruce_comuna = (
        nodo_a.get('comuna')
        and nodo_b.get('comuna')
        and _normalizar_texto(nodo_a['comuna']) != _normalizar_texto(nodo_b['comuna'])
    )
    penalizacion = PENALIZACION_INTERCOMUNAL if cruce_comuna else 1.0
    return max(distancia * FACTOR_VIAL_URBANO * penalizacion, 0.05)


def _construir_matrices_ruteo(nodos):
    """Genera las matrices simétricas de distancia real estimada, costo y visibilidad (eta)."""
    n_nodos = len(nodos)
    distancias_km = [[0.0] * n_nodos for _ in range(n_nodos)]
    costos = [[0.0] * n_nodos for _ in range(n_nodos)]
    eta = [[0.0] * n_nodos for _ in range(n_nodos)]

    for i in range(n_nodos):
        for j in range(n_nodos):
            if i != j:
                d_vial = calcular_distancia_haversine(
                    nodos[i]['lat'], nodos[i]['lon'], nodos[j]['lat'], nodos[j]['lon']
                ) * FACTOR_VIAL_URBANO
                costo = calcular_costo_tramo(nodos[i], nodos[j])
                distancias_km[i][j] = d_vial
                costos[i][j] = costo
                eta[i][j] = 1.0 / costo

    return distancias_km, costos, eta


def _resolver_secuencia_aco(n_nodos, pesos_pedidos, camiones, estado_flota, costos, eta):
    """Ejecuta optimización por colonia de hormigas (ACO) con restricciones de capacidad y paradas."""
    alpha = 1.0
    beta = 3.0
    rho = 0.5
    n_hormigas = 12
    n_iteraciones = 50

    rng = random.Random(42)
    tau = [[1.0] * n_nodos for _ in range(n_nodos)]
    mejor_ruta_global = None
    mejor_score_global = float('inf')

    for _ in range(n_iteraciones):
        rutas_hormigas = []
        scores_hormigas = []

        for _ in range(n_hormigas):
            ruta_hormiga = []
            costo_total_hormiga = 0.0
            nodos_pendientes = set(range(1, n_nodos))
            idx_camion = 0

            while nodos_pendientes and idx_camion < len(camiones):
                capacidad_restante = estado_flota[idx_camion]['cap_disp']
                paradas_restantes = estado_flota[idx_camion]['paradas_disp']
                nodo_actual = 0
                ruta_camion = []

                while nodos_pendientes and capacidad_restante > 0 and paradas_restantes > 0:
                    probabilidades = []
                    candidatos = []
                    suma_prob = 0.0

                    for j in nodos_pendientes:
                        if pesos_pedidos[j] <= capacidad_restante:
                            p = (tau[nodo_actual][j] ** alpha) * (eta[nodo_actual][j] ** beta)
                            probabilidades.append(p)
                            candidatos.append(j)
                            suma_prob += p

                    if not candidatos:
                        break

                    umbral = rng.uniform(0, suma_prob)
                    acum = 0.0
                    nodo_siguiente = candidatos[-1]
                    for idx_cand, p in enumerate(probabilidades):
                        acum += p
                        if acum >= umbral:
                            nodo_siguiente = candidatos[idx_cand]
                            break

                    ruta_camion.append(nodo_siguiente)
                    nodos_pendientes.remove(nodo_siguiente)
                    costo_total_hormiga += costos[nodo_actual][nodo_siguiente]
                    capacidad_restante -= pesos_pedidos[nodo_siguiente]
                    paradas_restantes -= 1
                    nodo_actual = nodo_siguiente

                if ruta_camion:
                    costo_total_hormiga += costos[nodo_actual][0]
                ruta_hormiga.append(ruta_camion)
                idx_camion += 1

            score_total = costo_total_hormiga + (len(nodos_pendientes) * 500.0)
            rutas_hormigas.append(ruta_hormiga)
            scores_hormigas.append(score_total)

            if score_total < mejor_score_global:
                mejor_score_global = score_total
                mejor_ruta_global = ruta_hormiga

        for i in range(n_nodos):
            for j in range(n_nodos):
                tau[i][j] *= (1.0 - rho)

        for idx_h, ruta_h in enumerate(rutas_hormigas):
            score = scores_hormigas[idx_h]
            if score <= 0:
                continue
            deposito = 1.0 / score
            for ruta_camion in ruta_h:
                if not ruta_camion:
                    continue
                tau[0][ruta_camion[0]] += deposito
                for i in range(len(ruta_camion) - 1):
                    tau[ruta_camion[i]][ruta_camion[i + 1]] += deposito
                tau[ruta_camion[-1]][0] += deposito

    return mejor_ruta_global


def _obtener_flota_disponible():
    """Retorna camiones disponibles con su capacidad y paradas remanentes sin sobrescribir rutas activas."""
    todos_camiones = list(Camion.objects.filter(conductor__isnull=False).order_by('id'))
    if not todos_camiones:
        todos_camiones = list(Camion.objects.all().order_by('id'))

    camiones_libres = []
    camiones_con_espacio = []

    for c in todos_camiones:
        activos = Pedido.objects.filter(camion_asignado=c, estado__in=['EN_RUTA', 'EN_PUNTO'])
        if not activos.exists():
            camiones_libres.append(c)
        else:
            peso_usado = sum(float(p.peso_total_kg) for p in activos)
            paradas_usadas = activos.count()
            if (float(c.capacidad_max_kg) - peso_usado) > 10.0 and paradas_usadas < MAX_PARADAS_POR_CAMION:
                camiones_con_espacio.append(c)

    camiones = camiones_libres + camiones_con_espacio
    estado_flota = {}
    for idx_c, c in enumerate(camiones):
        activos = Pedido.objects.filter(camion_asignado=c, estado__in=['EN_RUTA', 'EN_PUNTO'])
        peso_usado = sum(float(p.peso_total_kg) for p in activos)
        paradas_usadas = activos.count()
        estado_flota[idx_c] = {
            'cap_disp': max(0.0, float(c.capacidad_max_kg) - peso_usado),
            'paradas_disp': max(0, MAX_PARADAS_POR_CAMION - paradas_usadas),
            'orden_inicio': paradas_usadas + 1,
        }

    return camiones, estado_flota


def optimizar_y_asignar_rutas(zona_codigo='TODAS', fecha_filtro=None):
    """
    Planifica y asigna rutas de reparto respetando zonificación operativa,
    capacidad máxima de 1.600 kg y tope de 30 paradas por vehículo.
    """
    qs_pedidos = Pedido.objects.filter(
        estado__in=['PREVENTA', 'PREPARADO'],
        ubicacion_entrega__latitud__isnull=False,
        ubicacion_entrega__longitud__isnull=False,
    ).select_related('ubicacion_entrega').prefetch_related('detalles__producto')

    zona_info = ZONAS_OPERATIVAS.get(zona_codigo, ZONAS_OPERATIVAS['TODAS'])
    if zona_info['comunas']:
        qs_pedidos = qs_pedidos.filter(ubicacion_entrega__comuna__in=zona_info['comunas'])

    if fecha_filtro:
        qs_pedidos = qs_pedidos.filter(fecha_entrega_esperada=fecha_filtro)

    pedidos = list(qs_pedidos)
    camiones, estado_flota = _obtener_flota_disponible()

    if not pedidos or not camiones:
        return {}

    nodos = [PLANTA_ORIGEN] + [
        {
            'id': p.id,
            'lat': float(p.ubicacion_entrega.latitud),
            'lon': float(p.ubicacion_entrega.longitud),
            'comuna': p.ubicacion_entrega.comuna,
            'pedido': p,
        }
        for p in pedidos
    ]

    pesos_pedidos = {0: 0.0}
    for i in range(1, len(nodos)):
        peso = sum(float(d.producto.peso_kg) * d.cantidad for d in nodos[i]['pedido'].detalles.all())
        pesos_pedidos[i] = max(peso, 0.1)

    distancias_km, costos, eta = _construir_matrices_ruteo(nodos)
    mejor_ruta_global = _resolver_secuencia_aco(
        len(nodos), pesos_pedidos, camiones, estado_flota, costos, eta
    )

    metricas_por_camion = {}
    if mejor_ruta_global:
        with transaction.atomic():
            for idx_camion, ruta_camion in enumerate(mejor_ruta_global):
                if not ruta_camion:
                    continue
                camion = camiones[idx_camion]
                dist_ruta_km = 0.0
                nodo_prev = 0
                orden_inicial = estado_flota[idx_camion]['orden_inicio']

                for offset, idx_nodo in enumerate(ruta_camion):
                    dist_ruta_km += distancias_km[nodo_prev][idx_nodo]
                    nodo_prev = idx_nodo

                    pedido = nodos[idx_nodo]['pedido']
                    pedido.camion_asignado = camion
                    pedido.orden_en_ruta = orden_inicial + offset
                    pedido.estado = 'EN_RUTA'
                    pedido.save(update_fields=['camion_asignado', 'orden_en_ruta', 'estado'])

                dist_ruta_km += distancias_km[nodo_prev][0]
                tiempo_est_min = (
                    (dist_ruta_km / VELOCIDAD_PROMEDIO_KMH) * 60.0
                    + (len(ruta_camion) * TIEMPO_SERVICIO_PARADA_MIN)
                )

                metricas_por_camion[camion.id] = {
                    'distancia_km': round(dist_ruta_km, 2),
                    'tiempo_min': round(tiempo_est_min, 1),
                    'paradas': len(ruta_camion),
                }

    return metricas_por_camion


def calcular_kpis_operativos():
    """Calcula indicadores de cumplimiento de pedidos y puntualidad de despacho."""
    hoy = date.today()
    total_pedidos = Pedido.objects.count()
    if total_pedidos == 0:
        return {
            'fill_rate': 100.0,
            'lead_time': 100.0,
            'pedidos_rezagados': 0,
            'entregados_total': 0,
        }

    rezagados = Pedido.objects.filter(
        estado__in=['PREVENTA', 'PREPARADO'],
        fecha_entrega_esperada__lt=hoy
    ).count()

    entregados = Pedido.objects.filter(estado='ENTREGADO').count()
    en_ruta = Pedido.objects.filter(estado__in=['EN_RUTA', 'EN_PUNTO']).count()

    pedidos_comprometidos = Pedido.objects.filter(fecha_entrega_esperada__lte=hoy).count()
    if pedidos_comprometidos > 0:
        cumplidos = Pedido.objects.filter(
            fecha_entrega_esperada__lte=hoy,
            estado__in=['EN_RUTA', 'EN_PUNTO', 'ENTREGADO']
        ).count()
        fill_rate = round((cumplidos / pedidos_comprometidos) * 100, 1)
        lead_time = round(((pedidos_comprometidos - rezagados) / pedidos_comprometidos) * 100, 1)
    else:
        fill_rate = 100.0 if (entregados + en_ruta) > 0 else 98.5
        lead_time = 100.0

    return {
        'fill_rate': fill_rate,
        'lead_time': lead_time,
        'pedidos_rezagados': rezagados,
        'entregados_total': entregados,
    }


def normalizar_y_evaluar_camion(camion):
    """
    Renumera correlativamente las paradas activas de un camión
    y evalúa si excede los topes de 1.600 kg o 30 paradas.
    """
    if not camion:
        return None

    pedidos_activos = list(
        Pedido.objects.filter(camion_asignado=camion, estado__in=['EN_RUTA', 'EN_PUNTO'])
        .order_by('orden_en_ruta', 'id')
    )

    peso_total = 0.0
    for indice, pedido in enumerate(pedidos_activos, start=1):
        if pedido.orden_en_ruta != indice:
            pedido.orden_en_ruta = indice
            pedido.save(update_fields=['orden_en_ruta'])
        peso_total += float(pedido.peso_total_kg or 0)

    capacidad_max = float(getattr(camion, 'capacidad_max_kg', CAPACIDAD_MAX_DEFAULT_KG))
    total_paradas = len(pedidos_activos)

    return {
        'peso_total': round(peso_total, 2),
        'capacidad_max': capacidad_max,
        'total_paradas': total_paradas,
        'excede_peso': peso_total > capacidad_max,
        'excede_paradas': total_paradas > MAX_PARADAS_POR_CAMION,
    }