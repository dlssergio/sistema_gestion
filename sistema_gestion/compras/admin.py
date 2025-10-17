# compras/admin.py

from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from django import forms
from django.core.exceptions import ValidationError
from djmoney.forms.widgets import MoneyWidget
from djmoney.money import Money
from djmoney.forms.fields import MoneyField

from .models import (
    Proveedor, ComprobanteCompra, ComprobanteCompraItem,
    ListaPreciosProveedor, ItemListaPreciosProveedor
)
from .views import get_precio_proveedor_json, calcular_totales_compra_api
from parametros.models import Moneda
from ventas.services import TaxCalculatorService


# --- FORMULARIOS PERSONALIZADOS (LÓGICA CORRECTA Y CENTRALIZADA) ---

class CustomMoneyFormField(MoneyField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # EXPLICACIÓN ARQUITECTÓNICA: Este es el método que faltaba.
    # Se ejecuta cuando el formulario se carga con datos existentes desde la base de datos.
    # Su trabajo es "descomprimir" el objeto Money en los dos valores que el widget necesita.
    def decompress(self, value):
        if isinstance(value, Money):
            # `value` es el objeto Money(monto, simbolo) que viene de la BD.
            try:
                # Buscamos en nuestra tabla Moneda el objeto que corresponde al símbolo.
                moneda = Moneda.objects.get(simbolo=value.currency.code)
                # Devolvemos una lista: [monto, ID_de_nuestra_moneda]
                return [value.amount, moneda.pk]
            except Moneda.DoesNotExist:
                # Si por alguna razón la moneda de la BD no está en nuestra tabla,
                # devolvemos el monto pero sin moneda seleccionada.
                return [value.amount, None]
        # Si es un formulario nuevo, no hay valores iniciales.
        return [None, None]

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


class ComprobanteCompraItemForm(forms.ModelForm):
    precio_costo_unitario = CustomMoneyFormField(label="Costo Unitario", required=False)

    class Meta:
        model = ComprobanteCompraItem
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in Moneda.objects.all()]
        self.fields['precio_costo_unitario'].widget.widgets[1].choices = choices


# EXPLICACIÓN ARQUITECTÓNICA: Este formulario es la clave.
# Centraliza la lógica de carga de monedas para CUALQUIER lugar donde se edite un ítem de lista de precios.
class ItemListaPreciosProveedorForm(forms.ModelForm):
    precio_lista = CustomMoneyFormField(label="Precio de Lista", required=False)

    class Meta:
        model = ItemListaPreciosProveedor
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in Moneda.objects.all()]
        self.fields['precio_lista'].widget.widgets[1].choices = choices


# --- INLINES Y ADMINS ---

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    # ... (sin cambios)
    list_display = ('get_razon_social', 'codigo_proveedor', 'get_cuit', 'editar_entidad_link')
    search_fields = ('entidad__razon_social', 'entidad__cuit', 'codigo_proveedor', 'nombre_fantasia')
    filter_horizontal = ('roles',)

    def get_razon_social(self, obj): return obj.entidad.razon_social

    get_razon_social.short_description = 'Razón Social'

    def get_cuit(self, obj): return obj.entidad.cuit

    get_cuit.short_description = 'CUIT'

    def editar_entidad_link(self, obj):
        url = reverse('admin:entidades_entidad_change', args=[obj.entidad.pk])
        return format_html('<a href="{}">Editar Ficha Completa</a>', url)

    editar_entidad_link.short_description = 'Acciones'

    def add_view(self, request, form_url='', extra_context=None):
        url = reverse('admin:entidades_entidad_add') + '?rol=proveedor'
        return HttpResponseRedirect(url)


class ComprobanteCompraItemInline(admin.TabularInline):
    # ... (sin cambios)
    model = ComprobanteCompraItem
    form = ComprobanteCompraItemForm
    extra = 1
    autocomplete_fields = ['articulo']
    raw_id_fields = []


