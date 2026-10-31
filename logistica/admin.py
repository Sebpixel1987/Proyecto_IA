from django.contrib import admin
from .models import PerfilUsuario, Ubicacion, Cliente, Producto, Camion, Pedido, DetallePedido

class DetallePedidoInline(admin.TabularInline):
    model = DetallePedido
    extra = 1

class PedidoAdmin(admin.ModelAdmin):
    inlines = [DetallePedidoInline]
    list_display = ('id', 'cliente', 'estado', 'camion_asignado', 'fecha_entrega_esperada')
    list_filter = ('estado', 'camion_asignado', 'fecha_entrega_esperada')

admin.site.register(PerfilUsuario)
admin.site.register(Ubicacion)
admin.site.register(Cliente)
admin.site.register(Producto)
admin.site.register(Camion)
admin.site.register(Pedido, PedidoAdmin)