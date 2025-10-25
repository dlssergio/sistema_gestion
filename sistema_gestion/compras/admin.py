# compras/admin.py (VERSIÓN CON ACCIONES MASIVAS AMPLIADAS)

from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from djmoney.money import Money
from django.utils.safestring import mark_safe
from django import forms
from django.shortcuts import render
import json
from decimal import Decimal  # <<< IMPORTACIÓN AÑADIDA para el cálculo de aumento >>>

from .models import (
    Proveedor, ComprobanteCompra, ComprobanteCompraItem,
    ListaPreciosProveedor, ItemListaPreciosProveedor
)
from .views import get_precio_proveedor_json, calcular_totales_compra_api
from ventas.services import TaxCalculatorService


# --- ADMINS (Tu código existente se mantiene intacto) ---
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
    # ... (Tu código para ComprobanteCompraItemInline se mantiene exactamente igual) ...
    model = ComprobanteCompraItem
    extra = 1
    fields = ('articulo', 'cantidad', 'precio_costo_unitario_monto', 'precio_costo_unitario_moneda')
    autocomplete_fields = ['articulo', 'precio_costo_unitario_moneda']


@admin.register(ComprobanteCompra)
class ComprobanteCompraAdmin(admin.ModelAdmin):
    # ... (código sin cambios)
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

    class Media: js = ('admin/js/compras_admin.js',)

    def get_urls(self):
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
        if not hasattr(obj, 'impuestos') or not obj.impuestos: return "N/A"
        list_items = [
            f"<li><strong>{nombre}:</strong> ${float(monto):,.2f}</li>"
            for nombre, monto in obj.impuestos.items()
        ]
        html_string = f"<ul>{''.join(list_items)}</ul>"
        return mark_safe(html_string)


class ItemListaPreciosProveedorInline(admin.TabularInline):
    model = ItemListaPreciosProveedor
    extra = 0
    # <<< INICIO DE LA MODIFICACIÓN >>>
    # 1. Añadimos los campos de descuento para que sean editables.
    #    Para mejorar el layout, los agrupamos.
    fields = (
        'articulo',
        ('precio_lista_monto', 'precio_lista_moneda'),
        ('unidad_medida_compra', 'cantidad_minima'),
        'bonificacion_porcentaje',
        'descuentos_adicionales',
        'descuentos_financieros',
        'codigo_articulo_proveedor',
        'display_costo_efectivo'
    )
    # <<< FIN DE LA MODIFICACIÓN >>>
    autocomplete_fields = ['articulo', 'unidad_medida_compra', 'precio_lista_moneda']
    readonly_fields = ('display_costo_efectivo',)

    @admin.display(description='Costo Efectivo Final')
    def display_costo_efectivo(self, obj):
        if obj.pk:
            try:
                costo = obj.costo_efectivo
                formatted_amount = f"{costo.amount:,.4f}"  # Mostramos 4 decimales para mayor precisión en el costo
                return format_html(
                    '<strong style="color: #28a745;">{} {}</strong>',
                    costo.currency.code,
                    formatted_amount
                )
            except Exception:
                return "Error"
        return "—"


@admin.register(ListaPreciosProveedor)
class ListaPreciosProveedorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'proveedor', 'es_principal', 'es_activa', 'vigente_desde', 'vigente_hasta')
    list_filter = ('proveedor', 'es_activa', 'es_principal')
    search_fields = ('nombre', 'proveedor__entidad__razon_social')
    autocomplete_fields = ['proveedor']
    inlines = [ItemListaPreciosProveedorInline]


# --- FORMULARIOS PARA LAS PÁGINAS INTERMEDIAS DE LAS ACCIONES ---

class DescuentoAdicionalForm(forms.Form):
    descuentos_json = forms.CharField(
        label='Descuentos adicionales (formato JSON)',
        help_text='Ej: [-10, -5] para un 10% y luego un 5% de descuento.',
        widget=forms.TextInput(attrs={'size': '50'})
    )


# <<< INICIO: NUEVOS FORMULARIOS PARA NUEVAS ACCIONES >>>
class AumentoCostoForm(forms.Form):
    porcentaje_aumento = forms.DecimalField(
        label='Porcentaje de aumento (%)',
        help_text='Ej: 30 para aumentar los precios un 30%.',
        max_digits=5,
        decimal_places=2
    )


class BonificacionMasivaForm(forms.Form):
    bonificacion_porcentaje = forms.DecimalField(
        label='Nuevo porcentaje de bonificación (%)',
        help_text='Ej: 15 para aplicar un 15% de bonificación a todos los ítems.',
        max_digits=5,
        decimal_places=2
    )


class DescuentoFinancieroForm(forms.Form):
    descuentos_json = forms.CharField(
        label='Descuentos/Recargos Financieros (formato JSON)',
        help_text='Ej: [-10] para un 10% de dto. por pronto pago. [5] para un 5% de recargo.',
        widget=forms.TextInput(attrs={'size': '50'})
    )


# <<< FIN: NUEVOS FORMULARIOS PARA NUEVAS ACCIONES >>>