@admin.register(ComprobanteCompra)
class ComprobanteCompraAdmin(admin.ModelAdmin):
    # ... (sin cambios)
    change_form_template = "admin/compras/comprobantecompra/change_form.html"
    list_display = ('__str__', 'proveedor', 'fecha', 'estado', 'total')
    inlines = [ComprobanteCompraItemInline]
    readonly_fields = ('letra', 'subtotal', 'impuestos_desglosados', 'total')
    autocomplete_fields = ['proveedor']
    fieldsets = (
        (None, {'fields': ('tipo_comprobante', 'proveedor', 'fecha', 'estado')}),
        ('Numeración', {'fields': (('punto_venta', 'numero'),)}),
        ('Relaciones', {'fields': ('comprobante_origen',)}),
        ('Totales (Calculado en tiempo real)',
         {'classes': ('collapse', 'show'), 'fields': ('subtotal', 'impuestos_desglosados', 'total')})
    )

    class Media:
        js = ('admin/js/compras_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('get-precio-proveedor/<int:proveedor_pk>/<str:articulo_pk>/',
                 self.admin_site.admin_view(get_precio_proveedor_json), name='compras_get_precio_proveedor'),
            path('api/calcular-totales/',
                 self.admin_site.admin_view(calcular_totales_compra_api), name='compras_calcular_totales_api'),
        ]
        return custom_urls + urls

    @admin.display(description='Impuestos')
    def impuestos_desglosados(self, obj):
        if not obj.impuestos: return "N/A"
        html = "<ul>";
        for nombre, monto in obj.impuestos.items(): html += f"<li><strong>{nombre}:</strong> ${float(monto):,.2f}</li>"
        html += "</ul>";
        return format_html(html)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        obj = form.instance;
        if not obj.pk: return
        moneda_base = 'ARS'
        if obj.items.exists():
            primer_item_con_moneda = obj.items.first()
            if primer_item_con_moneda and primer_item_con_moneda.precio_costo_unitario:
                moneda_base = primer_item_con_moneda.precio_costo_unitario.currency.code
        subtotal_calculado = sum(item.subtotal for item in obj.items.all())
        obj.subtotal = Money(subtotal_calculado.amount, moneda_base)
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(obj, 'compra')
        obj.impuestos = {k: str(v) for k, v in desglose_impuestos.items()}
        total_impuestos = sum(desglose_impuestos.values())
        obj.total = obj.subtotal + Money(total_impuestos, moneda_base)
        obj.save()


class ItemListaPreciosProveedorInline(admin.TabularInline):
    model = ItemListaPreciosProveedor
    # <<< LA CLAVE DE LA SOLUCIÓN >>>
    # Le decimos explícitamente a este inline que use nuestro formulario personalizado.
    form = ItemListaPreciosProveedorForm
    extra = 0
    autocomplete_fields = ['articulo', 'unidad_medida_compra']
    fields = ('articulo', 'unidad_medida_compra', 'precio_lista', 'bonificacion_porcentaje', 'cantidad_minima',
              'codigo_articulo_proveedor')
    raw_id_fields = []


@admin.register(ListaPreciosProveedor)
class ListaPreciosProveedorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'proveedor', 'es_principal', 'es_activa', 'vigente_desde', 'vigente_hasta')
    list_filter = ('proveedor', 'es_activa', 'es_principal')
    search_fields = ('nombre', 'proveedor__entidad__razon_social')
    autocomplete_fields = ['proveedor']
    inlines = [ItemListaPreciosProveedorInline]


@admin.register(ItemListaPreciosProveedor)
class ItemListaPreciosProveedorAdmin(admin.ModelAdmin):
    # <<< LA OTRA CLAVE DE LA SOLUCIÓN >>>
    # También le decimos a la vista de edición principal que use el mismo formulario.
    form = ItemListaPreciosProveedorForm
    list_display = ('articulo', 'lista_precios', 'precio_lista')
    search_fields = ('articulo__descripcion', 'lista_precios__nombre', 'codigo_articulo_proveedor')
    list_filter = (('lista_precios__proveedor', admin.RelatedOnlyFieldListFilter),)
    autocomplete_fields = ('articulo', 'lista_precios')