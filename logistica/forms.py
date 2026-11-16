from django import forms
from django.contrib.auth.models import User
from .models import Ubicacion, Pedido, Producto, Cliente, PerfilUsuario

COMUNAS_GRAN_CONCEPCION = [
    ('Concepción', 'Concepción'),
    ('Talcahuano', 'Talcahuano'),
    ('Hualpén', 'Hualpén'),
    ('San Pedro de la Paz', 'San Pedro de la Paz'),
    ('Coronel', 'Coronel'),
    ('Chiguayante', 'Chiguayante'),
    ('Penco', 'Penco'),
    ('Lota', 'Lota'),
]


class UbicacionForm(forms.ModelForm):
    comuna = forms.ChoiceField(
        choices=COMUNAS_GRAN_CONCEPCION,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Ubicacion
        fields = ['direccion', 'comuna', 'latitud', 'longitud']
        widgets = {
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Av. O’Higgins 1250'}),
            'latitud': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'id': 'id_latitud'}),
            'longitud': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'id': 'id_longitud'}),
        }


class PedidoExternoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ['cliente', 'fecha_entrega_esperada', 'observaciones', 'estado']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'form-select'}),
            'fecha_entrega_esperada': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
        }


class RegistroClienteForm(forms.Form):
    nombre_completo = forms.CharField(
        max_length=150,
        label="Nombre o Razón Social del Local",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Minimarket Los Aromos'})
    )
    username = forms.CharField(
        max_length=100,
        label="Usuario de acceso",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: minimarket_aromos'})
    )
    email = forms.EmailField(
        required=False,
        label="Correo electrónico (opcional)",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'contacto@local.cl'})
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    telefono = forms.CharField(
        max_length=15,
        label="Teléfono de contacto",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+56 9 1234 5678'})
    )
    direccion = forms.CharField(
        max_length=255,
        label="Dirección exacta de entrega",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Calle y número'})
    )
    comuna = forms.ChoiceField(
        choices=COMUNAS_GRAN_CONCEPCION,
        label="Comuna",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    latitud = forms.DecimalField(
        max_digits=10,
        decimal_places=7,
        label="Latitud (haz clic en el mapa)",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'id': 'id_latitud'})
    )
    longitud = forms.DecimalField(
        max_digits=10,
        decimal_places=7,
        label="Longitud (haz clic en el mapa)",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'id': 'id_longitud'})
    )
    ventana_horaria_inicio = forms.TimeField(
        required=False,
        label="Horario recepción desde",
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'})
    )
    ventana_horaria_fin = forms.TimeField(
        required=False,
        label="Horario recepción hasta",
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'})
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Este nombre de usuario ya está registrado.")
        return username


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ['nombre', 'peso_kg', 'cantidad_disponible']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Queso Gauda Laminado 5kg'}),
            'peso_kg': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '5.00'}),
            'cantidad_disponible': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }