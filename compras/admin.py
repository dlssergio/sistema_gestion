from django import forms
from django.contrib import admin
from django.urls import reverse, path
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from django.core.exceptions import ValidationError
from djmoney.forms.widgets import MoneyWidget
from djmoney.money import Money
from djmoney.forms.fields import MoneyField

from .models import Proveedor, ComprobanteCompra, ComprobanteCompraItem
from .views import get_articulo_costo_json
from parametros.models import Moneda


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


# --- CAMPO DE FORMULARIO PERSONALIZADO (Sin Cambios) ---
class CustomMoneyFormField(MoneyField):
    def clean(self, value):
        if not value or not all(value):
            if self.required:
                raise ValidationError(self.error_messages['required'])
            return None
        amount_str, currency_id = value
        try:
            amount = forms.DecimalField(max_digits=12, decimal_places=2, required=self.required).clean(amount_str)
            currency = Moneda.objects.get(pk=currency_id)
            return Money(amount, currency.simbolo)
        except Moneda.DoesNotExist:
            raise ValidationError("La moneda con ID '%(id)s' no existe.", params={'id': currency_id})
        except ValidationError as e:
            raise ValidationError(e)
        except Exception as e:
            raise ValidationError(f"Error inesperado al procesar el costo: {e}")


# --- FORMULARIO DE ITEM (Sin Cambios) ---
class ComprobanteCompraItemForm(forms.ModelForm):
    precio_costo_unitario = CustomMoneyFormField(label="Costo Unitario")

    class Meta:
        model = ComprobanteCompraItem
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        moneda_queryset = Moneda.objects.all()
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in moneda_queryset]
        costo_widget = self.fields['precio_costo_unitario'].widget
        if isinstance(costo_widget, MoneyWidget) and hasattr(costo_widget, 'widgets'):
            costo_widget.widgets[1].choices = choices


class ComprobanteCompraItemInline(admin.TabularInline):
    model = ComprobanteCompraItem
    form = ComprobanteCompraItemForm
    extra = 1
    autocomplete_fields = ['articulo']


@admin.register(ComprobanteCompra)
class ComprobanteCompraAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'proveedor', 'fecha', 'estado', 'total')
    list_filter = ('estado', 'proveedor', 'fecha', 'tipo_comprobante')
    search_fields = ('numero', 'punto_venta')
    inlines = [ComprobanteCompraItemInline]
    readonly_fields = ('total', 'letra')
    autocomplete_fields = ['proveedor']
    fieldsets = (
        (None, {'fields': ('tipo_comprobante', 'proveedor', 'fecha', 'estado')}),
        ('Numeración', {'fields': (('punto_venta', 'numero'),)}),
        ('Relaciones', {'fields': ('comprobante_origen',)})
    )

    class Media:
        js = ('admin/js/compras_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'get-articulo-costo/<str:articulo_pk>/',
                self.admin_site.admin_view(get_articulo_costo_json),
                name='compras_get_articulo_costo'
            )
        ]
        return custom_urls + urls

    # <<< LA SOLUCIÓN: MÉTODO PARA CALCULAR Y GUARDAR EL TOTAL >>>
    def save_formset(self, request, form, formset, change):
        # Primero, dejamos que Django guarde los items como siempre
        super().save_formset(request, form, formset, change)

        # Obtenemos la instancia del Comprobante de Compra que se está guardando
        obj = form.instance

        # Calculamos la suma de los subtotales de todos sus items
        # sum() funciona perfectamente con una lista de objetos Money (si todos tienen la misma moneda)
        # La propiedad 'subtotal' en el modelo ComprobanteCompraItem ya calcula cantidad * precio
        total_calculado = sum(item.subtotal for item in obj.items.all())

        # Actualizamos el campo total del comprobante y lo guardamos
        # Se guarda una vez más para persistir el total calculado
        obj.total = total_calculado
        obj.save()