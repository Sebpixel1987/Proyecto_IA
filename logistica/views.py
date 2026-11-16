import folium
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .models import Pedido, Camion, RutaHistorica, Ubicacion
from .forms import UbicacionForm, PedidoExternoForm
from .utils import optimizar_y_asignar_rutas

@login_required(login_url='/admin/login/')
def dashboard(request):
    try:
        rol = request.user.perfilusuario.rol
        if rol == 'ADMIN':
            return redirect('panel_admin')
        elif rol == 'CONDUCTOR':
            return redirect('panel_conductor')
        elif rol == 'CLIENTE':
            return redirect('panel_cliente')
    except:
        return HttpResponse("Error: El usuario no tiene un PerfilUsuario asignado.")

@login_required(login_url='/admin/login/')
def panel_admin(request):
    if request.user.perfilusuario.rol != 'ADMIN': 
        return HttpResponse("Acceso denegado.")
    
    if request.method == 'POST':
        optimizar_y_asignar_rutas()
        
        # Guardado automático en el Historial de Rutas
        camiones = Camion.objects.all()
        for camion in camiones:
            pedidos_asignados = Pedido.objects.filter(camion_asignado=camion, estado='EN_RUTA')
            if pedidos_asignados.exists():
                ruta_hist = RutaHistorica.objects.create(
                    camion=camion,
                    distancia_total_km=15.5,
                    tiempo_estimado_min=30.0
                )
                ruta_hist.pedidos_incluidos.set(pedidos_asignados)
                
        return redirect('panel_admin')
        
    pedidos_preventa = Pedido.objects.filter(estado='PREVENTA').count()
    pedidos_en_ruta = Pedido.objects.filter(estado='EN_RUTA').order_by('camion_asignado', 'orden_en_ruta')
    
    rutas_por_camion = {}
    for p in pedidos_en_ruta:
        patente = p.camion_asignado.patente
        if patente not in rutas_por_camion:
            rutas_por_camion[patente] = []
        rutas_por_camion[patente].append(p)

    tablas_html = ""
    if not rutas_por_camion:
        tablas_html = """
        <div class='alert alert-info shadow-sm'>
            <i class='fa-solid fa-circle-info me-2'></i> No hay rutas asignadas actualmente. Ejecuta la optimización.
        </div>
        """
    else:
        for patente, pedidos in rutas_por_camion.items():
            filas = ""
            for p in pedidos:
                direccion = p.ubicacion_entrega.direccion if p.ubicacion_entrega else "Sin dirección"
                comuna = p.ubicacion_entrega.comuna if p.ubicacion_entrega else ""
                
                filas += f"""
                    <tr>
                        <td class="text-center"><span class="badge bg-secondary">{p.orden_en_ruta}</span></td>
                        <td><strong>#{p.id}</strong></td>
                        <td>{direccion}, {comuna}</td>
                        <td><span class="badge bg-success">En Ruta</span></td>
                    </tr>
                """
            
            tablas_html += f"""
            <div class="card mb-4 shadow-sm border-0">
                <div class="card-header bg-dark text-white d-flex justify-content-between align-items-center">
                    <h5 class="mb-0"><i class="fa-solid fa-truck-fast me-2"></i> Camión FOTON: {patente}</h5>
                    <span class="badge bg-primary rounded-pill fs-6">{len(pedidos)} paradas</span>
                </div>
                <div class="table-responsive">
                    <table class="table table-hover table-striped mb-0">
                        <thead class="table-light">
                            <tr>
                                <th scope="col" class="text-center">Orden</th>
                                <th scope="col">ID Pedido</th>
                                <th scope="col">Destino</th>
                                <th scope="col">Estado</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filas}
                        </tbody>
                    </table>
                </div>
            </div>
            """

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard Logístico - Emporio Alemán</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
        <style>
            body {{ background-color: #f4f6f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
            .navbar {{ background-color: #0d233a; }}
            .metric-card {{ border-left: 5px solid #ffc107; transition: transform 0.2s; }}
            .metric-card:hover {{ transform: translateY(-3px); }}
        </style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark shadow-sm mb-4">
            <div class="container">
                <a class="navbar-brand fw-bold" href="#">
                    <i class="fa-solid fa-route me-2 text-warning"></i>Emporio Alemán | IAnts Lab
                </a>
                <div class="d-flex text-white align-items-center">
                    <i class="fa-solid fa-user-shield me-2"></i> {request.user.username.upper()} (Administrador)
                </div>
            </div>
        </nav>

        <div class="container">
            <div class="row align-items-center mb-4">
                <div class="col-md-6">
                    <h2 class="fw-bold text-dark mb-0">Monitor de Despachos</h2>
                    <p class="text-muted">Optimización mediante Colonia de Hormigas (ACO)</p>
                </div>
                <div class="col-md-6 text-md-end">
                    <form method="POST" class="d-inline">
                        <input type="hidden" name="csrfmiddlewaretoken" value="{request.META.get('CSRF_COOKIE', '')}">
                        <button type="submit" class="btn btn-primary btn-lg shadow-sm me-2">
                            <i class="fa-solid fa-microchip me-2"></i> Optimizar Flota
                        </button>
                    </form>
                    <a href="/mapa/" target="_blank" class="btn btn-success btn-lg shadow-sm me-2">
                        <i class="fa-solid fa-map-location-dot me-2"></i> Ver Mapa (OSRM)
                    </a>
                    <a href="/historial/" class="btn btn-dark btn-lg shadow-sm me-2">
                        <i class="fa-solid fa-history me-2"></i> Historial
                    </a>
                    <a href="/datos/nuevo/" class="btn btn-secondary btn-lg shadow-sm">
                        <i class="fa-solid fa-plus-circle me-2"></i> Nuevo Pedido
                    </a>
                </div>
            </div>

            <div class="row mb-4">
                <div class="col-md-4">
                    <div class="card metric-card shadow-sm border-0">
                        <div class="card-body">
                            <h6 class="card-title text-muted text-uppercase fw-bold"><i class="fa-solid fa-boxes-stacked me-2"></i>En Preventa</h6>
                            <h2 class="mb-0 display-5 fw-bold text-dark">{pedidos_preventa}</h2>
                            <small class="text-muted">Pedidos pendientes de ruteo</small>
                        </div>
                    </div>
                </div>
            </div>

            <h4 class="fw-bold mb-3 text-secondary border-bottom pb-2">
                <i class="fa-solid fa-list-check me-2"></i> Rutas Asignadas ({len(rutas_por_camion)} camiones activos)
            </h4>
            {tablas_html}
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    return HttpResponse(html)

@login_required(login_url='/admin/login/')
def panel_conductor(request):
    if request.user.perfilusuario.rol != 'CONDUCTOR': 
        return HttpResponse("Acceso denegado.")
        
    camion = Camion.objects.filter(conductor__usuario=request.user).first()
    rutas = Pedido.objects.filter(camion_asignado=camion, estado='EN_RUTA').order_by('orden_en_ruta') if camion else []
    
    lista_rutas = ''.join([f"<li><strong>Pedido #{p.id}</strong> - Destino: {p.ubicacion_entrega.direccion}, {p.ubicacion_entrega.comuna}</li>" for p in rutas])
    html = f"<h1>Hoja de Ruta - Camión: {camion.patente if camion else 'Sin Asignar'}</h1><ol>{lista_rutas}</ol>"
    return HttpResponse(html)

@login_required(login_url='/admin/login/')
def panel_cliente(request):
    if request.user.perfilusuario.rol != 'CLIENTE': 
        return HttpResponse("Acceso denegado.")
        
    pedidos = Pedido.objects.filter(cliente__perfil__usuario=request.user)
    lista_pedidos = ''.join([f"<li><strong>Pedido #{p.id}</strong> | Estado: {p.estado} | Fecha: {p.fecha_entrega_esperada}</li>" for p in pedidos])
    html = f"<h1>Mis Pedidos</h1><ul>{lista_pedidos}</ul>"
    return HttpResponse(html)

@login_required(login_url='/admin/login/')
def mapa_rutas_view(request):
    if request.user.perfilusuario.rol not in ['ADMIN', 'CONDUCTOR']: 
        return HttpResponse("Acceso denegado.")
        
    m = folium.Map(
        location=[-36.8201, -73.0444], 
        zoom_start=11, 
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles &copy; Esri'
    )
    
    origen_chiguayante = [-36.9158, -73.0239]
    folium.Marker(
        origen_chiguayante, 
        popup="<b>Planta Emporio Alemán (Chiguayante)</b>",
        icon=folium.Icon(color="black", icon="star")
    ).add_to(m)

    camiones = Camion.objects.all()
    colores_ruta = ['blue', 'green', 'red', 'purple', 'orange']

    for idx, camion in enumerate(camiones):
        pedidos_en_ruta = Pedido.objects.filter(
            camion_asignado=camion, 
            estado='EN_RUTA'
        ).order_by('orden_en_ruta')
        
        if not pedidos_en_ruta.exists():
            continue
            
        color_actual = colores_ruta[idx % len(colores_ruta)]
        coordenadas_marcadores = [origen_chiguayante]
        
        for p in pedidos_en_ruta:
            if p.ubicacion_entrega.latitud and p.ubicacion_entrega.longitud:
                coord = [float(p.ubicacion_entrega.latitud), float(p.ubicacion_entrega.longitud)]
                coordenadas_marcadores.append(coord)
                
                folium.Marker(
                    coord, 
                    popup=f"Orden: {p.orden_en_ruta} | Pedido #{p.id}<br>Camión: {camion.patente}",
                    icon=folium.Icon(color=color_actual, icon="shopping-cart")
                ).add_to(m)
            
        coordenadas_marcadores.append(origen_chiguayante)
        
        osrm_coords = ";".join([f"{coord[1]},{coord[0]}" for coord in coordenadas_marcadores])
        osrm_url = f"http://router.project-osrm.org/route/v1/driving/{osrm_coords}?geometries=geojson&overview=full"
        
        try:
            response = requests.get(osrm_url, timeout=10)
            data = response.json()
            if data.get('code') == 'Ok':
                trazado_real = data['routes'][0]['geometry']['coordinates']
                coordenadas_ruta_final = [[lat, lon] for lon, lat in trazado_real]
            else:
                coordenadas_ruta_final = coordenadas_marcadores
        except requests.exceptions.RequestException:
            coordenadas_ruta_final = coordenadas_marcadores
        
        folium.PolyLine(
            coordenadas_ruta_final, 
            color=color_actual, 
            weight=4, 
            opacity=0.8,
            tooltip=f"Ruta {camion.patente}"
        ).add_to(m)

    mapa_html = m._repr_html_()
    
    html_completo = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Mapa de Rutas Reales - Emporio Alemán</title></head>
    <body style="font-family: sans-serif; margin: 0; padding: 20px; background: #f4f4f9;">
        <h2 style="text-align:center; color: #333;">Optimización de Última Milla (OSRM)</h2>
        <div style="text-align:center; margin-bottom: 15px;">
            <a href="/panel-admin/" style="padding: 10px 20px; background: #555; color: white; text-decoration: none; border-radius: 5px;">Volver al Panel</a>
        </div>
        <div style="width: 95%; max-width: 1200px; margin: 0 auto; border: 2px solid #ccc; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); overflow: hidden;">
            {mapa_html}
        </div>
    </body>
    </html>
    """
    return HttpResponse(html_completo)

@login_required(login_url='/admin/login/')
def historial_rutas(request):
    if request.user.perfilusuario.rol != 'ADMIN': 
        return HttpResponse("Acceso denegado.")
        
    rutas = RutaHistorica.objects.all().order_by('-fecha_ejecucion')
    filas = ""
    for r in rutas:
        patente = r.camion.patente if r.camion else "N/A"
        filas += f"""
        <tr>
            <td>#{r.id}</td>
            <td><i class="fa-solid fa-truck me-1"></i> {patente}</td>
            <td>{r.fecha_ejecucion.strftime('%d/%m/%Y %H:%M')}</td>
            <td>{r.distancia_total_km} km</td>
            <td>{r.tiempo_estimado_min} min</td>
            <td>
                <a href="/historial/{r.id}/" class="btn btn-sm btn-primary">
                    <i class="fa-solid fa-map-marked-alt me-1"></i> Ver Detalle
                </a>
            </td>
        </tr>
        """
        
    if not filas:
        filas = '<tr><td colspan="6" class="text-center text-muted py-4">No hay rutas registradas en el historial todavía.</td></tr>'

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Historial de Rutas - Emporio Alemán</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    </head>
    <body style="background-color: #f4f6f9;">
        <div class="container mt-4 mb-5">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2><i class="fa-solid fa-history me-2 text-primary"></i>Historial de Rutas Logísticas</h2>
                <div>
                    <a href="/datos/nuevo/" class="btn btn-dark me-2"><i class="fa-solid fa-plus-circle me-1"></i> Ingresar Pedido</a>
                    <a href="/panel-admin/" class="btn btn-outline-secondary"><i class="fa-solid fa-arrow-left me-1"></i> Volver al Panel</a>
                </div>
            </div>
            <div class="card shadow border-0">
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead class="table-dark">
                                <tr>
                                    <th>ID Ruta</th>
                                    <th>Camión FOTON</th>
                                    <th>Fecha de Ejecución</th>
                                    <th>Distancia Total</th>
                                    <th>Tiempo Estimado</th>
                                    <th>Acciones</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filas}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)

@login_required(login_url='/admin/login/')
def detalle_ruta_historica(request, pk):
    if request.user.perfilusuario.rol != 'ADMIN': 
        return HttpResponse("Acceso denegado.")
        
    ruta = get_object_or_404(RutaHistorica, pk=pk)
    patente = ruta.camion.patente if ruta.camion else "N/A"
    
    lista_pedidos = ""
    for p in ruta.pedidos_incluidos.all():
        lista_pedidos += f"<li>Pedido #{p.id} - Destino: {p.ubicacion_entrega.direccion if p.ubicacion_entrega else 'N/A'}</li>"
    if not lista_pedidos:
        lista_pedidos = "<li class='text-muted'>Sin pedidos asociados.</li>"

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Detalle Ruta #{ruta.id}</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    </head>
    <body style="background-color: #f4f6f9;">
        <div class="container mt-4 mb-5">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2><i class="fa-solid fa-map-marked-alt me-2 text-primary"></i>Detalle de Ruta Histórica #{ruta.id}</h2>
                <a href="/historial/" class="btn btn-outline-secondary"><i class="fa-solid fa-arrow-left me-1"></i> Volver al Historial</a>
            </div>
            <div class="card shadow border-0 col-md-6">
                <div class="card-header bg-dark text-white"><h5>Métricas del Despacho</h5></div>
                <div class="card-body">
                    <p><strong>Camión FOTON:</strong> {patente}</p>
                    <p><strong>Fecha:</strong> {ruta.fecha_ejecucion.strftime('%d/%m/%Y %H:%M')}</p>
                    <p><strong>Distancia:</strong> {ruta.distancia_total_km} km</p>
                    <p><strong>Tiempo Estimado:</strong> {ruta.tiempo_estimado_min} min</p>
                    <hr>
                    <h6 class="text-primary">Pedidos Incluidos:</h6>
                    <ul>{lista_pedidos}</ul>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)

@login_required(login_url='/admin/login/')
def registrar_ubicacion_y_pedido(request):
    if request.user.perfilusuario.rol != 'ADMIN': 
        return HttpResponse("Acceso denegado.")
        
    if request.method == 'POST':
        ubicacion_form = UbicacionForm(request.POST)
        pedido_form = PedidoExternoForm(request.POST)
        
        if ubicacion_form.is_valid() and pedido_form.is_valid():
            ubicacion = ubicacion_form.save()
            pedido = pedido_form.save(commit=False)
            pedido.ubicacion_entrega = ubicacion
            pedido.save()
            return redirect('historial_rutas')
    else:
        ubicacion_form = UbicacionForm()
        pedido_form = PedidoExternoForm()

    form_html = f"""
    <form method="POST">
        <input type="hidden" name="csrfmiddlewaretoken" value="{request.META.get('CSRF_COOKIE', '')}">
        <h5 class="text-primary border-bottom pb-2 mb-3">1. Datos de Ubicación</h5>
        {ubicacion_form.as_p()}
        
        <h5 class="text-primary border-bottom pb-2 mb-3 mt-4">2. Datos del Pedido</h5>
        {pedido_form.as_p()}
        
        <div class="d-grid gap-2 mt-4">
            <button type="submit" class="btn btn-success btn-lg"><i class="fa-solid fa-save me-2"></i>Guardar en Sistema</button>
            <a href="/panel-admin/" class="btn btn-outline-secondary">Cancelar / Volver al Panel</a>
        </div>
    </form>
    """

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Ingreso Externo - Emporio Alemán</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    </head>
    <body style="background-color: #f4f6f9;">
        <div class="container mt-4 mb-5">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card shadow border-0">
                        <div class="card-header bg-dark text-white">
                            <h4 class="mb-0"><i class="fa-solid fa-map-marker-alt me-2"></i>Ingreso de Datos Externos (Ubicación y Pedido)</h4>
                        </div>
                        <div class="card-body">
                            {form_html}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)