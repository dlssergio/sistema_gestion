# parametros/admin.py (VERSIÓN FINAL, LIMPIA Y CORRECTA)

from django.contrib import admin
from .models import (
    TipoComprobante, Contador, Pais, Provincia, Localidad, Moneda, Role,
    GrupoUnidadMedida, UnidadMedida, CategoriaImpositiva, Impuesto
)

@admin.register(TipoComprobante)
class TipoComprobanteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'letra', 'afecta_stock')

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