from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('admin-logistica/', views.panel_admin, name='panel_admin'),
    path('conductor/', views.panel_conductor, name='panel_conductor'),
    path('cliente/', views.panel_cliente, name='panel_cliente'),
]