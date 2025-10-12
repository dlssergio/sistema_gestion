# en inventario/admin.py (VERSIÓN FINAL CON LÓGICA DE MONEDA CORREGIDA Y ROBUSTA)
import json
from decimal import Decimal
from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Articulo, Marca, Rubro, Deposito, StockArticulo
from parametros.models import Moneda, Impuesto
from djmoney.forms.widgets import MoneyWidget


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


# FORMULARIO PERSONALIZADO PARA EL ADMIN DE ARTÍCULO
class ArticuloAdminForm(forms.ModelForm):
    class Meta:
        model = Articulo
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        moneda_queryset = Moneda.objects.all()

        # <<< LÓGICA CORRECTA: El valor de cada opción es el ID único de la moneda >>>
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in moneda_queryset]

        costo_widget = self.fields['precio_costo'].widget
        venta_widget = self.fields['precio_venta'].widget

        if isinstance(costo_widget, MoneyWidget) and hasattr(costo_widget, 'widgets'):
            costo_widget.widgets[1].choices = choices
        if isinstance(venta_widget, MoneyWidget) and hasattr(venta_widget, 'widgets'):
            venta_widget.widgets[1].choices = choices


@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    form = ArticuloAdminForm

    list_display = (
        'cod_articulo', 'descripcion', 'perfil', 'marca', 'stock_total_display', 'precio_venta', 'esta_activo')

    fieldsets = (
        (None, {'fields': ('json_data_injector',)}),
        ('Información Principal',
         {'fields': ('cod_articulo', 'descripcion', 'perfil', 'ean', 'qr_code', 'marca', 'rubro', 'esta_activo')}),
        ('Descripciones Detalladas', {'classes': ('collapse',), 'fields': ('observaciones', 'nota')}),
        ('Precios y Costos', {'fields': (
            'precio_costo',
            'utilidad',
            'precio_venta',
            'impuesto',
            'precio_final_form'
        )}),
        ('Configuración de Stock',
         {'fields': ('administra_stock', 'unidad_medida', 'stock_minimo', 'stock_maximo', 'punto_pedido')}),
    )

    inlines = [StockArticuloInline]
    list_filter = ('esta_activo', 'marca', 'rubro', 'perfil')
    search_fields = ('descripcion', 'cod_articulo', 'ean')
    autocomplete_fields = ['marca']
    readonly_fields = ('json_data_injector', 'precio_final_form')

    class Media:
        css = {'all': ('admin/css/tabs.css',)}
        js = ('admin/js/articulo_tabs.js', 'admin/js/articulo_admin.js',)

    def stock_total_display(self, obj):
        return obj.stock_total

    stock_total_display.short_description = "Stock Total"

    def precio_final_form(self, obj):
        precio = obj.precio_final_calculado
        return precio if precio else "-"

    precio_final_form.short_description = "Precio Final (con IVA)"

    def json_data_injector(self, obj):
        monedas = Moneda.objects.all()
        # <<< LÓGICA CORRECTA: El diccionario de cotizaciones usa el ID como clave >>>
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