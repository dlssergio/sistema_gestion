# en compras/serializers.py (Refactorizado para django-money)

from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField  # <<< CAMBIO: Importamos el MoneyField para serializers

# --- Modelos ---
from .models import ComprobanteCompra, ComprobanteCompraItem, Proveedor
from inventario.models import Articulo
from parametros.models import TipoComprobante

# --- Serializers de otras apps ---
from inventario.serializers import ArticuloSerializer
from entidades.serializers import ProveedorSerializer
from parametros.serializers import TipoComprobanteSerializer


# --- SERIALIZERS DE ESCRITURA (CREATE) AJUSTADOS ---

class ComprobanteCompraItemCreateSerializer(serializers.ModelSerializer):
    articulo = serializers.PrimaryKeyRelatedField(queryset=Articulo.objects.all())

    # <<< CAMBIO: El campo 'precio_costo_unitario' ya es un MoneyField y DRF sabe cómo manejarlo >>>
    # Al crear desde la API, puedes enviar: "precio_costo_unitario": "150.00", "precio_costo_unitario_currency": "ARS"

    class Meta:
        model = ComprobanteCompraItem
        # <<< CAMBIO: Se actualiza al nuevo nombre de campo 'precio_costo_unitario' >>>
        fields = ['articulo', 'cantidad', 'precio_costo_unitario']


class ComprobanteCompraCreateSerializer(serializers.ModelSerializer):
    proveedor = serializers.PrimaryKeyRelatedField(queryset=Proveedor.objects.all())
    tipo_comprobante = serializers.PrimaryKeyRelatedField(queryset=TipoComprobante.objects.all())
    items = ComprobanteCompraItemCreateSerializer(many=True)

    class Meta:
        model = ComprobanteCompra
        fields = [
            'proveedor',
            'tipo_comprobante',
            'fecha',
            'estado',
            'punto_venta',
            'numero',
            'items'
        ]


# --- SERIALIZERS DE LECTURA (READ) AJUSTADOS ---

class ComprobanteCompraItemSerializer(serializers.ModelSerializer):
    articulo = ArticuloSerializer(read_only=True)
    # <<< CAMBIO: Se declaran los MoneyFields para la lectura >>>
    precio_costo_unitario = MoneyField(max_digits=12, decimal_places=2, read_only=True)
    subtotal = MoneyField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ComprobanteCompraItem
        # <<< CAMBIO: Se actualizan los nombres de los campos >>>
        fields = ['articulo', 'cantidad', 'precio_costo_unitario', 'subtotal']


class ComprobanteCompraSerializer(serializers.ModelSerializer):
    proveedor = ProveedorSerializer(read_only=True)
    tipo_comprobante = TipoComprobanteSerializer(read_only=True)
    items = ComprobanteCompraItemSerializer(many=True, read_only=True)

    # <<< CAMBIO: Se declara el MoneyField para la lectura >>>
    total = MoneyField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ComprobanteCompra
        fields = ['id', 'numero_completo', 'proveedor', 'fecha', 'estado', 'total', 'tipo_comprobante', 'items']