# en ventas/serializers.py (VERSIÓN FINAL CORREGIDA)

from rest_framework import serializers

# --- MODELOS DE OTRAS APPS (LOS MOVEMOS AQUÍ ARRIBA) ---
from inventario.models import Articulo
from parametros.models import TipoComprobante
# 'Cliente' es de esta misma app ('ventas'), así que se importa de .models

# --- SERIALIZERS DE OTRAS APPS ---
from inventario.serializers import ArticuloSerializer
from entidades.serializers import ClienteSerializer
from parametros.serializers import TipoComprobanteSerializer

# --- MODELOS DE ESTA APP ---
from .models import ComprobanteVenta, ComprobanteVentaItem, Cliente

# --- SERIALIZERS DE ESCRITURA (CREATE) ---

class ComprobanteVentaItemCreateSerializer(serializers.ModelSerializer):
    #articulo = serializers.PrimaryKeyRelatedField(queryset=Articulo.objects.all())
    articulo = serializers.SlugRelatedField(
        queryset=Articulo.objects.all(),
        slug_field='cod_articulo'
    )

    class Meta:
        model = ComprobanteVentaItem
        fields = ['articulo', 'cantidad', 'precio_unitario_original']


class ComprobanteVentaCreateSerializer(serializers.ModelSerializer):
    # 'Cliente' y 'TipoComprobante' también están definidos ahora
    cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all())
    tipo_comprobante = serializers.PrimaryKeyRelatedField(queryset=TipoComprobante.objects.all())

    items = ComprobanteVentaItemCreateSerializer(many=True)

    class Meta:
        model = ComprobanteVenta
        fields = [
            'cliente',
            'tipo_comprobante',
            'fecha',
            'estado',
            'punto_venta',
            'numero',
            'items',
            'observaciones'
        ]

# --- SERIALIZERS DE LECTURA (READ) ---
# (Sin cambios)

class ComprobanteVentaItemSerializer(serializers.ModelSerializer):
    articulo = ArticuloSerializer(read_only=True)
    class Meta:
        model = ComprobanteVentaItem
        fields = ['articulo', 'cantidad', 'precio_unitario_original', 'subtotal']

class ComprobanteVentaSerializer(serializers.ModelSerializer):
    cliente = ClienteSerializer(read_only=True)
    tipo_comprobante = TipoComprobanteSerializer(read_only=True)
    items = ComprobanteVentaItemSerializer(many=True, read_only=True)
    class Meta:
        model = ComprobanteVenta
        fields = ['id', 'numero_completo', 'cliente', 'fecha', 'estado', 'total', 'tipo_comprobante', 'items', 'observaciones']