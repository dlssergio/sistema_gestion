# al principio del archivo
from auditlog.registry import auditlog
from .models import ComprobanteVenta, Cliente

from django.contrib import admin
from django.urls import reverse, path
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from decimal import Decimal

from .models import Cliente, ComprobanteVenta, ComprobanteVentaItem
# <<< CAMBIO CLAVE: AÑADIMOS LA IMPORTACIÓN QUE FALTABA >>>
from .views import get_precio_articulo, calcular_totales_api
from .services import TaxCalculatorService


class ClienteInline(admin.StackedInline):
    model = Cliente
    can_delete = False
    verbose_name_plural = 'Datos del Cliente'


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('get_razon_social', 'get_cuit', 'editar_entidad_link')
    search_fields = ('entidad__razon_social', 'entidad__cuit')

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

    def has_change_permission(self, request, obj=None): return False


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

    fieldsets = (
        (None, {'fields': ('tipo_comprobante', 'cliente', 'fecha', 'estado')}),
        ('Numeración', {'fields': (('punto_venta', 'numero'),)}),
        ('Totales (Calculado al Guardar)',
         {'classes': ('collapse',), 'fields': ('subtotal', 'impuestos_desglosados', 'total')})
    )

    class Media:
        js = ('admin/js/comprobante_venta_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('api/get-precio-articulo/<str:pk>/',
                 self.admin_site.admin_view(get_precio_articulo),
                 name='ventas_get_precio_articulo'),
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
        subtotal_calculado = sum(item.subtotal for item in obj.items.all())
        obj.subtotal = subtotal_calculado.quantize(Decimal('0.01'))
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(obj)
        obj.impuestos = {k: str(v) for k, v in desglose_impuestos.items()}
        total_impuestos = sum(desglose_impuestos.values())
        obj.total = obj.subtotal + total_impuestos
        obj.save()

# al final del archivo
auditlog.register(ComprobanteVenta)
auditlog.register(Cliente)