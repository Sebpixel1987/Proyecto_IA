from django import forms
from .models import Pedido, Ubicacion

class UbicacionForm(forms.ModelForm):
    class Meta:
        model = Ubicacion
        fields = ['direccion', 'comuna', 'latitud', 'longitud']
        widgets = {
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Av. Colón 9500'}),
            'comuna': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Talcahuano / Concepción'}),
            'latitud': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0000001', 'placeholder': '-36.7234'}),
            'longitud': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0000001', 'placeholder': '-73.1154'}),
        }

class PedidoExternoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ['cliente', 'ubicacion_entrega', 'fecha_entrega_esperada', 'estado']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'form-select'}),
            'ubicacion_entrega': forms.Select(attrs={'class': 'form-select'}),
            'fecha_entrega_esperada': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
        }