@admin.register(ItemListaPreciosProveedor)
class ItemListaPreciosProveedorAdmin(admin.ModelAdmin):
    list_display = ('articulo', 'lista_precios', 'precio_lista_monto', 'precio_lista_moneda', 'display_costo_efectivo')
    search_fields = ('articulo__descripcion', 'lista_precios__nombre', 'codigo_articulo_proveedor')
    list_filter = (('lista_precios__proveedor', admin.RelatedOnlyFieldListFilter), 'lista_precios')
    autocomplete_fields = ('articulo', 'lista_precios', 'precio_lista_moneda')

    # <<< INICIO: AÑADIMOS LAS NUEVAS ACCIONES A LA LISTA >>>
    actions = [
        'aumentar_precio_costo_action',
        'aplicar_descuentos_adicionales_action',
        'aplicar_bonificacion_masiva_action',
        'aplicar_descuentos_financieros_action'
    ]

    # <<< FIN: AÑADIMOS LAS NUEVAS ACCIONES A LA LISTA >>>

    # --- ACCIÓN 1: AUMENTAR PRECIO DE COSTO ---
    @admin.action(description='Aumentar Monto del Precio por Porcentaje')
    def aumentar_precio_costo_action(self, request, queryset):
        if 'apply' in request.POST:
            form = AumentoCostoForm(request.POST)
            if form.is_valid():
                porcentaje = form.cleaned_data['porcentaje_aumento']
                factor = Decimal(1) + (porcentaje / Decimal(100))

                count = 0
                for item in queryset:
                    item.precio_lista_monto *= factor
                    item.save()
                    count += 1

                self.message_user(request, f'Se aumentó el precio de {count} ítem(s) en un {porcentaje}%.')
                return HttpResponseRedirect(request.get_full_path())
        else:
            form = AumentoCostoForm()

        return render(request, 'admin/compras/accion_masiva_form.html', context={
            'title': 'Aumentar Monto del Precio', 'queryset': queryset, 'form': form,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'action_name': 'aumentar_precio_costo_action'
        })

    # --- ACCIÓN 2: APLICAR DESCUENTOS ADICIONALES ---
    @admin.action(description='Aplicar descuentos adicionales masivamente')
    def aplicar_descuentos_adicionales_action(self, request, queryset):
        if 'apply' in request.POST:
            form = DescuentoAdicionalForm(request.POST)
            if form.is_valid():
                descuento_str = form.cleaned_data['descuentos_json']
                try:
                    descuentos = json.loads(descuento_str)
                    if not isinstance(descuentos, list): raise ValueError("El valor debe ser una lista JSON.")

                    # queryset.update() es más eficiente para cambios de valor simple
                    updated_count = queryset.update(descuentos_adicionales=descuentos)

                    self.message_user(request, f'Se aplicaron los descuentos a {updated_count} ítem(s).')
                    return HttpResponseRedirect(request.get_full_path())
                except (json.JSONDecodeError, ValueError) as e:
                    self.message_user(request, f'Error: Formato JSON inválido. {e}', level='error')
        else:
            form = DescuentoAdicionalForm()

        return render(request, 'admin/compras/accion_masiva_form.html', context={
            'title': 'Aplicar Descuentos Adicionales', 'queryset': queryset, 'form': form,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'action_name': 'aplicar_descuentos_adicionales_action'
        })

    # <<< INICIO: NUEVAS ACCIONES >>>
    # --- ACCIÓN 3: APLICAR BONIFICACIÓN ---
    @admin.action(description='Aplicar bonificación masivamente')
    def aplicar_bonificacion_masiva_action(self, request, queryset):
        if 'apply' in request.POST:
            form = BonificacionMasivaForm(request.POST)
            if form.is_valid():
                bonificacion = form.cleaned_data['bonificacion_porcentaje']
                updated_count = queryset.update(bonificacion_porcentaje=bonificacion)
                self.message_user(request, f'Se aplicó la bonificación a {updated_count} ítem(s).')
                return HttpResponseRedirect(request.get_full_path())
        else:
            form = BonificacionMasivaForm()

        return render(request, 'admin/compras/accion_masiva_form.html', context={
            'title': 'Aplicar Bonificación', 'queryset': queryset, 'form': form,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'action_name': 'aplicar_bonificacion_masiva_action'
        })

    # --- ACCIÓN 4: APLICAR DESCUENTOS FINANCIEROS ---
    @admin.action(description='Aplicar descuentos/recargos financieros masivamente')
    def aplicar_descuentos_financieros_action(self, request, queryset):
        if 'apply' in request.POST:
            form = DescuentoFinancieroForm(request.POST)
            if form.is_valid():
                descuento_str = form.cleaned_data['descuentos_json']
                try:
                    descuentos = json.loads(descuento_str)
                    if not isinstance(descuentos, list): raise ValueError("El valor debe ser una lista JSON.")

                    updated_count = queryset.update(descuentos_financieros=descuentos)

                    self.message_user(request,
                                      f'Se aplicaron los descuentos/recargos financieros a {updated_count} ítem(s).')
                    return HttpResponseRedirect(request.get_full_path())
                except (json.JSONDecodeError, ValueError) as e:
                    self.message_user(request, f'Error: Formato JSON inválido. {e}', level='error')
        else:
            form = DescuentoFinancieroForm()

        return render(request, 'admin/compras/accion_masiva_form.html', context={
            'title': 'Aplicar Descuentos/Recargos Financieros', 'queryset': queryset, 'form': form,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'action_name': 'aplicar_descuentos_financieros_action'
        })

    # <<< FIN: NUEVAS ACCIONES >>>

    @admin.display(description='Costo Efectivo Final')
    def display_costo_efectivo(self, obj):
        if obj.pk:
            try:
                costo = obj.costo_efectivo
                formatted_amount = f"{costo.amount:,.4f}"
                return format_html(
                    '<strong style="color: #28a745;">{} {}</strong>',
                    costo.currency.code,
                    formatted_amount
                )
            except Exception:
                return "Error"
        return "—"