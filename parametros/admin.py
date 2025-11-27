# parametros/admin.py

from django.contrib import admin
from .models import (
    TipoComprobante, Contador, Moneda, Pais, Provincia, Localidad,
    CategoriaImpositiva, Impuesto, Role, GrupoUnidadMedida, UnidadMedida,
    SerieDocumento
)


@admin.register(TipoComprobante)
class TipoComprobanteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'letra', 'codigo_afip', 'afecta_stock')
    search_fields = ['nombre', 'codigo_afip']

@admin.register(Contador)
class ContadorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'prefijo', 'ultimo_valor')
    list_editable = ('ultimo_valor',)

@admin.register(Moneda)
class MonedaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'simbolo', 'cotizacion', 'es_base')
    list_editable = ('cotizacion',)
    search_fields = ('nombre', 'simbolo')

@admin.register(Pais)
class PaisAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'por_defecto')
    search_fields = ('nombre', 'codigo')

@admin.register(Provincia)
class ProvinciaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'pais')
    search_fields = ('nombre', 'codigo')
    list_filter = ('pais',)
    autocomplete_fields = ['pais']

@admin.register(Localidad)
class LocalidadAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo_postal', 'provincia')
    search_fields = ('nombre', 'codigo_postal')
    list_filter = ('provincia__pais', 'provincia')
    autocomplete_fields = ['provincia']

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name',)
    filter_horizontal = ('permissions', 'users',)

@admin.register(GrupoUnidadMedida)
class GrupoUnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'simbolo', 'grupo')
    list_filter = ('grupo',)
    search_fields = ('nombre', 'simbolo')
    autocomplete_fields = ['grupo']

# --- Clases de Admin para la Nueva Arquitectura de Impuestos ---

@admin.register(Impuesto)
class ImpuestoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tasa', 'aplica_a', 'es_porcentaje', 'vigente_desde', 'vigente_hasta')
    list_filter = ('aplica_a', 'es_porcentaje')
    search_fields = ('nombre',)

@admin.register(CategoriaImpositiva)
class CategoriaImpositivaAdmin(admin.ModelAdmin):
    search_fields = ('nombre',)


@admin.register(SerieDocumento)
class SerieDocumentoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo_comprobante', 'punto_venta', 'ultimo_numero', 'es_manual', 'activo')
    list_filter = ('tipo_comprobante', 'es_manual', 'activo')
    search_fields = ('nombre', 'punto_venta')
    autocomplete_fields = ['tipo_comprobante', 'deposito_defecto']

    fieldsets = (
        ('Configuración Principal', {
            'fields': ('nombre', 'tipo_comprobante', 'punto_venta', 'activo')
        }),
        ('Numeración', {
            'fields': ('ultimo_numero', 'es_manual'),
            'description': 'El sistema sumará 1 al último número automáticamente al emitir, a menos que sea manual.'
        }),
        ('Automatización', {
            'fields': ('deposito_defecto',)
        }),
    )