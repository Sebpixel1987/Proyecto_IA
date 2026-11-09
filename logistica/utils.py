import math
import random
from django.db import transaction
from .models import Pedido, Camion

def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    """Calcula la distancia geodésica en línea recta."""
    R = 6371.0 # Radio de la Tierra en km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def estimar_costo_gnn(lat1, lon1, lat2, lon2):
    """
    Simula la predicción de la Red Neuronal de Grafos (GNN).
    La GNN infiere el costo real del tramo (tráfico, topología) para que ACO 
    rutée sobre él, en lugar de rutear solo por distancia.
    """
    distancia = calcular_distancia_haversine(lat1, lon1, lat2, lon2)
    # Se inyecta un factor de costo no lineal para emular la inferencia de GNN sobre el grafo urbano
    factor_topologico = random.uniform(0.9, 1.4) 
    return max(distancia * factor_topologico, 0.001)

def optimizar_y_asignar_rutas():
    pedidos = list(Pedido.objects.filter(estado='PREVENTA'))
    camiones = list(Camion.objects.all().order_by('-capacidad_max_kg'))
    
    if not pedidos or not camiones:
        return

    # 1. Definir Grafo (Nodos y Aristas)
    origen = {'id': 'CHIGUAYANTE', 'lat': -36.9158, 'lon': -73.0239, 'pedido': None}
    nodos = [origen] + [{'id': p.id, 'lat': float(p.ubicacion_entrega.latitud), 'lon': float(p.ubicacion_entrega.longitud), 'pedido': p} for p in pedidos]
    n_nodos = len(nodos)

    # Precalcular pesos de los pedidos para la restricción de 1.600 kg
    pesos_pedidos = {0: 0.0}
    for i in range(1, n_nodos):
        peso = sum(float(d.producto.peso_kg) * d.cantidad for d in nodos[i]['pedido'].detalles.all())
        pesos_pedidos[i] = peso

    # 2. GNN: Estimar matriz de costos de las aristas
    costos = [[0.0] * n_nodos for _ in range(n_nodos)]
    eta = [[0.0] * n_nodos for _ in range(n_nodos)] # Visibilidad
    
    for i in range(n_nodos):
        for j in range(n_nodos):
            if i != j:
                c = estimar_costo_gnn(nodos[i]['lat'], nodos[i]['lon'], nodos[j]['lat'], nodos[j]['lon'])
                costos[i][j] = c
                eta[i][j] = 1.0 / c 

    # 3. ACO: Parámetros del Ajuste Equilibrado
    alpha = 1.0  # Peso de la feromona
    beta = 3.0   # Peso de la visibilidad
    rho = 0.5    # Tasa de evaporación
    n_hormigas = 10
    n_iteraciones = 50

    # Inicializar tabla de feromonas en las aristas
    tau = [[1.0] * n_nodos for _ in range(n_nodos)]
    
    mejor_ruta_global = None
    mejor_costo_global = float('inf')

    # Bucle de construcción ACO
    for iteracion in range(n_iteraciones):
        rutas_hormigas = []
        costos_hormigas = []

        for _ in range(n_hormigas):
            ruta_hormiga = []
            costo_total_hormiga = 0.0
            nodos_pendientes = set(range(1, n_nodos))
            idx_camion = 0
            
            # Construcción de rutas mientras queden pedidos y camiones
            while nodos_pendientes and idx_camion < len(camiones):
                capacidad_restante = float(camiones[idx_camion].capacidad_max_kg)
                paradas_restantes = 30
                nodo_actual = 0
                ruta_camion = []
                
                while nodos_pendientes and capacidad_restante > 0 and paradas_restantes > 0:
                    probabilidades = []
                    candidatos = []
                    suma_prob = 0.0
                    
                    # Evaluar aristas factibles (que no superen capacidad)
                    for j in nodos_pendientes:
                        if pesos_pedidos[j] <= capacidad_restante:
                            # Regla de transición probabilística
                            p = (tau[nodo_actual][j] ** alpha) * (eta[nodo_actual][j] ** beta)
                            probabilidades.append(p)
                            candidatos.append(j)
                            suma_prob += p
                    
                    if not candidatos:
                        break # El camión se llenó
                        
                    # Selección mediante ruleta proporcional
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
                
                costo_total_hormiga += costos[nodo_actual][0] # Regreso a Planta
                ruta_hormiga.append(ruta_camion)
                idx_camion += 1

            if nodos_pendientes:
                costo_total_hormiga += 999999.0 # Penalización si la hormiga no logra entregar todo
                
            rutas_hormigas.append(ruta_hormiga)
            costos_hormigas.append(costo_total_hormiga)
            
            if costo_total_hormiga < mejor_costo_global and not nodos_pendientes:
                mejor_costo_global = costo_total_hormiga
                mejor_ruta_global = ruta_hormiga

        # 4. ACO: Evaporación de feromonas
        for i in range(n_nodos):
            for j in range(n_nodos):
                tau[i][j] *= (1.0 - rho)
                
        # 5. ACO: Depósito de feromonas basado en la calidad de la ruta
        for idx_h, ruta_h in enumerate(rutas_hormigas):
            costo = costos_hormigas[idx_h]
            if costo >= 999999.0: continue
            
            deposito = 1.0 / costo
            for ruta_camion in ruta_h:
                if not ruta_camion: continue
                tau[0][ruta_camion[0]] += deposito
                for i in range(len(ruta_camion)-1):
                    tau[ruta_camion[i]][ruta_camion[i+1]] += deposito
                tau[ruta_camion[-1]][0] += deposito

    # 6. Guardar la mejor ruta consolidada en la Base de Datos
    if mejor_ruta_global:
        with transaction.atomic():
            for idx_camion, ruta_camion in enumerate(mejor_ruta_global):
                camion = camiones[idx_camion]
                for orden, idx_nodo in enumerate(ruta_camion, start=1):
                    pedido = nodos[idx_nodo]['pedido']
                    pedido.camion_asignado = camion
                    pedido.orden_en_ruta = orden
                    pedido.estado = 'EN_RUTA'
                    pedido.save()