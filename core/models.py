from django.db import models

class Cliente(models.Model):
    nombre = models.CharField(max_length=150, verbose_name="Nombre del Cliente")
    direccion = models.CharField(max_length=255, verbose_name="Dirección de Entrega")
    longitud = models.FloatField(null=True, blank=True, verbose_name="Longitud")

    def __str__(self):
        return self.nombre

class Pedido(models.Model):
    ESTADOS = [
        ('Pendiente', 'Pendiente'),
        ('En Ruta', 'En Ruta'),
        ('Entregado', 'Entregado'),
    ]
    
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    descripcion = models.TextField(verbose_name="Detalle del Pedido")
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendiente')
    fecha_ingreso = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pedido #{self.id} - {self.cliente.nombre} ({self.estado})"