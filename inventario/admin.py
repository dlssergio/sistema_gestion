# inventario/admin.py (VERSIÓN DEFINITIVA CORREGIDA)

import json
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from djmoney.forms.fields import MoneyField
from djmoney.forms.widgets import MoneyWidget
from djmoney.money import Money
from auditlog.registry import auditlog

from .models import Articulo, Marca, Rubro, Deposito, StockArticulo, ConversionUnidadMedida, ProveedorArticulo
from parametros.models import Moneda, UnidadMedida, ReglaImpuesto


# EXPLICACIÓN: Se mantiene la definición de CustomMoneyFormField aquí.
# Es necesario para el formulario del Artículo.
class CustomMoneyFormField(MoneyField):
    def clean(self, value):
        if not value or not all(value):
            if self.required: raise ValidationError(self.error_messages['required'])
            return None
        amount_str, currency_id = value
        try:
            currency = Moneda.objects.get(pk=currency_id)
            amount = forms.DecimalField(max_digits=14, decimal_places=4, required=self.required).clean(amount_str)
            return Money(amount, currency.simbolo)
        except Moneda.DoesNotExist:
            raise ValidationError(f"La moneda con ID '{currency_id}' no existe.")
        except Exception as e:
            raise ValidationError(f"Error inesperado al procesar el costo: {e}")


class ArticuloAdminForm(forms.ModelForm):
    precio_costo = CustomMoneyFormField(label="Precio de Costo", required=False)
    precio_venta = CustomMoneyFormField(label="Precio de Venta", required=False)

    class Meta:
        model = Articulo
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in Moneda.objects.all()]
        self.fields['precio_costo'].widget.widgets[1].choices = choices
        self.fields['precio_venta'].widget.widgets[1].choices = choices


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin): search_fields = ['nombre']


@admin.register(Rubro)
class RubroAdmin(admin.ModelAdmin): search_fields = ['nombre']


@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin): search_fields = ['nombre', 'simbolo']


admin.site.register(Deposito)


class ProveedorArticuloInline(admin.TabularInline):
    model = ProveedorArticulo
    extra = 1
    fields = ('proveedor', 'es_fuente_de_verdad', 'fecha_relacion')
    readonly_fields = ('fecha_relacion',)
    autocomplete_fields = ['proveedor']


class StockArticuloInline(admin.TabularInline): model = StockArticulo; extra = 1


class ConversionUnidadMedidaInline(
    admin.TabularInline): model = ConversionUnidadMedida; extra = 1; autocomplete_fields = ['unidad_externa']


@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    form = ArticuloAdminForm  # EXPLICACIÓN: Se asigna el formulario personalizado.
    change_form_template = 'admin/inventario/articulo/change_form.html'
    list_display = ('cod_articulo', 'descripcion', 'perfil', 'marca', 'stock_total', 'precio_venta', 'esta_activo',
                    'get_proveedor_fuente_costo')
    list_filter = ('esta_activo', 'marca', 'rubro', 'perfil')
    search_fields = ('cod_articulo', 'descripcion', 'ean')  # Crítico para autocomplete_fields
    autocomplete_fields = ['marca', 'rubro', 'unidad_medida_stock', 'impuesto']
    readonly_fields = ('precio_final_form',)
    inlines = [ProveedorArticuloInline, StockArticuloInline, ConversionUnidadMedidaInline]
    fieldsets = (
        ('Información Principal',
         {'fields': ('cod_articulo', 'descripcion', 'perfil', 'marca', 'rubro', 'esta_activo')}),
        ('Precios y Costos', {'fields': ('precio_costo', 'utilidad', 'precio_venta', 'impuesto')}),
        ('Precio Final (Calculado)', {'fields': ('precio_final_form',)}),
        ('Configuración de Stock y Unidades', {'fields': ('administra_stock', 'unidad_medida_stock')}),
        ('Observaciones', {'classes': ('collapse',), 'fields': ('observaciones', 'nota')}),
    )

    class Media:
        js = ('admin/js/articulo_admin.js',)

    # EXPLICACIÓN ARQUITECTÓNICA: Este es el "hook" correcto para filtrar los `autocomplete_fields`.
    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        # El JavaScript enviará el ID del proveedor en los parámetros de la petición AJAX.
        proveedor_id = request.GET.get('proveedor_id')

        if proveedor_id:
            queryset = queryset.filter(proveedores__pk=proveedor_id)

        return queryset, use_distinct

    @admin.display(description="Stock Total")
    def stock_total(self, obj): return obj.stock_total

    @admin.display(description="Fuente de Costo Base")
    def get_proveedor_fuente_costo(self, obj):
        prov = obj.proveedor_actualiza_precio
        return prov.entidad.razon_social if prov else "N/A"

    # ... (resto de métodos sin cambios)
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
        return super().change_view(request, object_id, form_url,
                                   extra_context=self.add_extra_context(request, extra_context))

    @admin.display(description="Precio Final con Impuestos")
    def precio_final_form(self, obj):
        return "Calculado en tiempo real..."


auditlog.register(Articulo)
auditlog.register(Marca)