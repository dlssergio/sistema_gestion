# parametros/serializers.py (VERSIÓN FINAL Y VERIFICADA)

from rest_framework import serializers
from .models import (
    TipoComprobante,
    Moneda,
    Impuesto,
    CategoriaImpositiva,
    ConfiguracionEmpresa
)
from entidades.serializers import EntidadSerializer


class MonedaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Moneda
        fields = '__all__'
        #fields = ['id', 'nombre', 'simbolo', 'es_base', 'cotizacion']

class TipoComprobanteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoComprobante
        fields = [
            'id',
            'nombre',
            'codigo_afip',
            'letra',
            'clase',                # 'V'entas, 'C'ompras
            'mueve_stock',
            'signo_stock',          # 1, -1, 0
            'mueve_cta_cte',
            'mueve_caja',
            'es_fiscal',
            'numeracion_automatica'
        ]

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