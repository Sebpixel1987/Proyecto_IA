import folium
import requests
import json
import csv
import io
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.views.decorators.http import require_POST

from .models import (
    PerfilUsuario, Ubicacion, Cliente, Producto,
    Camion, Pedido, DetallePedido, RutaHistorica
)
from .forms import (
    UbicacionForm, PedidoExternoForm,
    RegistroClienteForm, ProductoForm
)
from .utils import (
    optimizar_y_asignar_rutas, ZONAS_OPERATIVAS,
    calcular_kpis_operativos, normalizar_y_evaluar_camion,
    validar_coordenadas_comuna
)


def home(request):
    if request.user.is_authenticated and hasattr(request.user, 'perfilusuario'):
        return redirect('dashboard')
    return render(request, 'logistica/home.html')


def login_rol(request):
    rol_sugerido = request.GET.get('rol', '')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if hasattr(user, 'perfilusuario'):
                login(request, user)
                return redirect('dashboard')
            elif user.is_superuser:
                PerfilUsuario.objects.create(usuario=user, rol='ADMIN')
                login(request, user)
                return redirect('panel_admin')
            else:
                messages.error(request, "Tu usuario no tiene un perfil logístico asignado.")
        else:
            messages.error(request, "Usuario o contraseña incorrectos.")

    return render(request, 'logistica/login.html', {'rol_sugerido': rol_sugerido})


def logout_rol(request):
    logout(request)
    return redirect('home')


@transaction.atomic
def registro_cliente(request):
    if request.method == 'POST':
        form = RegistroClienteForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            user = User.objects.create_user(
                username=cd['username'],
                email=cd['email'],
                password=cd['password'],
                first_name=cd['nombre_completo']
            )
            perfil = PerfilUsuario.objects.create(usuario=user, rol='CLIENTE')
            ubicacion = Ubicacion.objects.create(
                direccion=cd['direccion'],
                comuna=cd['comuna'],
                latitud=cd['latitud'],
                longitud=cd['longitud']
            )
            Cliente.objects.create(
                perfil=perfil,
                ubicacion_principal=ubicacion,
                telefono=cd['telefono'],
                ventana_horaria_inicio=cd['ventana_horaria_inicio'],
                ventana_horaria_fin=cd['ventana_horaria_fin']
            )
            login(request, user)
            messages.success(request, "¡Cuenta creada con éxito! Ya puedes realizar tus pedidos.")
            return redirect('panel_cliente')
    else:
        form = RegistroClienteForm(initial={
            'latitud': -36.8270,
            'longitud': -73.0503
        })

    return render(request, 'logistica/registro_cliente.html', {'form': form})


@login_required(login_url='login_rol')
def dashboard(request):
    if not hasattr(request.user, 'perfilusuario'):
        if request.user.is_superuser:
            PerfilUsuario.objects.create(usuario=request.user, rol='ADMIN')
        else:
            messages.error(request, "El usuario no tiene un PerfilUsuario asignado.")
            return redirect('home')

    rol = request.user.perfilusuario.rol
    if rol == 'ADMIN':
        return redirect('panel_admin')
    elif rol == 'CONDUCTOR':
        return redirect('panel_conductor')
    elif rol == 'CLIENTE':
        return redirect('panel_cliente')
    return redirect('home')


