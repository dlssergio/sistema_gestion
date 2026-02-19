# compras/admin.py (VERSIÓN FINAL ENTERPRISE: E-CHEQ + FINANZAS)

from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from django import forms
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from djmoney.forms.widgets import MoneyWidget
from djmoney.money import Money
from djmoney.forms.fields import MoneyField
from decimal import Decimal

from .models import (
    Proveedor, ComprobanteCompra, ComprobanteCompraItem,
    ListaPreciosProveedor, ItemListaPreciosProveedor,
    OrdenPago, OrdenPagoImputacion, OrdenPagoValor
)
from .views import get_precio_proveedor_json, calcular_totales_compra_api, get_comprobante_info
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
    precio_costo_unitario = CustomMoneyFormField(label="Costo Unitario", required=False)

    class Meta:
        model = ComprobanteCompraItem
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(m.id, f"{m.simbolo} - {m.nombre}") for m in Moneda.objects.all()]
        self.fields['precio_costo_unitario'].widget.widgets[1].choices = choices
        if self.instance.pk:
            self.initial['precio_costo_unitario'] = self.instance.precio_costo_unitario

    def save(self, commit=True):
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


# --- ADMINS DE COMPRAS ---

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('get_razon_social', 'codigo_proveedor', 'get_cuit', 'editar_entidad_link')
    search_fields = ('entidad__razon_social', 'entidad__cuit', 'codigo_proveedor', 'nombre_fantasia')
    filter_horizontal = ('roles',)
    actions = ['generar_orden_pago']

    fieldsets = (
        ('Datos Generales', {
            'fields': ('entidad', 'codigo_proveedor', 'nombre_fantasia', 'roles')
        }),
        ('Financiero', {
            'fields': ('limite_credito',)
        }),
        ('Impuestos y Retenciones', {
            'fields': (
                ('regimen_ganancias', 'regimen_iibb'),
                ('situacion_iibb', 'nro_iibb')
            ),
            'description': 'Configure aquí los regímenes por defecto para el cálculo automático en Órdenes de Pago.'
        }),
    )

    def get_razon_social(self, obj):
        return obj.entidad.razon_social

    get_razon_social.short_description = 'Razón Social'

    def get_cuit(self, obj):
        return obj.entidad.cuit

    get_cuit.short_description = 'CUIT'

    def editar_entidad_link(self, obj):
        url = reverse('admin:entidades_entidad_change', args=[obj.entidad.pk])
        return format_html('<a href="{}">Editar Ficha Completa</a>', url)

    editar_entidad_link.short_description = 'Acciones'

    def add_view(self, request, form_url='', extra_context=None):
        url = reverse('admin:entidades_entidad_add') + '?rol=proveedor'
        return HttpResponseRedirect(url)

    @admin.action(description="💰 Generar Orden de Pago (Pagar Pendientes)")
    def generar_orden_pago(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, "Seleccione solo un proveedor.", level=messages.WARNING)
            return

        proveedor = queryset.first()
        pendientes = ComprobanteCompra.objects.filter(
            proveedor=proveedor,
            estado=ComprobanteCompra.Estado.CONFIRMADO,
            saldo_pendiente__gt=0
        )

        if not pendientes.exists():
            self.message_user(request, f"El proveedor {proveedor} no tiene facturas pendientes de pago.",
                              level=messages.INFO)
            return

        op = OrdenPago.objects.create(
            proveedor=proveedor,
            fecha=timezone.now(),
            estado=OrdenPago.Estado.BORRADOR,
            creado_por=request.user
        )

        for comp in pendientes:
            OrdenPagoImputacion.objects.create(
                orden_pago=op,
                comprobante=comp,
                monto_imputado=comp.saldo_pendiente
            )

        url = reverse('admin:compras_ordenpago_change', args=[op.pk])
        self.message_user(request, f"Orden de Pago generada con {pendientes.count()} facturas.")
        return redirect(url)


