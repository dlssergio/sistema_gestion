# en parametros/serializers.py

from rest_framework import serializers
from .models import Moneda, TipoComprobante, Impuesto

class MonedaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Moneda
        # Exponemos los campos más útiles para la UI
        fields = ['id', 'nombre', 'simbolo', 'es_base', 'cotizacion']

class TipoComprobanteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoComprobante
        # Exponemos todos los campos del modelo
        fields = '__all__'

class ImpuestoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Impuesto
        fields = '__all__'