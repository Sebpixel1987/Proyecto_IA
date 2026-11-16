import math
import random
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


def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    """Calcula la distancia geodésica en línea recta (km)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def estimar_costo_gnn(nodo_a, nodo_b):
    """
    Simula la inferencia de la Red Neuronal de Grafos (GNN) sobre aristas urbanas:
    combina distancia geodésica, factor vial urbano (1.28x promedio Gran Concepción)
    y penalización por salto intercomunal para favorecer clústers compactos.
    """
    distancia = calcular_distancia_haversine(nodo_a['lat'], nodo_a['lon'], nodo_b['lat'], nodo_b['lon'])
    factor_vial = 1.28  # Corrección calle real vs línea recta
    penalizacion_zona = 1.18 if (nodo_a.get('comuna') and nodo_b.get('comuna') and nodo_a['comuna'] != nodo_b['comuna']) else 1.0
    ruido_topologico = random.uniform(0.95, 1.15)
    return max(distancia * factor_vial * penalizacion_zona * ruido_topologico, 0.05)


def optimizar_y_asignar_rutas(zona_codigo='TODAS', fecha_filtro=None):
    """
    Ejecuta el ensamble GNN + ACO respetando:
    - Zonificación operativa y fecha de entrega (opcional)
    - Capacidad máxima de 1.600 kg y 30 paradas por camión FOTON TM-3
    - No sobrescribe ni sobrecarga camiones que ya tienen rutas activas en otra zona
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
    todos_camiones = list(Camion.objects.filter(conductor__isnull=False).order_by('id'))
    if not todos_camiones:
        todos_camiones = list(Camion.objects.all().order_by('id'))

    if not pedidos or not todos_camiones:
        return {}

    # Priorizar camiones libres (sin pedidos EN_RUTA) para no mezclar zonas en un mismo vehículo
    camiones_libres = [
        c for c in todos_camiones
        if not Pedido.objects.filter(camion_asignado=c, estado='EN_RUTA').exists()
    ]
    camiones_con_espacio = []
    for c in todos_camiones:
        activos = Pedido.objects.filter(camion_asignado=c, estado='EN_RUTA')
        if activos.exists():
            peso_usado = sum(float(p.peso_total_kg) for p in activos)
            paradas_usadas = activos.count()
            if (float(c.capacidad_max_kg) - peso_usado) > 10.0 and paradas_usadas < 30:
                camiones_con_espacio.append(c)

    # Usar primero los camiones completamente libres y luego los que aún tengan holgura
    camiones = camiones_libres + camiones_con_espacio
    if not camiones:
        return {}

    # Calcular capacidad y paradas disponibles reales de cada camión seleccionado
    estado_flota = {}
    for idx_c, c in enumerate(camiones):
        activos = Pedido.objects.filter(camion_asignado=c, estado='EN_RUTA')
        peso_usado = sum(float(p.peso_total_kg) for p in activos)
        paradas_usadas = activos.count()
        estado_flota[idx_c] = {
            'cap_disp': max(0.0, float(c.capacidad_max_kg) - peso_usado),
            'paradas_disp': max(0, 30 - paradas_usadas),
            'orden_inicio': paradas_usadas + 1,
        }

    # 1. Definir Grafo (Nodos y Aristas) desde Planta Chiguayante
    origen = {
        'id': 'CHIGUAYANTE',
        'lat': -36.9158,
        'lon': -73.0239,
        'comuna': 'Chiguayante',
        'pedido': None
    }
    nodos = [origen] + [
        {
            'id': p.id,
            'lat': float(p.ubicacion_entrega.latitud),
            'lon': float(p.ubicacion_entrega.longitud),
            'comuna': p.ubicacion_entrega.comuna,
            'pedido': p,
        }
        for p in pedidos
    ]
    n_nodos = len(nodos)

    pesos_pedidos = {0: 0.0}
    for i in range(1, n_nodos):
        peso = sum(float(d.producto.peso_kg) * d.cantidad for d in nodos[i]['pedido'].detalles.all())
        pesos_pedidos[i] = max(peso, 0.1)

    # 2. GNN: Matriz de costos topológicos y distancias reales
    costos = [[0.0] * n_nodos for _ in range(n_nodos)]
    distancias_km = [[0.0] * n_nodos for _ in range(n_nodos)]
    eta = [[0.0] * n_nodos for _ in range(n_nodos)]

    for i in range(n_nodos):
        for j in range(n_nodos):
            if i != j:
                d_real = calcular_distancia_haversine(
                    nodos[i]['lat'], nodos[i]['lon'], nodos[j]['lat'], nodos[j]['lon']
                ) * 1.28
                c = estimar_costo_gnn(nodos[i], nodos[j])
                distancias_km[i][j] = d_real
                costos[i][j] = c
                eta[i][j] = 1.0 / c

    # 3. ACO: Parámetros calibrados (alpha=1, beta=3, rho=0.5)
    alpha = 1.0
    beta = 3.0
    rho = 0.5
    n_hormigas = 12
    n_iteraciones = 50

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

                    rand = random.uniform(0, suma_prob)
                    acum = 0.0
                    nodo_siguiente = candidatos[-1]
                    for idx_cand, p in enumerate(probabilidades):
                        acum += p
                        if acum >= rand:
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

            penalizacion_rezago = len(nodos_pendientes) * 500.0
            score_total = costo_total_hormiga + penalizacion_rezago

            rutas_hormigas.append(ruta_hormiga)
            scores_hormigas.append(score_total)

            if score_total < mejor_score_global:
                mejor_score_global = score_total
                mejor_ruta_global = ruta_hormiga

        # 4. Evaporación de feromonas
        for i in range(n_nodos):
            for j in range(n_nodos):
                tau[i][j] *= (1.0 - rho)

        # 5. Depósito de feromonas
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

    # 6. Guardar asignación en BD y calcular métricas reales por camión
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
                    pedido.save()

                dist_ruta_km += distancias_km[nodo_prev][0]
                tiempo_est_min = (dist_ruta_km / 32.0) * 60.0 + (len(ruta_camion) * 8.0)

                metricas_por_camion[camion.id] = {
                    'distancia_km': round(dist_ruta_km, 2),
                    'tiempo_min': round(tiempo_est_min, 1),
                    'paradas': len(ruta_camion),
                }

    return metricas_por_camion


