# parametros/serializers.py (VERSIÓN FINAL Y VERIFICADA)

from rest_framework import serializers
from .models import (
    TipoComprobante,
    Moneda,
    Impuesto,
    CategoriaImpositiva,
    ConfiguracionEmpresa,
    CargaMasiva,
    ReglaConversionComprobante
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


class CargaMasivaSerializer(serializers.ModelSerializer):
    porcentaje_progreso = serializers.SerializerMethodField()
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)

    class Meta:
        model = CargaMasiva
        fields = '__all__'
        read_only_fields = (
            'estado', 'total_filas', 'filas_procesadas',
            'filas_exitosas', 'filas_error', 'detalle_errores',
            'usuario', 'creado_en', 'actualizado_en'
        )

    def get_porcentaje_progreso(self, obj):
        if obj.total_filas == 0:
            return 0
        return int((obj.filas_procesadas / obj.total_filas) * 100)


class ReglaConversionSerializer(serializers.ModelSerializer):
    tipo_origen_nombre  = serializers.CharField(source='tipo_origen.nombre',  read_only=True)
    tipo_destino_nombre = serializers.CharField(source='tipo_destino.nombre', read_only=True)

    class Meta:
        model  = ReglaConversionComprobante
        fields = [
            'id', 'tipo_origen', 'tipo_origen_nombre',
            'tipo_destino', 'tipo_destino_nombre',
            'etiqueta', 'copia_items', 'copia_cliente',
            'copia_condicion_venta', 'activo', 'orden',
            'confirmar_automaticamente',
        ]