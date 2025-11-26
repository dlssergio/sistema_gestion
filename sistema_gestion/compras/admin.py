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


# --- CLASE FORM FIELD ---
class CustomMoneyFormField(MoneyField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def decompress(self, value):
        if isinstance(value, Money):
            try:
                moneda = Moneda.objects.get(simbolo=value.currency.code)
                return [value.amount, moneda.pk]
            except Moneda.DoesNotExist:
                return [value.amount, None]
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


# --- FORMULARIOS ---

class ComprobanteCompraItemForm(forms.ModelForm):
    # Campo virtual unificado
    precio_costo_unitario = CustomMoneyFormField(label="Costo Unitario", required=False)

    class Meta:
        model = ComprobanteCompraItem
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in Moneda.objects.all()]
        self.fields['precio_costo_unitario'].widget.widgets[1].choices = choices

        # Cargar valor inicial si existe
        if self.instance.pk:
            self.initial['precio_costo_unitario'] = self.instance.precio_costo_unitario

    def save(self, commit=True):
        # Lógica de mapeo inverso: Widget -> Campos del Modelo
        instance = super().save(commit=False)
        val_precio = self.cleaned_data.get('precio_costo_unitario')

        if val_precio:
            instance.precio_costo_unitario_monto = val_precio.amount
            try:
                moneda = Moneda.objects.filter(simbolo=val_precio.currency.code).first()
                if moneda:
                    instance.precio_costo_unitario_moneda = moneda
            except Exception:
                pass

        if commit:
            instance.save()
        return instance


class ItemListaPreciosProveedorForm(forms.ModelForm):
    precio_lista = CustomMoneyFormField(label="Precio de Lista", required=False)

    class Meta:
        model = ItemListaPreciosProveedor
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in Moneda.objects.all()]
        self.fields['precio_lista'].widget.widgets[1].choices = choices
        if self.instance.pk:
            self.initial['precio_lista'] = self.instance.precio_lista

    def save(self, commit=True):
        instance = super().save(commit=False)
        val_precio = self.cleaned_data.get('precio_lista')
        if val_precio:
            instance.precio_lista_monto = val_precio.amount
            try:
                moneda = Moneda.objects.filter(simbolo=val_precio.currency.code).first()
                if moneda:
                    instance.precio_lista_moneda = moneda
            except Exception:
                pass

        if commit:
            instance.save()
        return instance


# --- INLINES Y ADMINS ---

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
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
    model = ComprobanteCompraItem
    form = ComprobanteCompraItemForm
    extra = 1
    autocomplete_fields = ['articulo']

    # CORRECCIÓN VISUAL: Definimos explícitamente qué campos mostrar.
    # Omitimos '_monto' y '_moneda' para que solo se vea el widget combinado 'precio_costo_unitario'
    fields = ('articulo', 'cantidad', 'precio_costo_unitario')


@admin.register(ComprobanteCompra)
class ComprobanteCompraAdmin(admin.ModelAdmin):
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
        # Intentamos obtener la moneda del primer item guardado
        if obj.items.exists():
            primer_item = obj.items.first()
            if primer_item.precio_costo_unitario_moneda:
                moneda_base = primer_item.precio_costo_unitario_moneda.simbolo

        subtotal_calculado = sum(item.subtotal for item in obj.items.all())
        obj.subtotal = Money(subtotal_calculado.amount, moneda_base)
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(obj, 'compra')
        obj.impuestos = {k: str(v) for k, v in desglose_impuestos.items()}
        total_impuestos = sum(desglose_impuestos.values())
        obj.total = obj.subtotal + Money(total_impuestos, moneda_base)
        obj.save()


class ItemListaPreciosProveedorInline(admin.TabularInline):
    model = ItemListaPreciosProveedor
    form = ItemListaPreciosProveedorForm
    extra = 0
    autocomplete_fields = ['articulo', 'unidad_medida_compra']
    # También ajustamos aquí para evitar duplicados si ocurrieran
    fields = ('articulo', 'unidad_medida_compra', 'precio_lista', 'bonificacion_porcentaje', 'cantidad_minima',
              'codigo_articulo_proveedor')


@admin.register(ListaPreciosProveedor)
class ListaPreciosProveedorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'proveedor', 'es_principal', 'es_activa', 'vigente_desde', 'vigente_hasta')
    list_filter = ('proveedor', 'es_activa', 'es_principal')
    search_fields = ('nombre', 'proveedor__entidad__razon_social')
    autocomplete_fields = ['proveedor']
    inlines = [ItemListaPreciosProveedorInline]


@admin.register(ItemListaPreciosProveedor)
class ItemListaPreciosProveedorAdmin(admin.ModelAdmin):
    form = ItemListaPreciosProveedorForm
    list_display = ('articulo', 'lista_precios', 'precio_lista')
    search_fields = ('articulo__descripcion', 'lista_precios__nombre', 'codigo_articulo_proveedor')
    list_filter = (('lista_precios__proveedor', admin.RelatedOnlyFieldListFilter),)
    autocomplete_fields = ('articulo', 'lista_precios')