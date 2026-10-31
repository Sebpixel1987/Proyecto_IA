from django.db import models
from django.contrib.auth.models import User

class PerfilUsuario(models.Model):
    ROLES = (
        ('ADMIN', 'Logística (Admin)'),
        ('CONDUCTOR', 'Conductor'),
        ('CLIENTE', 'Cliente'),
    )
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    rol = models.CharField(max_length=15, choices=ROLES)

    def __str__(self):
        return f"{self.usuario.username} - {self.rol}"

class Ubicacion(models.Model):
    direccion = models.CharField(max_length=255, help_text="Dirección estandarizada")
    comuna = models.CharField(max_length=100)
    latitud = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitud = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    def __str__(self):
        return f"{self.direccion}, {self.comuna}"

class Cliente(models.Model):
    perfil = models.OneToOneField(PerfilUsuario, on_delete=models.CASCADE, limit_choices_to={'rol': 'CLIENTE'})
    ubicacion_principal = models.ForeignKey(Ubicacion, on_delete=models.SET_NULL, null=True)
    telefono = models.CharField(max_length=15)
    ventana_horaria_inicio = models.TimeField(null=True, blank=True, help_text="Ej: 09:00:00")
    ventana_horaria_fin = models.TimeField(null=True, blank=True, help_text="Ej: 14:00:00")

    def __str__(self):
        return self.perfil.usuario.username

class Producto(models.Model):
    nombre = models.CharField(max_length=150)
    peso_kg = models.DecimalField(max_digits=6, decimal_places=2)
    cantidad_disponible = models.IntegerField(default=0)
    
    def __str__(self):
        return f"{self.nombre} ({self.peso_kg} kg)"

class Camion(models.Model):
    conductor = models.ForeignKey(PerfilUsuario, on_delete=models.SET_NULL, null=True, limit_choices_to={'rol': 'CONDUCTOR'})
    patente = models.CharField(max_length=10)
    capacidad_max_kg = models.DecimalField(max_digits=6, decimal_places=2, default=1600.00)

    def __str__(self):
        return f"Camión {self.patente} - Conductor: {self.conductor.usuario.username if self.conductor else 'Sin Asignar'}"

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
    camion_asignado = models.ForeignKey(Camion, on_delete=models.SET_NULL, null=True, blank=True)
    orden_en_ruta = models.IntegerField(null=True, blank=True, help_text="Posición calculada por el algoritmo de última milla")

    def __str__(self):
        return f"Pedido #{self.id} - {self.cliente} ({self.estado})"

class DetallePedido(models.Model):
    pedido = models.ForeignKey(Pedido, related_name='detalles', on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField()

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre} (Ped. #{self.pedido.id})"