import folium
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import Pedido, Camion
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
        return redirect('panel_admin')
        
    pedidos_preventa = Pedido.objects.filter(estado='PREVENTA')
    pedidos_en_ruta = Pedido.objects.filter(estado='EN_RUTA').order_by('camion_asignado', 'orden_en_ruta')
    
    lista_pedidos = ''.join([f"<li>Pedido #{p.id} - Camión: {p.camion_asignado.patente} - Orden: {p.orden_en_ruta}</li>" for p in pedidos_en_ruta])
    
    html = f"""
    <h1>Panel de Logística (Admin)</h1>
    <p>Pedidos en Preventa (Pendientes de ruta): {pedidos_preventa.count()}</p>
    <form method="POST">
        <input type="hidden" name="csrfmiddlewaretoken" value="{request.META.get('CSRF_COOKIE', '')}">
        <button type="submit" style="padding: 10px; background: blue; color: white; border: none; cursor: pointer;">Ejecutar Optimización de Rutas</button>
    </form>
    <br>
    <a href="/mapa/" target="_blank" style="padding: 10px; background: green; color: white; text-decoration: none; display: inline-block;">Ver Mapa de Rutas</a>
    
    <h2>Pedidos Asignados (En Ruta):</h2>
    <ul>
        {lista_pedidos}
    </ul>
    """
    return HttpResponse(html)

@login_required(login_url='/admin/login/')
def panel_conductor(request):
    if request.user.perfilusuario.rol != 'CONDUCTOR': 
        return HttpResponse("Acceso denegado.")
        
    camion = Camion.objects.filter(conductor__usuario=request.user).first()
    rutas = Pedido.objects.filter(camion_asignado=camion, estado='EN_RUTA').order_by('orden_en_ruta') if camion else []
    
    lista_rutas = ''.join([f"<li>Pedido #{p.id} - Destino: {p.ubicacion_entrega.direccion}, {p.ubicacion_entrega.comuna} (Llegar y Cumplir)</li>" for p in rutas])
    
    html = f"<h1>Hoja de Ruta - Camión: {camion.patente if camion else 'Sin Asignar'}</h1><ol>{lista_rutas}</ol>"
    return HttpResponse(html)

@login_required(login_url='/admin/login/')
def panel_cliente(request):
    if request.user.perfilusuario.rol != 'CLIENTE': 
        return HttpResponse("Acceso denegado.")
        
    pedidos = Pedido.objects.filter(cliente__perfil__usuario=request.user)
    
    lista_pedidos = ''.join([f"<li>Pedido #{p.id} - Estado: {p.estado} - Fecha: {p.fecha_entrega_esperada}</li>" for p in pedidos])
    
    html = f"<h1>Mis Pedidos</h1><ul>{lista_pedidos}</ul>"
    return HttpResponse(html)

@login_required(login_url='/admin/login/')
def mapa_rutas_view(request):
    if request.user.perfilusuario.rol not in ['ADMIN', 'CONDUCTOR']: 
        return HttpResponse("Acceso denegado.")
        
    # Centrar el mapa usando el servidor público de Esri (sin API Key, estable para desarrollo)
    m = folium.Map(
        location=[-36.8201, -73.0444], 
        zoom_start=11, 
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles &copy; Esri'
    )
    
    # Origen desde la Planta en Chiguayante
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
        coordenadas_ruta = [origen_chiguayante]
        
        for p in pedidos_en_ruta:
            if p.ubicacion_entrega.latitud and p.ubicacion_entrega.longitud:
                coord = [float(p.ubicacion_entrega.latitud), float(p.ubicacion_entrega.longitud)]
                coordenadas_ruta.append(coord)
                
                folium.Marker(
                    coord, 
                    popup=f"Orden: {p.orden_en_ruta} | Pedido #{p.id}<br>Camión: {camion.patente}",
                    icon=folium.Icon(color=color_actual, icon="shopping-cart")
                ).add_to(m)
            
        # Volver a la planta al finalizar el turno
        coordenadas_ruta.append(origen_chiguayante)
        
        # Trazar la ruta completa
        folium.PolyLine(
            coordenadas_ruta, 
            color=color_actual, 
            weight=3, 
            opacity=0.7,
            tooltip=f"Ruta {camion.patente}"
        ).add_to(m)

    mapa_html = m._repr_html_()
    
    html_completo = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Mapa de Rutas - Emporio Alemán</title></head>
    <body style="font-family: sans-serif; margin: 0; padding: 20px; background: #f4f4f9;">
        <h2 style="text-align:center; color: #333;">Optimización de Última Milla</h2>
        <div style="text-align:center; margin-bottom: 15px;">
            <a href="/admin/dashboard/" style="padding: 10px 20px; background: #555; color: white; text-decoration: none; border-radius: 5px;">Volver al Panel</a>
        </div>
        <div style="width: 95%; max-width: 1200px; margin: 0 auto; border: 2px solid #ccc; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); overflow: hidden;">
            {mapa_html}
        </div>
    </body>
    </html>
    """
    
    return HttpResponse(html_completo)