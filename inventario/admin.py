# inventario/admin.py

import json
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from djmoney.forms.fields import MoneyField
from djmoney.forms.widgets import MoneyWidget
from djmoney.money import Money
from auditlog.registry import auditlog

# <<< CORRECCIÓN DEFINITIVA: Se importa el nombre del modelo correcto 'PrecioProveedorArticulo' >>>
from compras.models import PrecioProveedorArticulo
from .models import Articulo, Marca, Rubro, Deposito, StockArticulo, ConversionUnidadMedida, ProveedorArticulo
from parametros.models import Moneda, UnidadMedida, ReglaImpuesto


class ProveedorArticuloInline(admin.TabularInline):
    model = ProveedorArticulo
    extra = 1
    fields = ('proveedor', 'es_fuente_de_verdad', 'fecha_relacion')
    readonly_fields = ('fecha_relacion',)
    autocomplete_fields = ['proveedor']

# <<< CORRECCIÓN DEFINITIVA: El inline de solo lectura ahora usa el modelo 'PrecioProveedorArticulo' >>>
class PrecioProveedorArticuloReadOnlyInline(admin.TabularInline):
    model = PrecioProveedorArticulo
    verbose_name_plural = "Precios de Costo por Proveedor (Informativo)"
    can_delete = False
    extra = 0
    # <<< CORRECCIÓN: Se actualizan los campos para reflejar la estructura SIN listas de precios >>>
    fields = ('proveedor', 'precio_costo', 'bonificacion_porcentaje', 'costo_unitario_efectivo')
    readonly_fields = fields
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin): search_fields = ['nombre']

@admin.register(Rubro)
class RubroAdmin(admin.ModelAdmin): search_fields = ['nombre']

@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin): search_fields = ['nombre', 'abreviatura']

admin.site.register(Deposito)

class StockArticuloInline(admin.TabularInline): model = StockArticulo; extra = 1
class ConversionUnidadMedidaInline(admin.TabularInline): model = ConversionUnidadMedida; extra = 1; autocomplete_fields = ['unidad_externa']

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
            raise ValidationError("La moneda con ID '%(id)s' no existe.", params={'id': currency_id})
        except ValidationError as e: raise ValidationError(e)
        except Exception as e: raise ValidationError(f"Error inesperado: {e}")

class ArticuloAdminForm(forms.ModelForm):
    precio_costo = CustomMoneyFormField(label="Precio de Costo", max_digits=12, decimal_places=2)
    precio_venta = CustomMoneyFormField(label="Precio de Venta", max_digits=12, decimal_places=2)
    class Meta:
        model = Articulo
        fields = '__all__'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in Moneda.objects.all()]
        costo_widget = self.fields['precio_costo'].widget
        venta_widget = self.fields['precio_venta'].widget
        if isinstance(costo_widget, MoneyWidget):
            costo_widget.widgets[1].choices = choices
        if isinstance(venta_widget, MoneyWidget):
            venta_widget.widgets[1].choices = choices

@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    form = ArticuloAdminForm
    change_form_template = 'admin/inventario/articulo/change_form.html'
    list_display = ('cod_articulo', 'descripcion', 'perfil', 'marca', 'stock_total', 'precio_venta', 'esta_activo', 'get_proveedor_fuente_costo')
    list_filter = ('esta_activo', 'marca', 'rubro', 'perfil')
    fieldsets = (
        ('Información Principal', {'fields': ('cod_articulo', 'descripcion', 'perfil', 'marca', 'rubro', 'esta_activo')}),
        ('Precios y Costos', {'fields': ('precio_costo', 'utilidad', 'precio_venta', 'impuesto')}),
        ('Precio Final (Calculado)', {'fields': ('precio_final_form',)}),
        ('Configuración de Stock y Unidades', {'fields': ('administra_stock', 'unidad_medida_stock')}),
        ('Observaciones', {'classes': ('collapse',), 'fields': ('observaciones', 'nota')}),
    )
    readonly_fields = ('precio_final_form',)
    inlines = [ ProveedorArticuloInline, PrecioProveedorArticuloReadOnlyInline, StockArticuloInline, ConversionUnidadMedidaInline, ]
    search_fields = ('descripcion', 'cod_articulo')
    autocomplete_fields = ['marca', 'rubro', 'unidad_medida_stock', 'impuesto']
    class Media:
        js = ('admin/js/articulo_admin.js',)

    def add_extra_context(self, request, extra_context=None):
        extra_context = extra_context or {}
        cotizaciones = {str(m.id): m.cotizacion for m in Moneda.objects.all()}
        extra_context['cotizaciones_json'] = json.dumps(cotizaciones, default=str)
        tasas_impuestos = list(ReglaImpuesto.objects.filter(activo=True).values('id', 'tasa'))
        extra_context['tasas_impuestos_json'] = json.dumps(tasas_impuestos, default=str)
        return extra_context

    def add_view(self, request, form_url='', extra_context=None):
        return super().add_view(request, form_url, extra_context=self.add_extra_context(request, extra_context))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return super().change_view(request, object_id, form_url, extra_context=self.add_extra_context(request, extra_context))

    @admin.display(description="Precio Final con Impuestos")
    def precio_final_form(self, obj):
        return "Calculado en tiempo real..."
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        proveedor_id = request.GET.get('proveedor__id__exact')
        if proveedor_id and hasattr(qs.model, 'proveedores'):
            qs = qs.filter(proveedores__id=proveedor_id)
        return qs
    @admin.display(description="Stock Total")
    def stock_total(self, obj): return obj.stock_total
    @admin.display(description="Fuente de Costo Base")
    def get_proveedor_fuente_costo(self, obj):
        prov = obj.proveedor_actualiza_precio
        return prov.entidad.razon_social if prov else "N/A"

auditlog.register(Articulo)
auditlog.register(Marca)