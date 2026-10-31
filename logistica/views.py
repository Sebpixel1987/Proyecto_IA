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
    if request.user.perfilusuario.rol != 'ADMIN': return HttpResponse("Acceso denegado.")
    
    if request.method == 'POST':
        optimizar_y_asignar_rutas()
        return redirect('panel_admin')
        
    pedidos_preventa = Pedido.objects.filter(estado='PREVENTA')
    pedidos_en_ruta = Pedido.objects.filter(estado='EN_RUTA')
    
    html = f"""
    <h1>Panel de Logística (Admin)</h1>
    <p>Pedidos en Preventa (Pendientes de ruta): {pedidos_preventa.count()}</p>
    <form method="POST"><input type="hidden" name="csrfmiddlewaretoken" value="{request.META.get('CSRF_COOKIE', '')}">
        <button type="submit" style="padding: 10px; background: blue; color: white;">Ejecutar Optimización de Rutas</button>
    </form>
    <h2>Pedidos Asignados (En Ruta):</h2>
    <ul>
        {''.join([f"<li>Pedido #{p.id} - Camión: {p.camion_asignado.patente} - Orden: {p.orden_en_ruta}</li>" for p in pedidos_en_ruta])}
    </ul>
    """
    return HttpResponse(html)

@login_required(login_url='/admin/login/')
def panel_conductor(request):
    if request.user.perfilusuario.rol != 'CONDUCTOR': return HttpResponse("Acceso denegado.")
    camion = Camion.objects.filter(conductor__usuario=request.user).first()
    rutas = Pedido.objects.filter(camion_asignado=camion, estado='EN_RUTA').order_by('orden_en_ruta') if camion else []
    
    html = f"<h1>Hoja de Ruta - Camión: {camion.patente if camion else 'Sin Asignar'}</h1>"
    html += "<ol>" + ''.join([f"<li>Pedido #{p.id} - Destino: {p.ubicacion_entrega.direccion}, {p.ubicacion_entrega.comuna} (Llegar y Cumplir)</li>" for p in rutas]) + "</ol>"
    return HttpResponse(html)

@login_required(login_url='/admin/login/')
def panel_cliente(request):
    if request.user.perfilusuario.rol != 'CLIENTE': return HttpResponse("Acceso denegado.")
    pedidos = Pedido.objects.filter(cliente__perfil__usuario=request.user)
    
    html = "<h1>Mis Pedidos</h1><ul>"
    html += ''.join([f"<li>Pedido #{p.id} - Estado: {p.estado} - Fecha: {p.fecha_entrega_esperada}</li>" for p in pedidos]) + "</ul>"
    return HttpResponse(html)