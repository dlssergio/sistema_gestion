# en inventario/admin.py (VERSIÓN FINAL CON INDENTACIÓN LIMPIA)
import json
from decimal import Decimal
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Articulo, Marca, Rubro, Deposito, StockArticulo
from parametros.models import Moneda, Impuesto


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal): return float(obj)
        return super(DecimalEncoder, self).default(obj)


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    search_fields = ['nombre']


admin.site.register(Rubro)
admin.site.register(Deposito)


class StockArticuloInline(admin.TabularInline):
    model = StockArticulo
    extra = 1


@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    list_display = (
    'cod_articulo', 'descripcion', 'perfil', 'marca', 'stock_total_display', 'precio_venta_base', 'esta_activo')

    fieldsets = (
        (None, {'fields': ('json_data_injector',)}),
        ('Información Principal',
         {'fields': ('cod_articulo', 'descripcion', 'perfil', 'ean', 'qr_code', 'marca', 'rubro', 'esta_activo')}),
        ('Descripciones Detalladas', {'classes': ('collapse',), 'fields': ('observaciones', 'nota')}),
        ('Precios y Costos', {'fields': (
        ('moneda_costo', 'precio_costo_original'), 'utilidad', ('moneda_venta', 'precio_venta_original'), 'impuesto',
        'precio_costo_base', 'precio_venta_base', 'precio_final_form')}),
        ('Configuración de Stock',
         {'fields': ('administra_stock', 'unidad_medida', 'stock_minimo', 'stock_maximo', 'punto_pedido')}),
    )

    inlines = [StockArticuloInline]

    list_filter = ('esta_activo', 'marca', 'rubro', 'perfil')
    search_fields = ('descripcion', 'cod_articulo', 'ean')
    autocomplete_fields = ['marca']
    readonly_fields = ('json_data_injector', 'precio_costo_base', 'precio_venta_base', 'precio_final_form')

    class Media:
        css = {'all': ('admin/css/tabs.css',)}
        js = ('admin/js/articulo_tabs.js', 'admin/js/articulo_admin.js',)

    def stock_total_display(self, obj):
        return obj.stock_total

    stock_total_display.short_description = "Stock Total"

    def precio_final_display(self, obj): return f"${obj.precio_final_calculado:,.2f}"

    precio_final_display.short_description = "Precio Final (Lista)"

    def precio_final_form(self, obj): return f"${obj.precio_final_calculado:,.2f}"

    precio_final_form.short_description = "Precio Final (con IVA)"

    def json_data_injector(self, obj):
        monedas = Moneda.objects.all()
        cotizaciones = {str(m.id): m.cotizacion for m in monedas}
        impuestos = Impuesto.objects.all()
        tasas_impuestos = {str(i.id): i.tasa for i in impuestos}
        cotizaciones_json = mark_safe(json.dumps(cotizaciones, cls=DecimalEncoder))
        tasas_impuestos_json = mark_safe(json.dumps(tasas_impuestos, cls=DecimalEncoder))
        return format_html(
            '<script id="cotizaciones-json" type="application/json">{}</script><script id="tasas-impuestos-json" type="application/json">{}</script>',
            cotizaciones_json, tasas_impuestos_json
        )

    json_data_injector.short_description = ""