# inventario/admin.py (VERSIÓN CON CAMPOS RESTAURADOS)

import json
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from djmoney.forms.fields import MoneyField
from djmoney.forms.widgets import MoneyWidget
from djmoney.money import Money
from auditlog.registry import auditlog
from .models import Articulo, Marca, Rubro, Deposito, StockArticulo, ConversionUnidadMedida, ProveedorArticulo
# <<< INICIO DE LA CORRECCIÓN 1: Se importa 'Impuesto' en lugar del obsoleto 'ReglaImpuesto' >>>
from parametros.models import Moneda, Impuesto, CategoriaImpositiva


class CustomMoneyFormField(MoneyField):
    # ... (Tu código de CustomMoneyFormField se mantiene intacto) ...
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
    precio_venta = MoneyField(label="Precio de Venta", required=False)

    class Meta:
        model = Articulo
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in Moneda.objects.all()]
        if 'precio_venta' in self.fields:
            self.fields['precio_venta'].widget.widgets[1].choices = choices


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin): search_fields = ['nombre']


@admin.register(Rubro)
class RubroAdmin(admin.ModelAdmin): search_fields = ['nombre']


admin.site.register(Deposito)


class ProveedorArticuloInline(admin.TabularInline):
    model = ProveedorArticulo
    extra = 1
    fields = ('proveedor', 'es_fuente_de_verdad', 'fecha_relacion')
    readonly_fields = ('fecha_relacion',)
    autocomplete_fields = ['proveedor']


class StockArticuloInline(admin.TabularInline): model = StockArticulo; extra = 1


class ConversionUnidadMedidaInline(admin.TabularInline):
    model = ConversionUnidadMedida;
    extra = 1;
    autocomplete_fields = ['unidad_externa']


@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    change_form_template = 'admin/inventario/articulo/change_form.html'
    list_display = ('cod_articulo', 'descripcion', 'perfil', 'marca', 'stock_total', 'precio_venta', 'esta_activo',
                    'get_proveedor_fuente_costo')
    list_filter = ('esta_activo', 'marca', 'rubro', 'perfil')

    # <<< INICIO DE LA CORRECCIÓN: Se restaura 'ean' a la lista de búsqueda >>>
    search_fields = ('cod_articulo', 'descripcion', 'ean')
    # <<< FIN DE LA CORRECCIÓN >>>

    autocomplete_fields = ['marca', 'rubro', 'grupo_unidades', 'unidad_medida_stock', 'unidad_medida_venta',
                           'categoria_impositiva', 'precio_costo_moneda', 'precio_venta_moneda']
    filter_horizontal = ('impuestos',)
    readonly_fields = ('precio_final_form',)

    fieldsets = (
        ('Información Principal',
         # <<< Se añade 'ean' y 'qr' para que sean visibles en el formulario >>>
         {'fields': ('cod_articulo', 'ean', 'qr', 'descripcion', 'perfil', 'marca', 'rubro', 'esta_activo')}),
        ('Precios, Costos e Impuestos',
         {'fields': (
             ('precio_costo_monto', 'precio_costo_moneda'), 'utilidad', ('precio_venta_monto', 'precio_venta_moneda'),
             'categoria_impositiva', 'impuestos')}),
        ('Precio Final (Calculado)', {'fields': ('precio_final_form',)}),
        ('Gestión de Inventario y Unidades',
         {'fields': ('administra_stock', 'grupo_unidades', 'unidad_medida_stock', 'unidad_medida_venta')}),
        ('Observaciones', {'classes': ('collapse',), 'fields': ('observaciones', 'nota')}),
    )
    inlines = [ProveedorArticuloInline, StockArticuloInline, ConversionUnidadMedidaInline]

    class Media:
        js = ('admin/js/articulo_admin.js',)

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
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

    # <<< INICIO DE LA CORRECCIÓN 2: Se actualiza la función para usar el nuevo modelo 'Impuesto' >>>
    def add_extra_context(self, request, extra_context=None):
        extra_context = extra_context or {}
        cotizaciones = {str(m.id): m.cotizacion for m in Moneda.objects.all()}
        extra_context['cotizaciones_json'] = json.dumps(cotizaciones, default=str)
        # Se reemplaza la consulta al obsoleto 'ReglaImpuesto' por el nuevo modelo 'Impuesto'.
        tasas_impuestos = list(Impuesto.objects.values('id', 'tasa'))
        extra_context['tasas_impuestos_json'] = json.dumps(tasas_impuestos, default=str)
        return extra_context

    # <<< FIN DE LA CORRECCIÓN 2 >>>

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