from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField

# --- Modelos ---
from .models import ComprobanteCompra, ComprobanteCompraItem, Proveedor
from inventario.models import Articulo
from parametros.models import TipoComprobante

# --- Serializers de otras apps ---
from inventario.serializers import ArticuloSerializer
from entidades.serializers import ProveedorSerializer
from parametros.serializers import TipoComprobanteSerializer


# --- SERIALIZERS DE ESCRITURA (CREATE) ---

class ComprobanteCompraItemCreateSerializer(serializers.ModelSerializer):
    articulo = serializers.PrimaryKeyRelatedField(queryset=Articulo.objects.all())

    class Meta:
        model = ComprobanteCompraItem
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


# --- SERIALIZERS DE LECTURA (READ) ---

class ComprobanteCompraItemSerializer(serializers.ModelSerializer):
    articulo = ArticuloSerializer(read_only=True)
    precio_costo_unitario = MoneyField(max_digits=12, decimal_places=2, read_only=True)
    subtotal = MoneyField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ComprobanteCompraItem
        fields = ['articulo', 'cantidad', 'precio_costo_unitario', 'subtotal']


class ComprobanteCompraSerializer(serializers.ModelSerializer):
    proveedor = ProveedorSerializer(read_only=True)
    tipo_comprobante = TipoComprobanteSerializer(read_only=True)
    items = ComprobanteCompraItemSerializer(many=True, read_only=True)
    total = MoneyField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ComprobanteCompra
        fields = ['id', 'numero_completo', 'proveedor', 'fecha', 'estado', 'total', 'tipo_comprobante', 'items']