# ==============================================================================
# 1. PANEL ADMINISTRADOR (Gestión de Productos, Pedidos y Planificación)
# ==============================================================================
@login_required(login_url='login_rol')
def panel_admin(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        messages.error(request, "Acceso restringido a administradores de logística.")
        return redirect('dashboard')

    if request.method == 'POST' and request.POST.get('accion') == 'optimizar':
        zona_seleccionada = request.POST.get('zona_operativa', 'TODAS')
        fecha_despacho = request.POST.get('fecha_despacho') or None

        metricas_camiones = optimizar_y_asignar_rutas(
            zona_codigo=zona_seleccionada,
            fecha_filtro=fecha_despacho
        )

        camiones = Camion.objects.all()
        rutas_generadas = 0
        for camion in camiones:
            if camion.id in metricas_camiones:
                pedidos_asignados = Pedido.objects.filter(
                    camion_asignado=camion,
                    estado__in=['EN_RUTA', 'EN_PUNTO']
                )
                if pedidos_asignados.exists():
                    info_m = metricas_camiones[camion.id]
                    ruta_hist = RutaHistorica.objects.create(
                        camion=camion,
                        distancia_total_km=info_m['distancia_km'],
                        tiempo_estimado_min=info_m['tiempo_min']
                    )
                    ruta_hist.pedidos_incluidos.set(pedidos_asignados)
                    rutas_generadas += 1

        if rutas_generadas > 0:
            nombre_zona = ZONAS_OPERATIVAS.get(zona_seleccionada, {}).get('nombre', zona_seleccionada)
            messages.success(
                request,
                f"Planificación de rutas completada ({nombre_zona}): {rutas_generadas} camión(es) asignado(s)."
            )
        else:
            messages.warning(
                request,
                "No se encontraron pedidos pendientes para la zona/fecha seleccionada o faltan camiones disponibles."
            )
        return redirect('panel_admin')

    pedidos_pendientes = Pedido.objects.filter(
        estado__in=['PREVENTA', 'PREPARADO']
    ).select_related('cliente__perfil__usuario', 'ubicacion_entrega').prefetch_related('detalles__producto').order_by('fecha_entrega_esperada', 'id')

    pedidos_en_ruta = Pedido.objects.filter(
        estado__in=['EN_RUTA', 'EN_PUNTO']
    ).select_related('cliente__perfil__usuario', 'ubicacion_entrega', 'camion_asignado__conductor__usuario').prefetch_related('detalles__producto').order_by('camion_asignado', 'orden_en_ruta')

    rutas_por_camion = {}
    for p in pedidos_en_ruta:
        camion = p.camion_asignado
        if camion not in rutas_por_camion:
            rutas_por_camion[camion] = {
                'pedidos': [],
                'peso_total': 0
            }
        rutas_por_camion[camion]['pedidos'].append(p)
        rutas_por_camion[camion]['peso_total'] += float(p.peso_total_kg)

    productos = Producto.objects.all().order_by('nombre')
    producto_form = ProductoForm()
    kpis = calcular_kpis_operativos()

    context = {
        'pedidos_pendientes': pedidos_pendientes,
        'rutas_por_camion': rutas_por_camion,
        'todos_camiones': Camion.objects.select_related('conductor__usuario').all().order_by('patente'),
        'conductores': PerfilUsuario.objects.filter(rol='CONDUCTOR').select_related('usuario').order_by('usuario__username'),
        'productos': productos,
        'producto_form': producto_form,
        'total_camiones_activos': len(rutas_por_camion),
        'zonas_operativas': ZONAS_OPERATIVAS,
        'kpis': kpis,
    }
    return render(request, 'logistica/panel_admin.html', context)


@login_required(login_url='login_rol')
def crear_producto(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return redirect('dashboard')

    if request.method == 'POST':
        form = ProductoForm(request.POST)
        if form.is_valid():
            prod = form.save()
            messages.success(request, f"Producto '{prod.nombre}' ({prod.peso_kg} kg) registrado correctamente.")
        else:
            messages.error(request, "Error al registrar el producto. Revisa los datos ingresados.")
    return redirect('panel_admin')


@login_required(login_url='login_rol')
def actualizar_stock_producto(request, pk):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return redirect('dashboard')

    if request.method == 'POST':
        producto = get_object_or_404(Producto, pk=pk)
        nuevo_stock = request.POST.get('cantidad_disponible')
        if nuevo_stock is not None and nuevo_stock.isdigit():
            producto.cantidad_disponible = int(nuevo_stock)
            producto.save()
            messages.success(request, f"Stock de '{producto.nombre}' actualizado a {producto.cantidad_disponible} un.")
    return redirect('panel_admin')


# ==============================================================================
# 2. PANEL CLIENTE (Realizar pedidos con restricciones y seguimiento)
# ==============================================================================
@login_required(login_url='login_rol')
@transaction.atomic
def panel_cliente(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'CLIENTE':
        messages.error(request, "Acceso restringido a clientes registrados.")
        return redirect('dashboard')

    cliente = get_object_or_404(Cliente, perfil=request.user.perfilusuario)
    productos_disponibles = Producto.objects.filter(cantidad_disponible__gt=0).order_by('nombre')

    if request.method == 'POST':
        fecha_entrega = request.POST.get('fecha_entrega_esperada')
        observaciones = request.POST.get('observaciones', '').strip()
        ventana_inicio = request.POST.get('ventana_horaria_inicio')
        ventana_fin = request.POST.get('ventana_horaria_fin')

        if ventana_inicio:
            cliente.ventana_horaria_inicio = ventana_inicio
        if ventana_fin:
            cliente.ventana_horaria_fin = ventana_fin
        cliente.save()

        items_seleccionados = []
        for prod in productos_disponibles:
            cant_str = request.POST.get(f'cantidad_{prod.id}', '0')
            if cant_str.isdigit() and int(cant_str) > 0:
                cant = int(cant_str)
                if cant <= prod.cantidad_disponible:
                    items_seleccionados.append((prod, cant))
                else:
                    messages.error(request, f"Stock insuficiente para {prod.nombre} (disponible: {prod.cantidad_disponible}).")
                    return redirect('panel_cliente')

        if not items_seleccionados:
            messages.warning(request, "Debes seleccionar al menos 1 producto con cantidad mayor a 0.")
            return redirect('panel_cliente')

        if not cliente.ubicacion_principal:
            messages.error(request, "No tienes una ubicación de entrega configurada. Contacta a soporte.")
            return redirect('panel_cliente')

        pedido = Pedido.objects.create(
            cliente=cliente,
            ubicacion_entrega=cliente.ubicacion_principal,
            estado='PREVENTA',
            fecha_entrega_esperada=fecha_entrega or date.today(),
            observaciones=observaciones
        )

        for prod, cant in items_seleccionados:
            DetallePedido.objects.create(
                pedido=pedido,
                producto=prod,
                cantidad=cant
            )
            prod.cantidad_disponible -= cant
            prod.save()

        messages.success(request, f"Pedido #{pedido.id} ingresado correctamente ({pedido.peso_total_kg} kg total).")
        return redirect('panel_cliente')

    mis_pedidos = Pedido.objects.filter(cliente=cliente).prefetch_related('detalles__producto').order_by('-id')

    context = {
        'cliente': cliente,
        'productos': productos_disponibles,
        'mis_pedidos': mis_pedidos,
        'hoy': date.today().isoformat(),
    }
    return render(request, 'logistica/panel_cliente.html', context)


# ==============================================================================
# 3. PANEL CONDUCTOR (Trazabilidad Paso a Paso, Comprobante y Hoja Imprimible)
# ==============================================================================
MOTIVOS_NO_ENTREGA = [
    'Local cerrado fuera de horario',
    'Sin personal para recepción de mercadería',
    'Rechazo por temperatura / cadena de frío',
    'Dirección incorrecta o acceso bloqueado',
    'Cliente solicita reprogramar despacho',
]


@login_required(login_url='login_rol')
def panel_conductor(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'CONDUCTOR':
        messages.error(request, "Acceso restringido a conductores de flota.")
        return redirect('dashboard')

    camion = Camion.objects.filter(conductor=request.user.perfilusuario).first()
    camiones_disponibles = []
    paradas = []
    historial_hoy = []
    peso_carga_total = 0
    entregados_hoy = 0
    no_entregados_hoy = 0

    if not camion:
        camiones_disponibles = Camion.objects.filter(conductor__isnull=True).order_by('patente')
    else:
        paradas = Pedido.objects.filter(
            camion_asignado=camion,
            estado__in=['EN_RUTA', 'EN_PUNTO']
        ).select_related(
            'cliente__perfil__usuario', 'ubicacion_entrega'
        ).prefetch_related('detalles__producto').order_by('orden_en_ruta', 'id')

        peso_carga_total = sum(float(p.peso_total_kg) for p in paradas)

        hoy = timezone.localdate()
        historial_hoy = Pedido.objects.filter(
            camion_asignado=camion,
            estado__in=['ENTREGADO', 'NO_ENTREGADO'],
            hora_cierre_entrega__date=hoy
        ).select_related('cliente__perfil__usuario', 'ubicacion_entrega').order_by('-hora_cierre_entrega')

        entregados_hoy = historial_hoy.filter(estado='ENTREGADO').count()
        no_entregados_hoy = historial_hoy.filter(estado='NO_ENTREGADO').count()

    context = {
        'camion': camion,
        'camiones_disponibles': camiones_disponibles,
        'paradas': paradas,
        'historial_hoy': historial_hoy,
        'peso_carga_total': peso_carga_total,
        'entregados_hoy': entregados_hoy,
        'no_entregados_hoy': no_entregados_hoy,
        'motivos_no_entrega': MOTIVOS_NO_ENTREGA,
    }
    return render(request, 'logistica/panel_conductor.html', context)


@login_required(login_url='login_rol')
@require_POST
def registrar_llegada_punto(request, pedido_id):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'CONDUCTOR':
        return redirect('dashboard')

    camion = Camion.objects.filter(conductor=request.user.perfilusuario).first()
    pedido = get_object_or_404(Pedido, id=pedido_id, camion_asignado=camion)

    if pedido.estado == 'EN_RUTA':
        pedido.estado = 'EN_PUNTO'
        if not pedido.hora_llegada:
            pedido.hora_llegada = timezone.now()
        pedido.save(update_fields=['estado', 'hora_llegada'])
        hora_txt = timezone.localtime(pedido.hora_llegada).strftime('%H:%M:%S')
        messages.info(request, f"Llegada registrada para el pedido #{pedido.id} a las {hora_txt}.")

    return redirect('panel_conductor')


@login_required(login_url='login_rol')
@require_POST
def marcar_pedido_entregado(request, pedido_id):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'CONDUCTOR':
        return redirect('dashboard')

    camion = Camion.objects.filter(conductor=request.user.perfilusuario).first()
    pedido = get_object_or_404(Pedido, id=pedido_id, camion_asignado=camion)

    ahora = timezone.now()
    if not pedido.hora_llegada:
        pedido.hora_llegada = ahora

    pedido.hora_cierre_entrega = ahora
    pedido.estado = 'ENTREGADO'
    pedido.receptor_entrega = request.POST.get('receptor_entrega', '').strip() or 'Recepción conforme en local'
    pedido.observacion_conductor = request.POST.get('observacion_conductor', '').strip()
    pedido.save(update_fields=[
        'hora_llegada', 'hora_cierre_entrega', 'estado',
        'receptor_entrega', 'observacion_conductor'
    ])

    messages.success(request, f"Pedido #{pedido.id} cerrado como ENTREGADO. Comprobante digital generado.")
    return redirect('panel_conductor')


@login_required(login_url='login_rol')
@require_POST
def marcar_pedido_no_entregado(request, pedido_id):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'CONDUCTOR':
        return redirect('dashboard')

    camion = Camion.objects.filter(conductor=request.user.perfilusuario).first()
    pedido = get_object_or_404(Pedido, id=pedido_id, camion_asignado=camion)

    motivo = request.POST.get('motivo_no_entrega', '').strip()
    if not motivo:
        messages.error(request, "Debes seleccionar un motivo para registrar la no entrega.")
        return redirect('panel_conductor')

    ahora = timezone.now()
    if not pedido.hora_llegada:
        pedido.hora_llegada = ahora

    pedido.hora_cierre_entrega = ahora
    pedido.estado = 'NO_ENTREGADO'
    pedido.motivo_no_entrega = motivo
    pedido.observacion_conductor = request.POST.get('observacion_conductor', '').strip()
    pedido.save(update_fields=[
        'hora_llegada', 'hora_cierre_entrega', 'estado',
        'motivo_no_entrega', 'observacion_conductor'
    ])

    messages.warning(request, f"Pedido #{pedido.id} registrado como NO ENTREGADO ({motivo}).")
    return redirect('panel_conductor')


@login_required(login_url='login_rol')
def comprobante_entrega_pedido(request, pedido_id):
    if not hasattr(request.user, 'perfilusuario'):
        return redirect('home')

    perfil = request.user.perfilusuario
    pedido = get_object_or_404(
        Pedido.objects.select_related(
            'cliente__perfil__usuario', 'ubicacion_entrega', 'camion_asignado__conductor__usuario'
        ).prefetch_related('detalles__producto'),
        id=pedido_id
    )

    if perfil.rol == 'CONDUCTOR' and (not pedido.camion_asignado or pedido.camion_asignado.conductor != perfil):
        return HttpResponse("Acceso denegado a este comprobante.")
    elif perfil.rol == 'CLIENTE' and pedido.cliente.perfil != perfil:
        return HttpResponse("Acceso denegado a este comprobante.")

    llegada_txt = timezone.localtime(pedido.hora_llegada).strftime('%d/%m/%Y %H:%M:%S') if pedido.hora_llegada else 'No registrada'
    cierre_txt = timezone.localtime(pedido.hora_cierre_entrega).strftime('%d/%m/%Y %H:%M:%S') if pedido.hora_cierre_entrega else 'Pendiente de cierre'

    duracion_txt = '—'
    if pedido.hora_llegada and pedido.hora_cierre_entrega:
        segundos = max(0, int((pedido.hora_cierre_entrega - pedido.hora_llegada).total_seconds()))
        minutos = segundos // 60
        seg_rest = segundos % 60
        duracion_txt = f"{minutos} min {seg_rest} seg"

    if pedido.estado == 'ENTREGADO':
        badge_estado = '<span class="badge bg-success fs-6">ENTREGADO CONFORME</span>'
        bloque_resultado = f"<p class='mb-1'><strong>Recibido por:</strong> {pedido.receptor_entrega or 'Recepción en local'}</p>"
    elif pedido.estado == 'NO_ENTREGADO':
        badge_estado = '<span class="badge bg-danger fs-6">NO ENTREGADO</span>'
        bloque_resultado = f"<p class='mb-1 text-danger'><strong>Motivo de incidencia:</strong> {pedido.motivo_no_entrega}</p>"
    else:
        badge_estado = f'<span class="badge bg-warning text-dark fs-6">{pedido.estado}</span>'
        bloque_resultado = "<p class='mb-1 text-muted'>Pedido aún en proceso de despacho.</p>"

    filas_productos = ""
    for d in pedido.detalles.all():
        subtotal_kg = round(float(d.producto.peso_kg) * d.cantidad, 2)
        filas_productos += f"<tr><td>{d.producto.nombre}</td><td class='text-center'>{d.cantidad}</td><td class='text-end'>{subtotal_kg} kg</td></tr>"

    patente = pedido.camion_asignado.patente if pedido.camion_asignado else 'Sin asignar'
    conductor = pedido.camion_asignado.conductor.usuario.get_full_name() or pedido.camion_asignado.conductor.usuario.username if (pedido.camion_asignado and pedido.camion_asignado.conductor) else 'Sin asignar'

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Comprobante Digital Pedido #{pedido.id} - Emporio Alemán</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
        <style>@media print {{ .no-print {{ display: none !important; }} }}</style>
    </head>
    <body style="background-color: #f4f6f9;">
        <div class="container my-4" style="max-width: 760px;">
            <div class="d-flex justify-content-between align-items-center mb-3 no-print">
                <button onclick="history.back()" class="btn btn-outline-secondary btn-sm">
                    <i class="fa-solid fa-arrow-left me-1"></i> Volver
                </button>
                <button onclick="window.print()" class="btn btn-dark btn-sm">
                    <i class="fa-solid fa-print me-1"></i> Imprimir / Guardar PDF
                </button>
            </div>
            <div class="card shadow border-0">
                <div class="card-header bg-dark text-white d-flex justify-content-between align-items-center py-3">
                    <div>
                        <h5 class="mb-0 fw-bold">EMPORIO ALEMÁN S.A.</h5>
                        <small class="text-warning">Comprobante Digital de Ejecución en Última Milla</small>
                    </div>
                    <div class="text-end">
                        <span class="fw-bold fs-5">Pedido #{pedido.id}</span>
                    </div>
                </div>
                <div class="card-body p-4">
                    <div class="d-flex justify-content-between align-items-center border-bottom pb-3 mb-3">
                        <div>
                            <div class="text-muted small">Estado de Ejecución</div>
                            {badge_estado}
                        </div>
                        <div class="text-end small">
                            <div><strong>Camión FOTON:</strong> {patente}</div>
                            <div><strong>Conductor:</strong> {conductor}</div>
                        </div>
                    </div>

                    <div class="row g-3 mb-3">
                        <div class="col-md-6">
                            <div class="p-3 bg-light rounded h-100">
                                <h6 class="fw-bold text-uppercase small text-muted">Datos del Cliente</h6>
                                <p class="mb-1 fw-bold">{pedido.cliente}</p>
                                <p class="mb-0 small">{pedido.ubicacion_entrega.direccion}, {pedido.ubicacion_entrega.comuna}</p>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="p-3 bg-light rounded h-100">
                                <h6 class="fw-bold text-uppercase small text-muted">Trazabilidad Horaria</h6>
                                <p class="mb-1 small"><strong>Llegada al punto:</strong> {llegada_txt}</p>
                                <p class="mb-1 small"><strong>Cierre de gestión:</strong> {cierre_txt}</p>
                                <p class="mb-0 small"><strong>Tiempo en punto:</strong> {duracion_txt}</p>
                            </div>
                        </div>
                    </div>

                    <div class="alert alert-secondary mb-3">
                        {bloque_resultado}
                        <p class="mb-0 small"><strong>Observaciones en terreno:</strong> {pedido.observacion_conductor or 'Sin observaciones adicionales.'}</p>
                    </div>

                    <h6 class="fw-bold text-uppercase small text-muted mt-4">Detalle de Carga Despachada ({pedido.peso_total_kg} kg total)</h6>
                    <table class="table table-sm table-bordered">
                        <thead class="table-light">
                            <tr>
                                <th>Producto</th>
                                <th class="text-center">Cantidad</th>
                                <th class="text-end">Peso</th>
                            </tr>
                        </thead>
                        <tbody>{filas_productos}</tbody>
                    </table>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)


@login_required(login_url='login_rol')
def hoja_ruta_imprimible(request, camion_id):
    if not hasattr(request.user, 'perfilusuario'):
        return redirect('home')

    rol = request.user.perfilusuario.rol
    camion = get_object_or_404(Camion, id=camion_id)

    if rol == 'CONDUCTOR' and camion.conductor != request.user.perfilusuario:
        messages.error(request, "No tienes permiso para ver la hoja de ruta de otro vehículo.")
        return redirect('panel_conductor')
    elif rol not in ['ADMIN', 'CONDUCTOR']:
        return redirect('dashboard')

    paradas = Pedido.objects.filter(
        camion_asignado=camion,
        estado__in=['EN_RUTA', 'EN_PUNTO']
    ).select_related(
        'cliente__perfil__usuario', 'ubicacion_entrega'
    ).prefetch_related('detalles__producto').order_by('orden_en_ruta')

    peso_total_kg = sum(float(p.peso_total_kg) for p in paradas)
    porcentaje_carga = round((peso_total_kg / float(camion.capacidad_max_kg)) * 100, 1) if camion.capacidad_max_kg else 0
    total_bultos = sum(
        sum(d.cantidad for d in p.detalles.all())
        for p in paradas
    )

    puntos_mapa = []
    for p in paradas:
        if p.ubicacion_entrega and p.ubicacion_entrega.latitud and p.ubicacion_entrega.longitud:
            puntos_mapa.append({
                'orden': p.orden_en_ruta or 0,
                'pedido_id': p.id,
                'cliente': str(p.cliente),
                'direccion': f"{p.ubicacion_entrega.direccion}, {p.ubicacion_entrega.comuna}",
                'lat': float(p.ubicacion_entrega.latitud),
                'lon': float(p.ubicacion_entrega.longitud),
            })

    context = {
        'camion': camion,
        'paradas': paradas,
        'puntos_mapa_json': json.dumps(puntos_mapa),
        'peso_total_kg': peso_total_kg,
        'porcentaje_carga': porcentaje_carga,
        'total_bultos': total_bultos,
        'fecha_emision': timezone.now(),
        'volver_url': 'panel_conductor' if rol == 'CONDUCTOR' else 'panel_admin',
    }
    return render(request, 'logistica/hoja_ruta_print.html', context)


# ==============================================================================
# 4. MAPA DE RECORRIDOS + HISTORIAL + INGRESO MANUAL
# ==============================================================================
@login_required(login_url='login_rol')
def mapa_rutas_view(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol not in ['ADMIN', 'CONDUCTOR']:
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

    if request.user.perfilusuario.rol == 'CONDUCTOR':
        camiones = Camion.objects.filter(conductor=request.user.perfilusuario)
    else:
        camiones = Camion.objects.all()

    colores_ruta = ['blue', 'green', 'red', 'purple', 'orange']

    for idx, camion in enumerate(camiones):
        pedidos_en_ruta = Pedido.objects.filter(
            camion_asignado=camion,
            estado__in=['EN_RUTA', 'EN_PUNTO']
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
    volver_url = "/panel-conductor/" if request.user.perfilusuario.rol == 'CONDUCTOR' else "/panel-admin/"

    html_completo = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Mapa de Recorridos - Emporio Alemán</title></head>
    <body style="font-family: sans-serif; margin: 0; padding: 20px; background: #f4f4f9;">
        <h2 style="text-align:center; color: #333;">Mapa de Recorridos de Última Milla</h2>
        <div style="text-align:center; margin-bottom: 15px;">
            <a href="{volver_url}" style="padding: 10px 20px; background: #0d233a; color: white; text-decoration: none; border-radius: 5px;">Volver al Panel</a>
        </div>
        <div style="width: 95%; max-width: 1200px; margin: 0 auto; border: 2px solid #ccc; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); overflow: hidden;">
            {mapa_html}
        </div>
    </body>
    </html>
    """
    return HttpResponse(html_completo)


@login_required(login_url='login_rol')
def historial_rutas(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
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


@login_required(login_url='login_rol')
def detalle_ruta_historica(request, pk):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return HttpResponse("Acceso denegado.")

    ruta = get_object_or_404(RutaHistorica, pk=pk)
    patente = ruta.camion.patente if ruta.camion else "N/A"

    filas_pedidos = ""
    for p in ruta.pedidos_incluidos.all().order_by('orden_en_ruta', 'id'):
        llegada = timezone.localtime(p.hora_llegada).strftime('%H:%M') if p.hora_llegada else '—'
        cierre = timezone.localtime(p.hora_cierre_entrega).strftime('%H:%M') if p.hora_cierre_entrega else '—'

        if p.estado == 'ENTREGADO':
            badge = '<span class="badge bg-success">Entregado</span>'
            detalle_txt = f"Recibe: {p.receptor_entrega or 'Conforme'}"
        elif p.estado == 'NO_ENTREGADO':
            badge = '<span class="badge bg-danger">No Entregado</span>'
            detalle_txt = f"Motivo: {p.motivo_no_entrega}"
        else:
            badge = f'<span class="badge bg-warning text-dark">{p.estado}</span>'
            detalle_txt = "En curso"

        filas_pedidos += f"""
        <tr>
            <td><strong>#{p.id}</strong></td>
            <td>{p.cliente}</td>
            <td>{p.ubicacion_entrega.direccion if p.ubicacion_entrega else 'N/A'}</td>
            <td>{badge}</td>
            <td>{llegada} / {cierre}</td>
            <td class="small">{detalle_txt}</td>
            <td class="text-end">
                <a href="/comprobante/pedido/{p.id}/" class="btn btn-sm btn-outline-dark">
                    <i class="fa-solid fa-file-invoice me-1"></i> Comprobante
                </a>
            </td>
        </tr>
        """

    if not filas_pedidos:
        filas_pedidos = '<tr><td colspan="7" class="text-center text-muted py-3">Sin pedidos asociados.</td></tr>'

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
                <h2><i class="fa-solid fa-clipboard-check me-2 text-primary"></i>Comprobante de Ruta #{ruta.id}</h2>
                <a href="/historial/" class="btn btn-outline-secondary"><i class="fa-solid fa-arrow-left me-1"></i> Volver al Historial</a>
            </div>
            <div class="card shadow border-0 mb-4">
                <div class="card-header bg-dark text-white"><h5>Resumen del Despacho</h5></div>
                <div class="card-body row">
                    <div class="col-md-3"><strong>Camión FOTON:</strong> {patente}</div>
                    <div class="col-md-3"><strong>Fecha:</strong> {ruta.fecha_ejecucion.strftime('%d/%m/%Y %H:%M')}</div>
                    <div class="col-md-3"><strong>Distancia Est.:</strong> {ruta.distancia_total_km} km</div>
                    <div class="col-md-3"><strong>Tiempo Est.:</strong> {ruta.tiempo_estimado_min} min</div>
                </div>
            </div>
            <div class="card shadow border-0">
                <div class="card-header bg-white"><h6 class="mb-0 fw-bold">Trazabilidad por Parada</h6></div>
                <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                        <thead class="table-light">
                            <tr>
                                <th>Pedido</th>
                                <th>Cliente</th>
                                <th>Dirección</th>
                                <th>Estado</th>
                                <th>Llegada / Cierre</th>
                                <th>Resultado</th>
                                <th class="text-end">Respaldo</th>
                            </tr>
                        </thead>
                        <tbody>{filas_pedidos}</tbody>
                    </table>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)


@login_required(login_url='login_rol')
def registrar_ubicacion_y_pedido(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return HttpResponse("Acceso denegado.")

    if request.method == 'POST':
        ubicacion_form = UbicacionForm(request.POST)
        pedido_form = PedidoExternoForm(request.POST)

        if ubicacion_form.is_valid() and pedido_form.is_valid():
            ubicacion = ubicacion_form.save()
            pedido = pedido_form.save(commit=False)
            pedido.ubicacion_entrega = ubicacion
            pedido.save()
            messages.success(request, f"Pedido #{pedido.id} ingresado manualmente.")
            return redirect('panel_admin')
    else:
        ubicacion_form = UbicacionForm()
        pedido_form = PedidoExternoForm()

    csrf_token = get_token(request)
    form_html = f"""
    <form method="POST">
        <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}">
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
        <title>Ingreso Manual - Emporio Alemán</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    </head>
    <body style="background-color: #f4f6f9;">
        <div class="container mt-4 mb-5">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card shadow border-0">
                        <div class="card-header bg-dark text-white">
                            <h4 class="mb-0"><i class="fa-solid fa-map-marker-alt me-2"></i>Ingreso Manual de Ubicación y Pedido</h4>
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


# ==============================================================================
# 5. CARGA MASIVA EXCEL (.XLSX) / CSV Y PLANTILLA ESTANDARIZADA
# ==============================================================================
COLUMNAS_PLANTILLA = [
    'cliente_usuario',
    'nombre_local',
    'telefono',
    'direccion',
    'comuna',
    'latitud',
    'longitud',
    'fecha_entrega',
    'ventana_inicio',
    'ventana_fin',
    'producto',
    'peso_unitario_kg',
    'cantidad',
    'observaciones',
]

ALIAS_COLUMNAS_PLANTA = {
    'codigo_cliente': 'cliente_usuario',
    'cod_cliente': 'cliente_usuario',
    'rut_cliente': 'cliente_usuario',
    'razon_social': 'nombre_local',
    'nombre_cliente': 'nombre_local',
    'cliente': 'nombre_local',
    'fono': 'telefono',
    'celular': 'telefono',
    'direccion_entrega': 'direccion',
    'domicilio': 'direccion',
    'ciudad': 'comuna',
    'lat': 'latitud',
    'lon': 'longitud',
    'lng': 'longitud',
    'fecha_despacho': 'fecha_entrega',
    'fecha': 'fecha_entrega',
    'hora_inicio': 'ventana_inicio',
    'hora_fin': 'ventana_fin',
    'descripcion': 'producto',
    'sku': 'producto',
    'peso_kg': 'peso_unitario_kg',
    'kilos': 'peso_unitario_kg',
    'cajas': 'cantidad',
    'unidades': 'cantidad',
    'obs': 'observaciones',
    'notas': 'observaciones',
}


def _normalizar_header(header):
    clave = str(header).strip().lower() if header is not None else ''
    return ALIAS_COLUMNAS_PLANTA.get(clave, clave)


@login_required(login_url='login_rol')
def descargar_plantilla_carga(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return redirect('dashboard')

    formato = request.GET.get('formato', 'xlsx').lower()
    filas_ejemplo = [
        [
            'minimarket_sol', 'Minimarket El Sol', '+56987654321',
            'Av. O’Higgins 1250', 'Concepción', -36.8269, -73.0498,
            date.today().isoformat(), '09:00', '13:30',
            'Queso Gauda Laminado 5kg', 5.00, 4, 'Entregar por acceso lateral'
        ],
        [
            'minimarket_sol', 'Minimarket El Sol', '+56987654321',
            'Av. O’Higgins 1250', 'Concepción', -36.8269, -73.0498,
            date.today().isoformat(), '09:00', '13:30',
            'Jamón Pierna Cocido 3kg', 3.00, 6, 'Entregar por acceso lateral'
        ],
        [
            'fiambreria_puerto', 'Fiambrería Puerto Talcahuano', '+56976543210',
            'Av. Colón 3420', 'Talcahuano', -36.7345, -73.1128,
            date.today().isoformat(), '10:00', '16:00',
            'Salame Italiano 2kg', 2.00, 10, 'Llamar al llegar'
        ],
        [
            'almacen_sanpedro', 'Almacén San Pedro', '+56965432109',
            'Av. Pedro Aguirre Cerda 890', 'San Pedro de la Paz', -36.8441, -73.1032,
            date.today().isoformat(), '08:30', '12:30',
            'Queso Mantecoso 4kg', 4.00, 5, ''
        ],
    ]

    if formato == 'xlsx':
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Pedidos_Emporio"

            ws.append(COLUMNAS_PLANTILLA)
            header_fill = PatternFill(start_color="0D233A", end_color="0D233A", fill_type="solid")
            header_font = Font(color="FFFFFF", bold=True)
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font

            for fila in filas_ejemplo:
                ws.append(fila)

            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = max_len + 4

            buffer = io.BytesIO()
            wb.save(buffer)
            buffer.seek(0)

            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename="plantilla_carga_emporio.xlsx"'
            return response
        except ImportError:
            pass

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="plantilla_carga_emporio.csv"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')
    writer.writerow(COLUMNAS_PLANTILLA)
    for fila in filas_ejemplo:
        writer.writerow(fila)
    return response


def _leer_filas_archivo(archivo):
    nombre = archivo.name.lower()
    filas_raw = []

    if nombre.endswith('.xlsx'):
        try:
            import openpyxl
        except ImportError:
            raise ValueError("El servidor no tiene instalado 'openpyxl'. Ejecuta: pip install openpyxl o sube un archivo .csv.")

        wb = openpyxl.load_workbook(archivo, data_only=True)
        ws = wb.active
        iter_rows = list(ws.iter_rows(values_only=True))
        if not iter_rows:
            raise ValueError("El archivo Excel está vacío.")

        headers = [_normalizar_header(h) for h in iter_rows[0]]
        for idx, row in enumerate(iter_rows[1:], start=2):
            if all(v is None or str(v).strip() == '' for v in row):
                continue
            fila_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
            fila_dict['_num_fila'] = idx
            filas_raw.append(fila_dict)

    elif nombre.endswith('.csv'):
        contenido = archivo.read().decode('utf-8-sig')
        muestra = contenido[:1024]
        delimitador = ';' if muestra.count(';') >= muestra.count(',') else ','
        reader = csv.DictReader(io.StringIO(contenido), delimiter=delimitador)
        if not reader.fieldnames:
            raise ValueError("El archivo CSV no tiene encabezados válidos.")

        for idx, row in enumerate(reader, start=2):
            if all(v is None or str(v).strip() == '' for v in row.values()):
                continue
            fila_dict = {_normalizar_header(k): v for k, v in row.items() if k}
            fila_dict['_num_fila'] = idx
            filas_raw.append(fila_dict)
    else:
        raise ValueError("Formato no soportado. Sube un archivo .xlsx o .csv.")

    return filas_raw


def _parsear_hora(valor):
    if valor is None or str(valor).strip() == '':
        return None
    if hasattr(valor, 'hour') and hasattr(valor, 'minute'):
        return valor if not isinstance(valor, datetime) else valor.time()
    texto = str(valor).strip()
    for fmt in ('%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime(texto, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Formato de hora inválido ('{texto}'). Usa HH:MM (ej: 09:00).")


def _parsear_fecha(valor):
    if valor is None or str(valor).strip() == '':
        return date.today()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Formato de fecha inválido ('{texto}'). Usa AAAA-MM-DD o DD/MM/AAAA.")


@login_required(login_url='login_rol')
def carga_masiva_datos(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return redirect('dashboard')

    resumen_importacion = None
    errores_fila = []

    if request.method == 'POST' and request.FILES.get('archivo_datos'):
        archivo = request.FILES['archivo_datos']
        try:
            filas = _leer_filas_archivo(archivo)
            if not filas:
                raise ValueError("No se encontraron filas con datos para procesar.")

            faltantes = [c for c in COLUMNAS_PLANTILLA if c not in filas[0]]
            if faltantes:
                raise ValueError(f"Faltan columnas obligatorias en el archivo: {', '.join(faltantes)}")

            with transaction.atomic():
                clientes_creados = 0
                pedidos_creados = 0
                items_creados = 0
                pedidos_agrupados = {}

                for fila in filas:
                    num = fila['_num_fila']
                    try:
                        username = str(fila.get('cliente_usuario') or '').strip()
                        nombre_local = str(fila.get('nombre_local') or username).strip()
                        telefono = str(fila.get('telefono') or 'Sin teléfono').strip()
                        direccion = str(fila.get('direccion') or '').strip()
                        comuna = str(fila.get('comuna') or 'Concepción').strip()
                        prod_nombre = str(fila.get('producto') or '').strip()
                        obs = str(fila.get('observaciones') or '').strip()

                        if not username or not direccion or not prod_nombre:
                            raise ValueError("Los campos 'cliente_usuario', 'direccion' y 'producto' son obligatorios.")

                        lat = Decimal(str(fila.get('latitud')).replace(',', '.'))
                        lon = Decimal(str(fila.get('longitud')).replace(',', '.'))

                        es_valido_geo, error_geo = validar_coordenadas_comuna(comuna, lat, lon)
                        if not es_valido_geo:
                            raise ValueError(error_geo)

                        peso_unit = Decimal(str(fila.get('peso_unitario_kg') or '1.0').replace(',', '.'))
                        cantidad = int(float(fila.get('cantidad') or 1))

                        if cantidad <= 0 or peso_unit <= 0:
                            raise ValueError("La cantidad y el peso unitario deben ser mayores a 0.")

                        fecha_ent = _parsear_fecha(fila.get('fecha_entrega'))
                        v_inicio = _parsear_hora(fila.get('ventana_inicio'))
                        v_fin = _parsear_hora(fila.get('ventana_fin'))

                        user, u_creado = User.objects.get_or_create(
                            username=username,
                            defaults={'first_name': nombre_local}
                        )
                        if u_creado:
                            user.set_password('1234')
                            user.save()

                        perfil, _ = PerfilUsuario.objects.get_or_create(
                            usuario=user,
                            defaults={'rol': 'CLIENTE'}
                        )

                        ubicacion, _ = Ubicacion.objects.get_or_create(
                            direccion=direccion,
                            comuna=comuna,
                            defaults={'latitud': lat, 'longitud': lon}
                        )
                        if ubicacion.latitud != lat or ubicacion.longitud != lon:
                            ubicacion.latitud = lat
                            ubicacion.longitud = lon
                            ubicacion.save()

                        cliente, c_creado = Cliente.objects.get_or_create(
                            perfil=perfil,
                            defaults={
                                'ubicacion_principal': ubicacion,
                                'telefono': telefono,
                                'ventana_horaria_inicio': v_inicio,
                                'ventana_horaria_fin': v_fin,
                            }
                        )
                        if c_creado:
                            clientes_creados += 1
                        else:
                            cliente.ubicacion_principal = ubicacion
                            if telefono:
                                cliente.telefono = telefono
                            if v_inicio:
                                cliente.ventana_horaria_inicio = v_inicio
                            if v_fin:
                                cliente.ventana_horaria_fin = v_fin
                            cliente.save()

                        producto, _ = Producto.objects.get_or_create(
                            nombre__iexact=prod_nombre,
                            defaults={
                                'nombre': prod_nombre,
                                'peso_kg': peso_unit,
                                'cantidad_disponible': 100
                            }
                        )

                        clave_pedido = (cliente.id, fecha_ent)
                        if clave_pedido not in pedidos_agrupados:
                            pedido = Pedido.objects.create(
                                cliente=cliente,
                                ubicacion_entrega=ubicacion,
                                estado='PREVENTA',
                                fecha_entrega_esperada=fecha_ent,
                                observaciones=obs
                            )
                            pedidos_agrupados[clave_pedido] = pedido
                            pedidos_creados += 1
                        else:
                            pedido = pedidos_agrupados[clave_pedido]
                            if obs and obs not in (pedido.observaciones or ''):
                                pedido.observaciones = f"{pedido.observaciones} | {obs}".strip(' |')
                                pedido.save()

                        DetallePedido.objects.create(
                            pedido=pedido,
                            producto=producto,
                            cantidad=cantidad
                        )
                        items_creados += 1

                    except (ValueError, InvalidOperation, TypeError) as e_fila:
                        errores_fila.append(f"Fila {num}: {str(e_fila)}")

                if errores_fila:
                    raise ValueError("Se detectaron errores en algunas filas; no se guardó ningún registro.")

                resumen_importacion = {
                    'clientes_creados': clientes_creados,
                    'pedidos_creados': pedidos_creados,
                    'items_creados': items_creados,
                }
                messages.success(
                    request,
                    f"Carga masiva exitosa: {pedidos_creados} pedido(s), {items_creados} línea(s) de producto y {clientes_creados} cliente(s) nuevo(s)."
                )

        except Exception as e:
            messages.error(request, f"Error en la importación: {str(e)}")

    context = {
        'columnas': COLUMNAS_PLANTILLA,
        'resumen_importacion': resumen_importacion,
        'errores_fila': errores_fila,
    }
    return render(request, 'logistica/carga_masiva.html', context)


# ==============================================================================
# 6. EDICIÓN Y REPROGRAMACIÓN MANUAL DE RUTAS (PANEL ADMIN)
# ==============================================================================
@login_required(login_url='login_rol')
@require_POST
def mover_parada_ruta(request, pedido_id, direccion):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return redirect('dashboard')

    pedido = get_object_or_404(Pedido, id=pedido_id)
    if not pedido.camion_asignado:
        messages.error(request, 'El pedido no tiene un camión asignado.')
        return redirect('panel_admin')

    with transaction.atomic():
        paradas = list(
            Pedido.objects.filter(
                camion_asignado=pedido.camion_asignado,
                estado__in=['EN_RUTA', 'EN_PUNTO']
            ).order_by('orden_en_ruta', 'id')
        )

        ids = [p.id for p in paradas]
        if pedido.id in ids:
            pos = ids.index(pedido.id)
            if direccion == 'subir' and pos > 0:
                paradas[pos], paradas[pos - 1] = paradas[pos - 1], paradas[pos]
            elif direccion == 'bajar' and pos < len(paradas) - 1:
                paradas[pos], paradas[pos + 1] = paradas[pos + 1], paradas[pos]

            for idx, item in enumerate(paradas, start=1):
                item.orden_en_ruta = idx
                item.save(update_fields=['orden_en_ruta'])

    messages.success(request, f'Secuencia actualizada para el pedido #{pedido.id}.')
    return redirect('panel_admin')


@login_required(login_url='login_rol')
@require_POST
def reasignar_pedido_camion(request, pedido_id):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return redirect('dashboard')

    pedido = get_object_or_404(Pedido, id=pedido_id)
    nuevo_camion_id = request.POST.get('camion_id')

    if not nuevo_camion_id:
        messages.error(request, 'Selecciona un camión válido.')
        return redirect('panel_admin')

    camion_destino = get_object_or_404(Camion, id=nuevo_camion_id)
    camion_origen = pedido.camion_asignado

    if camion_origen and camion_origen.id == camion_destino.id:
        messages.info(request, f'El pedido #{pedido.id} ya pertenece al camión {camion_destino.patente}.')
        return redirect('panel_admin')

    with transaction.atomic():
        pedido.camion_asignado = camion_destino
        pedido.orden_en_ruta = 9999
        if pedido.estado in ['PREVENTA', 'PREPARADO']:
            pedido.estado = 'EN_RUTA'
        pedido.save(update_fields=['camion_asignado', 'orden_en_ruta', 'estado'])

        if camion_origen:
            normalizar_y_evaluar_camion(camion_origen)

        resumen = normalizar_y_evaluar_camion(camion_destino)

    if resumen and (resumen['excede_peso'] or resumen['excede_paradas']):
        messages.warning(
            request,
            f'Pedido #{pedido.id} asignado a {camion_destino.patente}. '
            f'Alerta operativa: {resumen["peso_total"]} / {int(resumen["capacidad_max"])} kg '
            f'y {resumen["total_paradas"]} / 30 paradas.'
        )
    else:
        messages.success(request, f'Pedido #{pedido.id} asignado al camión {camion_destino.patente}.')

    return redirect('panel_admin')


@login_required(login_url='login_rol')
@require_POST
def devolver_pedido_preventa(request, pedido_id):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return redirect('dashboard')

    pedido = get_object_or_404(Pedido, id=pedido_id)
    camion_origen = pedido.camion_asignado

    with transaction.atomic():
        pedido.camion_asignado = None
        pedido.orden_en_ruta = None
        pedido.estado = 'PREVENTA'
        pedido.save(update_fields=['camion_asignado', 'orden_en_ruta', 'estado'])

        if camion_origen:
            normalizar_y_evaluar_camion(camion_origen)

    messages.info(request, f'Pedido #{pedido.id} devuelto a PREVENTA.')
    return redirect('panel_admin')


# ==============================================================================
# 7. GESTIÓN DE FLOTA Y CONDUCTORES (ADMIN + AUTOASIGNACIÓN CONDUCTOR)
# ==============================================================================
@login_required(login_url='login_rol')
@require_POST
def crear_camion(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return redirect('dashboard')

    patente = request.POST.get('patente', '').strip().upper()
    capacidad_raw = request.POST.get('capacidad_max_kg', '1600').replace(',', '.')

    if not patente:
        messages.error(request, 'Debes ingresar una patente válida.')
        return redirect('panel_admin')

    if Camion.objects.filter(patente__iexact=patente).exists():
        messages.warning(request, f'El camión con patente {patente} ya está registrado.')
        return redirect('panel_admin')

    try:
        capacidad = Decimal(capacidad_raw)
        if capacidad <= 0:
            raise InvalidOperation
    except InvalidOperation:
        capacidad = Decimal('1600.00')

    Camion.objects.create(patente=patente, capacidad_max_kg=capacidad)
    messages.success(request, f'Camión {patente} ({capacidad} kg) agregado a la flota.')
    return redirect('panel_admin')


@login_required(login_url='login_rol')
@require_POST
def crear_conductor(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return redirect('dashboard')

    username = request.POST.get('username', '').strip()
    nombre_completo = request.POST.get('nombre_completo', '').strip()
    password = request.POST.get('password', '').strip() or '1234'
    camion_id = request.POST.get('camion_id')

    if not username:
        messages.error(request, 'El nombre de usuario del conductor es obligatorio.')
        return redirect('panel_admin')

    if User.objects.filter(username__iexact=username).exists():
        messages.error(request, f'El usuario "{username}" ya existe en el sistema.')
        return redirect('panel_admin')

    with transaction.atomic():
        partes = nombre_completo.split(' ', 1)
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=partes[0] if partes else username,
            last_name=partes[1] if len(partes) > 1 else '',
        )
        perfil = PerfilUsuario.objects.create(usuario=user, rol='CONDUCTOR')

        if camion_id:
            camion = get_object_or_404(Camion, id=camion_id)
            camion.conductor = perfil
            camion.save(update_fields=['conductor'])
            messages.success(request, f'Conductor "{username}" creado y asignado al camión {camion.patente}.')
        else:
            messages.success(request, f'Conductor "{username}" creado correctamente.')

    return redirect('panel_admin')


@login_required(login_url='login_rol')
@require_POST
def asignar_conductor_camion(request, camion_id):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'ADMIN':
        return redirect('dashboard')

    camion = get_object_or_404(Camion, id=camion_id)
    conductor_id = request.POST.get('conductor_id')

    with transaction.atomic():
        if not conductor_id:
            camion.conductor = None
            camion.save(update_fields=['conductor'])
            messages.info(request, f'Camión {camion.patente} liberado sin conductor asignado.')
        else:
            perfil_conductor = get_object_or_404(PerfilUsuario, id=conductor_id, rol='CONDUCTOR')
            Camion.objects.filter(conductor=perfil_conductor).exclude(id=camion.id).update(conductor=None)
            camion.conductor = perfil_conductor
            camion.save(update_fields=['conductor'])
            messages.success(
                request,
                f'Conductor {perfil_conductor.usuario.username} asignado al camión {camion.patente}.'
            )

    return redirect('panel_admin')


@login_required(login_url='login_rol')
@require_POST
def seleccionar_camion_conductor(request):
    if not hasattr(request.user, 'perfilusuario') or request.user.perfilusuario.rol != 'CONDUCTOR':
        return redirect('dashboard')

    perfil = request.user.perfilusuario
    if Camion.objects.filter(conductor=perfil).exists():
        messages.info(request, 'Ya tienes un vehículo asignado para esta jornada.')
        return redirect('panel_conductor')

    camion_id = request.POST.get('camion_id')
    if not camion_id:
        messages.error(request, 'Selecciona un camión disponible.')
        return redirect('panel_conductor')

    with transaction.atomic():
        camion = Camion.objects.select_for_update().filter(id=camion_id, conductor__isnull=True).first()
        if not camion:
            messages.error(request, 'Ese camión acaba de ser tomado por otro conductor. Elige otro disponible.')
            return redirect('panel_conductor')

        camion.conductor = perfil
        camion.save(update_fields=['conductor'])

    messages.success(request, f'Vehículo FOTON {camion.patente} asignado a tu turno.')
    return redirect('panel_conductor')