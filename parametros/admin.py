from django.contrib import admin
from .models import TipoComprobante, Contador, Pais, Provincia, Localidad, Moneda, ReglaImpuesto
from .models import Role

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

@admin.register(ReglaImpuesto)
class ReglaImpuestoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tasa', 'aplica_a', 'activo', 'valido_desde', 'valido_hasta')
    list_filter = ('aplica_a', 'activo')
    search_fields = ('nombre',)
    filter_horizontal = ('categorias_producto',)
    fieldsets = (
        (None, {
            'fields': ('nombre', 'tasa', 'tipo_impuesto', 'aplica_a', 'activo')
        }),
        ('Condiciones de Aplicación', {
            'fields': ('categorias_producto',)
        }),
        ('Vigencia', {
            'fields': ('valido_desde', 'valido_hasta')
        }),
    )