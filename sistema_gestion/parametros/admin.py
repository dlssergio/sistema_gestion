# en parametros/admin.py (Versión Corregida)
from django.contrib import admin
from .models import TipoComprobante, Contador, Pais, Provincia, Localidad, Moneda, Impuesto
from .models import Role

# Solo hay UNA definición para TipoComprobanteAdmin
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

admin.site.register(Impuesto)

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
