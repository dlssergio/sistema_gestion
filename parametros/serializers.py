# parametros/serializers.py (VERSIÓN FINAL Y VERIFICADA)

from rest_framework import serializers
from .models import Moneda, TipoComprobante, Impuesto, CategoriaImpositiva, ConfiguracionEmpresa
from entidades.serializers import EntidadSerializer


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


class ConfiguracionEmpresaSerializer(serializers.ModelSerializer):
    # Anidamos la entidad para tener el CUIT y dirección disponibles directamente
    entidad_data = EntidadSerializer(source='entidad', read_only=True)

    class Meta:
        model = ConfiguracionEmpresa
        fields = [
            'id', 'nombre_fantasia', 'logo',
            'inicio_actividades', 'ingresos_brutos',
            'moneda_principal', 'entidad', 'entidad_data'
        ]