class ComprobanteCompraItemInline(admin.TabularInline):
    model = ComprobanteCompraItem
    form = ComprobanteCompraItemForm
    extra = 1
    autocomplete_fields = ['articulo']
    fields = ('articulo', 'cantidad', 'precio_costo_unitario')


@admin.register(ComprobanteCompra)
class ComprobanteCompraAdmin(admin.ModelAdmin):
    change_form_template = "admin/compras/comprobantecompra/change_form.html"
    list_display = (
        '__str__', 'proveedor', 'fecha', 'numero_completo_display', 'condicion_compra', 'estado', 'total',
        'saldo_visual')
    list_filter = ('estado', 'proveedor', 'fecha', 'tipo_comprobante', 'condicion_compra')
    search_fields = ('numero', 'proveedor__entidad__razon_social')
    inlines = [ComprobanteCompraItemInline]
    autocomplete_fields = ['proveedor', 'serie', 'comprobante_origen']
    readonly_fields = (
        'letra',
        'subtotal',
        'impuestos_desglosados',
        'total',
        'saldo_pendiente'
    )

    fieldsets = (
        ('Documento Interno (Opcional)', {
            'fields': ('serie',),
            'description': 'Seleccione una serie <b>solo</b> si está generando una Orden de Compra o Devolución interna. Para cargar una factura de proveedor, deje este campo vacío.'
        }),
        ('Datos del Proveedor', {
            'fields': (
                ('proveedor', 'fecha'),
                ('tipo_comprobante', 'estado'),
                'condicion_compra'
            )
        }),
        ('Vinculación (Circuito de Compras)', {
            'fields': ('comprobante_origen',),
            'description': 'Si es una Factura/Remito, seleccione la Orden de Compra previa para descontar el stock "A Recibir".'
        }),
        ('Identificación', {
            'fields': (
                ('punto_venta', 'numero'),
                'letra'
            )
        }),
        ('Totales', {
            'classes': ('show',),
            'fields': ('subtotal', 'impuestos_desglosados', 'total', 'saldo_pendiente')
        })
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
        html = "<ul>"
        for nombre, monto in obj.impuestos.items():
            html += f"<li><strong>{nombre}:</strong> ${float(monto):,.2f}</li>"
        html += "</ul>"
        return format_html(html)

    @admin.display(description='Número')
    def numero_completo_display(self, obj):
        return f"{obj.letra} {obj.punto_venta:05d}-{obj.numero:08d}"

    @admin.display(description="Saldo", ordering='saldo_pendiente')
    def saldo_visual(self, obj):
        color = "red" if obj.saldo_pendiente > 0 else "green"
        return format_html('<span style="color: {}; font-weight: bold;">${}</span>', color, obj.saldo_pendiente)

    # Filtro inteligente para el buscador de la Orden de Pago
    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if 'app_label' in request.GET and request.GET['model_name'] == 'ordenpagoimputacion':
            queryset = queryset.filter(estado=ComprobanteCompra.Estado.CONFIRMADO, saldo_pendiente__gt=0)
        return queryset, use_distinct

    # Filtro inteligente para el campo comprobante_origen
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Si estamos editando un comprobante existente
        if obj and 'comprobante_origen' in form.base_fields:
            # Filtramos para que solo aparezcan comprobantes del MISMO PROVEEDOR
            # y que no sea el mismo comprobante que estamos editando.
            form.base_fields['comprobante_origen'].queryset = ComprobanteCompra.objects.filter(
                proveedor=obj.proveedor
            ).exclude(pk=obj.pk)
        return form

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        obj = form.instance
        if not obj.pk: return
        moneda_base = 'ARS'
        if obj.items.exists():
            primer_item = obj.items.first()
            if primer_item.precio_costo_unitario_moneda:
                moneda_base = primer_item.precio_costo_unitario_moneda.simbolo

        subtotal_calculado = sum(item.subtotal for item in obj.items.all())
        subtotal_money = Money(subtotal_calculado.amount, moneda_base)
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(obj, 'compra')
        obj.impuestos = {k: str(v) for k, v in desglose_impuestos.items()}
        total_impuestos = sum(desglose_impuestos.values())
        impuestos_money = Money(total_impuestos, moneda_base)
        total_money = subtotal_money + impuestos_money

        obj.subtotal = subtotal_money.amount
        obj.total = total_money.amount
        obj.saldo_pendiente = obj.total
        obj.save()


class ItemListaPreciosProveedorInline(admin.TabularInline):
    model = ItemListaPreciosProveedor
    form = ItemListaPreciosProveedorForm
    extra = 0
    autocomplete_fields = ['articulo', 'unidad_medida_compra']
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


# ========================================================
#  ADMINISTRACIÓN DE ÓRDENES DE PAGO (TESORERÍA)
# ========================================================

class OrdenPagoImputacionInline(admin.TabularInline):
    model = OrdenPagoImputacion
    extra = 1
    autocomplete_fields = ['comprobante']
    fields = ('comprobante', 'total_original_display', 'monto_imputado')
    readonly_fields = ('total_original_display',)

    def total_original_display(self, obj):
        if obj.comprobante:
            return f"${obj.comprobante.total:,.2f}"
        return "-"
    total_original_display.short_description = "Monto Original Factura"

class OrdenPagoValorInline(admin.TabularInline):
    model = OrdenPagoValor
    extra = 1
    autocomplete_fields = ['origen', 'cheque_tercero']
    # === AQUÍ ESTÁ EL CAMBIO CLAVE: Agregamos los campos nuevos ===
    fields = (
        ('tipo', 'monto', 'origen'),
        ('cheque_tercero', 'referencia'),
        ('cheque_propio_nro', 'es_echeq', 'fecha_pago_cheque')
    )

@admin.register(OrdenPago)
class OrdenPagoAdmin(admin.ModelAdmin):
    list_display = ('numero', 'proveedor', 'fecha', 'monto_total', 'estado', 'finanzas_aplicadas')
    list_filter = ('estado', 'fecha')
    search_fields = ('numero', 'proveedor__entidad__razon_social')
    autocomplete_fields = ['proveedor', 'serie']
    inlines = [OrdenPagoImputacionInline, OrdenPagoValorInline]
    readonly_fields = ('numero', 'finanzas_aplicadas', 'monto_total', 'creado_por')

    fieldsets = (
        ('Encabezado', {'fields': ('serie', 'fecha', 'proveedor', 'estado')}),
        ('Auditoría', {'fields': ('creado_por', 'finanzas_aplicadas', 'observaciones')})
    )

    class Media:
        js = ('admin/js/orden_pago_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('api/get-comprobante-info/<int:pk>/',
                 self.admin_site.admin_view(get_comprobante_info),
                 name='compras_get_comprobante_info'),
        ]
        return custom_urls + urls

    def save_model(self, request, obj, form, change):
        if not obj.pk: obj.creado_por = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if form.instance.pk:
            total = sum(v.monto for v in form.instance.valores.all())
            form.instance.monto_total = total
            form.instance.save()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if obj.estado == OrdenPago.Estado.CONFIRMADO and not obj.finanzas_aplicadas:
            try:
                obj.aplicar_finanzas()
                self.message_user(request, "✅ Orden de Pago aplicada financieramente con éxito.")
            except Exception as e:
                obj.estado = OrdenPago.Estado.BORRADOR
                obj.save()
                self.message_user(request, f"❌ Error aplicando finanzas: {e}", level=messages.ERROR)

        # Manejo de anulación
        if obj.estado == OrdenPago.Estado.ANULADO and obj.finanzas_aplicadas:
             obj.revertir_finanzas()
             self.message_user(request, "⚠️ Orden de Pago ANULADA. Saldos revertidos.")