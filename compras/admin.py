# compras/admin.py

from auditlog.registry import auditlog
from django import forms
from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from django.core.exceptions import ValidationError
from djmoney.forms.widgets import MoneyWidget
from djmoney.money import Money
from djmoney.forms.fields import MoneyField
from decimal import Decimal

from .models import Proveedor, ComprobanteCompra, ComprobanteCompraItem, PrecioProveedorArticulo
from .views import calcular_totales_compra_api, get_precio_proveedor_json
from parametros.models import Moneda
from ventas.services import TaxCalculatorService
from inventario.models import Articulo


class CustomMoneyFormField(MoneyField):
    def clean(self, value):
        if not value or not all(value):
            if self.required: raise ValidationError(self.error_messages['required'])
            return None
        amount_str, currency_id = value
        try:
            amount = forms.DecimalField(max_digits=14, decimal_places=4, required=self.required).clean(amount_str)
            currency = Moneda.objects.get(pk=currency_id)
            return Money(amount, currency.simbolo)
        except Moneda.DoesNotExist:
            raise ValidationError(f"La moneda con ID '{currency_id}' no existe.")
        except Exception as e:
            raise ValidationError(f"Error inesperado al procesar el costo: {e}")


class PrecioProveedorArticuloInline(admin.TabularInline):
    model = PrecioProveedorArticulo
    formfield_overrides = {MoneyField: {'form_class': CustomMoneyFormField}}
    extra = 1
    autocomplete_fields = ['articulo', 'unidad_medida_compra']
    fields = ('articulo', 'unidad_medida_compra', 'precio_costo', 'bonificacion_porcentaje', 'descuentos_adicionales',
              'descuentos_financieros', 'codigo_articulo_proveedor', 'costo_unitario_efectivo')
    readonly_fields = ('costo_unitario_efectivo',)
    verbose_name_plural = "Artículos y Precios de este Proveedor"


# <<< ARQUITECTURA FINAL Y CORRECTA: Un único admin para Proveedores >>>
# Este admin gestionará tanto a los proveedores como sus listas de precios.
@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('get_razon_social', 'codigo_proveedor', 'get_cuit', 'editar_entidad_link')
    search_fields = ('entidad__razon_social', 'entidad__cuit', 'codigo_proveedor', 'nombre_fantasia')
    inlines = [PrecioProveedorArticuloInline]
    filter_horizontal = ('roles',)  # Restaurado desde tu archivo original

    def get_razon_social(self, obj): return obj.entidad.razon_social

    get_razon_social.short_description = 'Razón Social'

    def get_cuit(self, obj): return obj.entidad.cuit

    get_cuit.short_description = 'CUIT'

    # <<< RESTAURADO: Funcionalidad crítica para editar la entidad completa >>>
    @admin.display(description="Acciones")
    def editar_entidad_link(self, obj):
        url = reverse('admin:entidades_entidad_change', args=[obj.entidad.pk])
        return format_html('<a href="{}">Editar Ficha Completa</a>', url)

    # <<< RESTAURADO: Funcionalidad crítica para AÑADIR proveedores >>>
    def add_view(self, request, form_url='', extra_context=None):
        """Redirige el botón 'Añadir' al formulario unificado de Entidad."""
        url = reverse('admin:entidades_entidad_add') + '?rol=proveedor'
        return HttpResponseRedirect(url)


# <<< DESTRUIDO: Se elimina por completo la arquitectura fallida del Proxy Model >>>
# No más 'ProveedorProxy' ni 'ProveedorListaPreciosAdmin'.

class ComprobanteCompraItemForm(forms.ModelForm):
    precio_costo_unitario = CustomMoneyFormField(label="Costo Unitario", max_digits=12, decimal_places=2)

    class Meta:
        model = ComprobanteCompraItem
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in Moneda.objects.all()]
        costo_widget = self.fields['precio_costo_unitario'].widget
        if isinstance(costo_widget, MoneyWidget):
            costo_widget.widgets[1].choices = choices


class ComprobanteCompraItemInline(admin.TabularInline):
    model = ComprobanteCompraItem
    form = ComprobanteCompraItemForm
    extra = 1
    raw_id_fields = ['articulo']
    autocomplete_fields = []

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "articulo":
            proveedor_id = request.GET.get('proveedor__id__exact') or request.POST.get('proveedor')
            if proveedor_id:
                # La lógica de filtrado es correcta y se mantiene
                articulos_validos_ids = PrecioProveedorArticulo.objects.filter(
                    proveedor_id=proveedor_id
                ).values_list('articulo_id', flat=True)
                kwargs["queryset"] = Articulo.objects.filter(pk__in=articulos_validos_ids)
            else:
                kwargs["queryset"] = Articulo.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ComprobanteCompra)
class ComprobanteCompraAdmin(admin.ModelAdmin):
    change_form_template = "admin/compras/comprobantecompra/change_form.html"
    list_display = ('__str__', 'proveedor', 'fecha', 'estado', 'total')
    inlines = [ComprobanteCompraItemInline]
    readonly_fields = ('letra', 'subtotal', 'impuestos_desglosados', 'total')
    fieldsets = (
        (None, {'fields': ('tipo_comprobante', 'proveedor', 'fecha', 'estado')}),
        ('Numeración', {'fields': (('punto_venta', 'numero'),)}),
        ('Relaciones', {'fields': ('comprobante_origen',)}),
        ('Totales (Calculado al Guardar)',
         {'classes': ('collapse',), 'fields': ('subtotal', 'impuestos_desglosados', 'total')})
    )

    class Media:
        js = ('admin/js/compras_admin.js',)

    def get_urls(self):
        from .views import calcular_totales_compra_api, get_precio_proveedor_json
        urls = super().get_urls()
        custom_urls = [
            path('get-precio-proveedor/<int:proveedor_pk>/<str:articulo_pk>/',
                 self.admin_site.admin_view(get_precio_proveedor_json), name='compras_get_precio_proveedor'),
            path('api/calcular-totales/', self.admin_site.admin_view(calcular_totales_compra_api),
                 name='compras_calcular_totales_api'),
        ]
        return custom_urls + urls

    @admin.display(description='Impuestos')
    def impuestos_desglosados(self, obj):
        if not obj.impuestos: return "N/A"
        html = "<ul>";
        for nombre, monto in obj.impuestos.items():
            html += f"<li><strong>{nombre}:</strong> ${float(monto):,.2f}</li>"
        html += "</ul>";
        return format_html(html)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        obj = form.instance;
        moneda_base = 'ARS'
        if obj.items.exists(): moneda_base = obj.items.first().precio_costo_unitario.currency.code
        subtotal_calculado = sum(item.subtotal for item in obj.items.all())
        obj.subtotal = Money(subtotal_calculado.amount, moneda_base)
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(obj, 'compra')
        obj.impuestos = {k: str(v) for k, v in desglose_impuestos.items()}
        total_impuestos = sum(desglose_impuestos.values())
        obj.total = obj.subtotal + Money(total_impuestos, moneda_base)
        obj.save()


auditlog.register(ComprobanteCompra)
# <<< CORRECCIÓN: Se elimina el registro de auditoría para el proxy que ya no existe >>>
# auditlog.register(ProveedorProxy)
# El modelo base 'Proveedor' ya está cubierto por el registro de su admin.