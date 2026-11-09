import random
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from logistica.models import PerfilUsuario, Ubicacion, Cliente, Producto, Camion, Pedido, DetallePedido
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Puebla la base de datos de Emporio Alemán con datos de prueba para optimización de rutas'

    def handle(self, *args, **kwargs):
        self.stdout.write("Limpiando base de datos...")
        DetallePedido.objects.all().delete()
        Pedido.objects.all().delete()
        Camion.objects.all().delete()
        Producto.objects.all().delete()
        Cliente.objects.all().delete()
        Ubicacion.objects.all().delete()
        # Limpiar usuarios generados en pruebas anteriores para evitar errores de duplicidad
        User.objects.filter(perfilusuario__rol='CLIENTE').delete()
        
        # 1. Crear Flota de Camiones (2 propios, 3 arrendados, 1.600 kg)
        self.stdout.write("Creando flota de camiones...")
        flota = ['FOTON-01', 'FOTON-02', 'EXT-01', 'EXT-02', 'EXT-03']
        for patente in flota:
            Camion.objects.create(patente=patente, capacidad_max_kg=1600.00)

        # 2. Crear Productos (Basado en lista de picking)
        self.stdout.write("Creando catálogo de productos...")
        productos_data = [
            {'nombre': '9807 - CAJA QUESO MANTECOSO', 'peso_kg': 15.0, 'cantidad_disponible': 100},
            {'nombre': '5148 - CAJA CHORIZO PARRILLERO AHUMADO', 'peso_kg': 12.5, 'cantidad_disponible': 100},
            {'nombre': '5158 - CAJA LONGANIZA AHUMADA SACHET', 'peso_kg': 10.0, 'cantidad_disponible': 100},
            {'nombre': '5074 - CAJA JAMON SANDWICH LAMINADO', 'peso_kg': 8.0, 'cantidad_disponible': 100},
            {'nombre': '5107 - CAJA VIENESAS AL VACIO 20 UN', 'peso_kg': 5.0, 'cantidad_disponible': 100},
        ]
        productos_db = []
        for p in productos_data:
            productos_db.append(Producto.objects.create(**p))

        # 3. Crear Ubicaciones y Clientes Reales (Gran Concepción - Coronel)
        self.stdout.write("Generando clientes en ubicaciones reales...")
        
        # Puntos reales estratégicos para Emporio Alemán
        coordenadas_reales = [
            (-37.0256, -73.1365, "Coronel", "Plaza de Armas Coronel"),
            (-36.9939, -73.1384, "Coronel", "Lagunillas Sector 3"),
            (-37.0090, -73.1460, "Coronel", "Camilo Olavarría"),
            (-36.8837, -73.1251, "San Pedro de la Paz", "Lomas Coloradas"),
            (-36.8385, -73.1118, "San Pedro de la Paz", "Andalué"),
            (-36.8521, -73.1095, "San Pedro de la Paz", "Michaihue"),
            (-36.8270, -73.0503, "Concepción", "Plaza Independencia"),
            (-36.8296, -73.0375, "Concepción", "Barrio Universitario UdeC"),
            (-36.8190, -73.0118, "Concepción", "Collao, Terminal Collao"),
            (-36.7845, -73.0901, "Hualpén", "Club Hípico / Colón"),
            (-36.7932, -73.0645, "Hualpén", "Lomas de San Andrés"),
            (-36.7167, -73.1167, "Talcahuano", "Centro Talcahuano"),
            (-36.7450, -73.1020, "Talcahuano", "Las Higueras"),
            (-36.7698, -73.0645, "Talcahuano", "Brisas del Sol"),
            (-36.8040, -73.0390, "Concepción", "Barrio Norte")
        ]
        
        clientes_db = []
        for i in range(35): # 35 clientes obligan a usar más de 1 camión
            lat, lon, comuna, direccion = coordenadas_reales[i % len(coordenadas_reales)]
            # Ligera variación decimal para evitar empalmes si se repite la ubicación
            lat += random.uniform(-0.002, 0.002) 
            lon += random.uniform(-0.002, 0.002)
            
            ubicacion = Ubicacion.objects.create(
                direccion=direccion, 
                comuna=comuna, 
                latitud=round(lat, 6), 
                longitud=round(lon, 6)
            )
            
            user = User.objects.create_user(username=f"cliente_real_{i}", password="password123")
            perfil = PerfilUsuario.objects.create(usuario=user, rol='CLIENTE')
            
            cliente = Cliente.objects.create(
                perfil=perfil,
                ubicacion_principal=ubicacion,
                telefono=f"+569{random.randint(10000000, 99999999)}",
                ventana_horaria_inicio="09:00:00",
                ventana_horaria_fin="18:00:00"
            )
            clientes_db.append(cliente)

        # 4. Generar Pedidos Masivos
        self.stdout.write("Simulando pedidos para estresar el motor de ruteo...")
        fecha_entrega = timezone.now().date() + timedelta(days=1)
        
        for cliente in clientes_db:
            pedido = Pedido.objects.create(
                cliente=cliente, 
                ubicacion_entrega=cliente.ubicacion_principal,
                estado='PREVENTA',
                fecha_entrega_esperada=fecha_entrega
            )
            
            # Asignar cajas para forzar el volumen de carga y emular la densidad operativa
            num_lineas = random.randint(1, 4)
            for _ in range(num_lineas):
                producto = random.choice(productos_db)
                cantidad = random.randint(1, 5)
                DetallePedido.objects.create(pedido=pedido, producto=producto, cantidad=cantidad)

        self.stdout.write(self.style.SUCCESS("¡Base de datos poblada exitosamente! Se inyectaron 40 pedidos y 5 camiones."))