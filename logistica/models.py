from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class PerfilUsuario(models.Model):
    ROLES = (
        ('ADMIN', 'Logística (Admin)'),
        ('CONDUCTOR', 'Conductor'),
        ('CLIENTE', 'Cliente'),
    )
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    rol = models.CharField(max_length=15, choices=ROLES)

    def __str__(self):
        return f"{self.usuario.username} ({self.rol})"


class Ubicacion(models.Model):
    direccion = models.CharField(max_length=255, help_text="Dirección estandarizada")
    comuna = models.CharField(max_length=100)
    latitud = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitud = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    def __str__(self):
        return f"{self.direccion}, {self.comuna}"


class Cliente(models.Model):
    perfil = models.OneToOneField(
        PerfilUsuario,
        on_delete=models.CASCADE,
        limit_choices_to={'rol': 'CLIENTE'}
    )
    ubicacion_principal = models.ForeignKey(Ubicacion, on_delete=models.SET_NULL, null=True)
    telefono = models.CharField(max_length=15)
    ventana_horaria_inicio = models.TimeField(null=True, blank=True, help_text="Ej: 09:00:00")
    ventana_horaria_fin = models.TimeField(null=True, blank=True, help_text="Ej: 14:00:00")

    def __str__(self):
        nombre = self.perfil.usuario.get_full_name() or self.perfil.usuario.username
        return nombre


class Producto(models.Model):
    nombre = models.CharField(max_length=150)
    peso_kg = models.DecimalField(max_digits=6, decimal_places=2)
    cantidad_disponible = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.nombre} ({self.peso_kg} kg)"


class Camion(models.Model):
    conductor = models.ForeignKey(
        PerfilUsuario,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={'rol': 'CONDUCTOR'}
    )
    patente = models.CharField(max_length=10)
    capacidad_max_kg = models.DecimalField(max_digits=6, decimal_places=2, default=1600.00)

    def __str__(self):
        conductor_nombre = self.conductor.usuario.username if self.conductor else 'Sin Asignar'
        return f"Camión {self.patente} - Conductor: {conductor_nombre}"


class Pedido(models.Model):
    ESTADOS = (
        ('PREVENTA', 'Preventa (Ingresado)'),
        ('PREPARADO', 'Preparado (Picking)'),
        ('EN_RUTA', 'En Ruta'),
        ('ENTREGADO', 'Entregado'),
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    ubicacion_entrega = models.ForeignKey(Ubicacion, on_delete=models.PROTECT)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PREVENTA')
    fecha_entrega_esperada = models.DateField()
    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name="Requisitos o Restricciones de Entrega",
        help_text="Ej: Llamar al llegar, descargar por portón lateral, recibir antes de las 13:00 hrs."
    )
    camion_asignado = models.ForeignKey(Camion, on_delete=models.SET_NULL, null=True, blank=True)
    orden_en_ruta = models.IntegerField(
        null=True,
        blank=True,
        help_text="Posición calculada por el algoritmo de última milla"
    )

    @property
    def peso_total_kg(self):
        return sum(d.producto.peso_kg * d.cantidad for d in self.detalles.all())

    def __str__(self):
        return f"Pedido #{self.id} - {self.cliente} ({self.estado})"


class DetallePedido(models.Model):
    pedido = models.ForeignKey(Pedido, related_name='detalles', on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField()

    @property
    def subtotal_kg(self):
        return self.producto.peso_kg * self.cantidad

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre} (Ped. #{self.pedido.id})"


class RutaHistorica(models.Model):
    camion = models.ForeignKey(
        Camion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Camión Asignado"
    )
    fecha_ejecucion = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Ejecución")
    distancia_total_km = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Distancia Total (km)")
    tiempo_estimado_min = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Tiempo Estimado (min)")
    pedidos_incluidos = models.ManyToManyField(Pedido, blank=True, verbose_name="Pedidos en la Ruta")
    geometria_osrm = models.JSONField(null=True, blank=True, verbose_name="Trazado OSRM (GeoJSON)")

    def __str__(self):
        patente = self.camion.patente if self.camion else "Sin Camión"
        return f"Ruta #{self.id} - Camión {patente} ({self.fecha_ejecucion.strftime('%d/%m/%Y %H:%M')})"