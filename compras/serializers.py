# en compras/serializers.py (NUEVO ARCHIVO)

from rest_framework import serializers

# --- Modelos que necesitaremos ---
from .models import ComprobanteCompra, ComprobanteCompraItem, Proveedor
from inventario.models import Articulo
from parametros.models import TipoComprobante

# --- Serializers de otras apps que reutilizaremos ---
from inventario.serializers import ArticuloSerializer
from entidades.serializers import ProveedorSerializer # Reutilizamos el de lectura
from parametros.serializers import TipoComprobanteSerializer

# --- SERIALIZERS DE ESCRITURA (CREATE) ---

class ComprobanteCompraItemCreateSerializer(serializers.ModelSerializer):
    articulo = serializers.PrimaryKeyRelatedField(queryset=Articulo.objects.all())

    class Meta:
        model = ComprobanteCompraItem
        fields = ['articulo', 'cantidad', 'precio_costo_unitario_original', 'moneda_costo']


class ComprobanteCompraCreateSerializer(serializers.ModelSerializer):
    proveedor = serializers.PrimaryKeyRelatedField(queryset=Proveedor.objects.all())
    tipo_comprobante = serializers.PrimaryKeyRelatedField(queryset=TipoComprobante.objects.all())
    items = ComprobanteCompraItemCreateSerializer(many=True)

    class Meta:
        model = ComprobanteCompra
        # Definimos los campos que el frontend enviará
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
    class Meta:
        model = ComprobanteCompraItem
        fields = ['articulo', 'cantidad', 'precio_costo_unitario_original', 'moneda_costo', 'subtotal']

class ComprobanteCompraSerializer(serializers.ModelSerializer):
    proveedor = ProveedorSerializer(read_only=True)
    tipo_comprobante = TipoComprobanteSerializer(read_only=True)
    items = ComprobanteCompraItemSerializer(many=True, read_only=True)
    class Meta:
        model = ComprobanteCompra
        fields = ['id', 'numero_completo', 'proveedor', 'fecha', 'estado', 'total', 'tipo_comprobante', 'items']