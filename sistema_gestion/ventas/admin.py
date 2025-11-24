# ventas/admin.py (VERSIÓN FINAL CON IMPORTACIÓN CORREGIDA)

from auditlog.registry import auditlog
from django.contrib import admin
from django.urls import reverse, path
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from decimal import Decimal

from .models import Cliente, ComprobanteVenta, ComprobanteVentaItem, PriceList, ProductPrice

# --- INICIO DE LA CORRECCIÓN ---
# Añadimos la nueva vista 'get_precio_articulo_cliente' a la importación.
from .views import get_precio_articulo, calcular_totales_api, get_precio_articulo_cliente
# --- FIN DE LA CORRECCIÓN ---

from .services import TaxCalculatorService

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('get_razon_social', 'get_cuit', 'editar_entidad_link')
    search_fields = ('entidad__razon_social', 'entidad__cuit')
    autocomplete_fields = ['price_list']

    def get_razon_social(self, obj): return obj.entidad.razon_social
    get_razon_social.short_description = 'Razón Social'

    def get_cuit(self, obj): return obj.entidad.cuit
    get_cuit.short_description = 'CUIT'

    def editar_entidad_link(self, obj):
        url = reverse('admin:entidades_entidad_change', args=[obj.entidad.pk])
        return format_html('<a href="{}">Editar Ficha Completa</a>', url)
    editar_entidad_link.short_description = 'Acciones'

    def add_view(self, request, form_url='', extra_context=None):
        url = reverse('admin:entidades_entidad_add') + '?rol=cliente'
        return HttpResponseRedirect(url)

class ComprobanteVentaItemInline(admin.TabularInline):
    model = ComprobanteVentaItem
    extra = 1
    autocomplete_fields = ['articulo']
    readonly_fields = ('subtotal',)

@admin.register(ComprobanteVenta)
class ComprobanteVentaAdmin(admin.ModelAdmin):
    change_form_template = "admin/ventas/comprobanteventa/change_form.html"
    list_display = ('__str__', 'cliente', 'fecha', 'estado', 'total')
    list_filter = ('estado', 'cliente', 'fecha', 'tipo_comprobante')
    search_fields = ('numero', 'punto_venta')
    inlines = [ComprobanteVentaItemInline]
    readonly_fields = ('letra', 'subtotal', 'impuestos_desglosados', 'total')
    autocomplete_fields = ['cliente']
    fieldsets = (
        (None, {'fields': ('tipo_comprobante', 'cliente', 'fecha', 'estado')}),
        ('Numeración', {'fields': (('punto_venta', 'numero'),)}),
        ('Totales (Calculado al Guardar)',
         {'classes': ('collapse', 'show'), 'fields': ('subtotal', 'impuestos_desglosados', 'total')})
    )
    class Media:
        js = ('admin/js/comprobante_venta_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('api/get-precio-articulo/<str:pk>/',
                 self.admin_site.admin_view(get_precio_articulo),
                 name='ventas_get_precio_articulo'),
            path('api/get-precio-articulo-cliente/<int:cliente_pk>/<str:articulo_pk>/',
                 self.admin_site.admin_view(get_precio_articulo_cliente),
                 name='ventas_get_precio_articulo_cliente'),
            path('api/calcular-totales/',
                 self.admin_site.admin_view(calcular_totales_api),
                 name='ventas_calcular_totales_api'),
        ]
        return custom_urls + urls

    @admin.display(description='Impuestos')
    def impuestos_desglosados(self, obj):
        if not obj.impuestos: return "N/A"
        html = "<ul>"
        for nombre, monto in obj.impuestos.items():
            html += f"<li><strong>{nombre}:</strong> ${float(monto):,.2f}</li>"
        html += "</ul>"
        return format_html(html)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        obj = form.instance
        if not obj.pk: return
        subtotal_calculado = sum(item.subtotal for item in obj.items.all())
        obj.subtotal = subtotal_calculado.quantize(Decimal('0.01'))
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(obj, 'venta')
        obj.impuestos = {k: str(v) for k, v in desglose_impuestos.items()}
        total_impuestos = sum(desglose_impuestos.values())
        obj.total = obj.subtotal + total_impuestos
        obj.save()

class ProductPriceInline(admin.TabularInline):
    """
    Este inline nos permite añadir y editar precios de artículos
    directamente DENTRO de la página de una Lista de Precios.
    """
    model = ProductPrice
    extra = 1
    autocomplete_fields = ['product', 'price_moneda']
    fields = ('product', 'price_monto', 'price_moneda', 'min_quantity', 'max_quantity')

@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    """
    Administrador para el modelo principal de Listas de Precios de Venta.
    """
    list_display = ('name', 'code', 'is_default', 'valid_from', 'valid_until')
    search_fields = ('name', 'code')
    inlines = [ProductPriceInline]

@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    """
    Administrador para ver todos los precios de productos de forma individual.
    Útil para búsquedas y filtros avanzados.
    """
    list_display = ('product', 'price_list', 'price', 'min_quantity')
    list_filter = ('price_list',)
    search_fields = ('product__descripcion', 'product__cod_articulo', 'price_list__name')
    autocomplete_fields = ['product', 'price_list', 'price_moneda']

auditlog.register(ComprobanteVenta)
auditlog.register(Cliente)