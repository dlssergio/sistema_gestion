# parametros/serializers.py (VERSIÓN FINAL Y VERIFICADA)

from rest_framework import serializers
from .models import Moneda, TipoComprobante, Impuesto, CategoriaImpositiva

class MonedaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Moneda
        fields = ['id', 'nombre', 'simbolo', 'es_base', 'cotizacion']

class TipoComprobanteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoComprobante
        fields = '__all__'

# --- Serializers para la Nueva Arquitectura de Impuestos ---

class ImpuestoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Impuesto
        fields = '__all__'

class CategoriaImpositivaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaImpositiva
        fields = '__all__'