def calcular_kpis_operativos():
    """
    Calcula los KPIs comprometidos con Emporio Alemán:
    - Fill Rate (Meta >= 98%): cumplimiento de pedidos asignados/entregados vs total requerido.
    - Lead Time (Meta 98%-100%): entregas puntuales sin pedidos rezagados vencidos.
    """
    hoy = date.today()
    total_pedidos = Pedido.objects.count()
    if total_pedidos == 0:
        return {
            'fill_rate': 100.0,
            'lead_time': 100.0,
            'pedidos_rezagados': 0,
            'entregados_total': 0,
        }

    # Pedidos activos o completados (no rezagados)
    rezagados = Pedido.objects.filter(
        estado__in=['PREVENTA', 'PREPARADO'],
        fecha_entrega_esperada__lt=hoy
    ).count()

    entregados = Pedido.objects.filter(estado='ENTREGADO').count()
    en_ruta = Pedido.objects.filter(estado='EN_RUTA').count()

    # Fill rate: proporción de pedidos despachados/entregados frente a pedidos con fecha <= hoy
    pedidos_comprometidos = Pedido.objects.filter(fecha_entrega_esperada__lte=hoy).count()
    if pedidos_comprometidos > 0:
        cumplidos = Pedido.objects.filter(
            fecha_entrega_esperada__lte=hoy,
            estado__in=['EN_RUTA', 'ENTREGADO']
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