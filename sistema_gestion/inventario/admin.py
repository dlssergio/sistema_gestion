# inventario/admin.py (VERSIÓN DEFINITIVA Y CORREGIDA)

import json
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.utils.html import format_html
from djmoney.forms.fields import MoneyField
from djmoney.money import Money
from auditlog.registry import auditlog
from django.urls import path, reverse

from .models import (
    Articulo, Marca, Rubro, Deposito, StockArticulo,
    ConversionUnidadMedida, ProveedorArticulo,
    MovimientoStock, ItemMovimientoStock, HistoricoMovimientos,
    # Nuevos modelos Enterprise
    TipoStock, BalanceStock, MovimientoStockLedger,
    # Nuevos modelos Transferencia
    TransferenciaInterna, ItemTransferencia,
    # Nuevos modelos Ajustes
    MotivoAjuste, AjusteStock, ItemAjusteStock
)
from .services import TransferenciaService, AjusteService  # Importamos los servicios
from parametros.models import Moneda, Impuesto, CategoriaImpositiva
from .views import kardex_articulo_view, reporte_valorizacion_view


# --- CLASES AUXILIARES ---
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


# --- ADMINS MAESTROS ---

@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    search_fields = ['nombre']


@admin.register(Rubro)
class RubroAdmin(admin.ModelAdmin):
    search_fields = ['nombre']


@admin.register(Deposito)
class DepositoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'direccion', 'es_principal')
    search_fields = ['nombre']


# --- INLINES ---

class ProveedorArticuloInline(admin.TabularInline):
    model = ProveedorArticulo
    extra = 1
    fields = ('proveedor', 'es_fuente_de_verdad', 'fecha_relacion')
    readonly_fields = ('fecha_relacion',)
    autocomplete_fields = ['proveedor']


class StockArticuloInline(admin.TabularInline):
    """
    Muestra el stock Legacy (Compatible) dentro de la ficha del artículo.
    """
    model = StockArticulo
    extra = 0
    fields = ('deposito', 'cantidad_real', 'cantidad_comprometida', 'cantidad_disponible')
    readonly_fields = ('cantidad_disponible',)  # Es calculado, solo lectura
    can_delete = False

    def cantidad_disponible(self, obj):
        return obj.cantidad_disponible


class ConversionUnidadMedidaInline(admin.TabularInline):
    model = ConversionUnidadMedida
    extra = 1
    autocomplete_fields = ['unidad_externa']


# --- ARTÍCULO ---

@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    change_form_template = 'admin/inventario/articulo/change_form.html'

    list_display = (
        'cod_articulo', 'descripcion', 'marca',
        'stock_fisico_total', 'stock_comprometido_total',
        'display_precio_venta', 'esta_activo',
        'get_proveedor_fuente_costo',
        'boton_kardex'
    )
    list_filter = ('esta_activo', 'marca', 'rubro', 'perfil')
    search_fields = ('cod_articulo', 'descripcion', 'ean')

    autocomplete_fields = [
        'marca', 'rubro', 'grupo_unidades', 'unidad_medida_stock', 'unidad_medida_venta',
        'categoria_impositiva', 'precio_costo_moneda', 'precio_venta_moneda'
    ]
    filter_horizontal = ('impuestos',)
    readonly_fields = ('precio_final_form',)

    fieldsets = (
        ('Información Principal',
         {'fields': (
             'cod_articulo', 'ean', 'qr', 'descripcion', 'foto', 'ubicacion', 'perfil', 'marca', 'rubro',
             'esta_activo')}),
        ('Precios, Costos e Impuestos',
         {'fields': (
             ('precio_costo_monto', 'precio_costo_moneda'),
             'utilidad',
             ('precio_venta_monto', 'precio_venta_moneda'),
             'categoria_impositiva', 'impuestos')}),
        ('Precio Final (Calculado)', {'fields': ('precio_final_form',)}),
        ('Gestión de Inventario y Unidades',
         {'fields': (
             ('administra_stock', 'permite_stock_negativo'),
             'grupo_unidades',
             'unidad_medida_stock',
             'unidad_medida_venta'
         )}),
        ('Observaciones', {'classes': ('collapse',), 'fields': ('observaciones', 'nota')}),
    )
    inlines = [ProveedorArticuloInline, StockArticuloInline, ConversionUnidadMedidaInline]

    class Media:
        js = ('admin/js/articulo_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:articulo_id>/kardex/',
                self.admin_site.admin_view(kardex_articulo_view),
                name='inventario_articulo_kardex',
            ),
        ]
        return custom_urls + urls

    @admin.display(description="Kardex")
    def boton_kardex(self, obj):
        if not obj.pk: return "-"
        url = reverse('admin:inventario_articulo_kardex', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="background-color: #17a2b8; color: white; padding: 3px 10px;" title="Ver Movimientos">📜 Ver</a>',
            url
        )

    @admin.display(description="Precio Venta", ordering='precio_venta_monto')
    def display_precio_venta(self, obj):
        return obj.precio_venta

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        proveedor_id = request.GET.get('proveedor_id')
        if proveedor_id:
            queryset = queryset.filter(proveedores__pk=proveedor_id)
        return queryset, use_distinct

    # --- MÉTODOS PARA VER STOCK EN LA LISTA ---
    @admin.display(description="Físico")
    def stock_fisico_total(self, obj):
        if not obj.administra_stock: return "-"
        return sum(s.cantidad_real for s in obj.stocks.all())

    @admin.display(description="Reservado")
    def stock_comprometido_total(self, obj):
        if not obj.administra_stock: return "-"
        val = sum(s.cantidad_comprometida for s in obj.stocks.all())
        return f"{val}" if val > 0 else "-"

    @admin.display(description="Fuente de Costo Base")
    def get_proveedor_fuente_costo(self, obj):
        prov = obj.proveedor_actualiza_precio
        return prov.entidad.razon_social if prov else "N/A"

    def add_extra_context(self, request, extra_context=None):
        extra_context = extra_context or {}
        cotizaciones = {str(m.id): float(m.cotizacion) for m in Moneda.objects.all()}
        extra_context['cotizaciones_json'] = json.dumps(cotizaciones)
        tasas_impuestos = list(Impuesto.objects.values('id', 'tasa'))
        for t in tasas_impuestos:
            t['tasa'] = float(t['tasa'])
        extra_context['tasas_impuestos_json'] = json.dumps(tasas_impuestos)
        return extra_context

    def add_view(self, request, form_url='', extra_context=None):
        return super().add_view(request, form_url, extra_context=self.add_extra_context(request, extra_context))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return super().change_view(request, object_id, form_url,
                                   extra_context=self.add_extra_context(request, extra_context))

    @admin.display(description="Precio Final con Impuestos")
    def precio_final_form(self, obj):
        return "Calculado automáticamente..."


# --- HISTÓRICO LEGACY (AUDITORÍA VIEJA) ---
@admin.register(HistoricoMovimientos)
class HistoricoMovimientosAdmin(admin.ModelAdmin):
    list_display = ('fecha_fmt', 'articulo', 'deposito', 'tipo_stock', 'operacion', 'cantidad', 'referencia', 'usuario')
    list_filter = (
        'tipo_stock',
        'operacion',
        'deposito',
        'fecha',
        'usuario'
    )
    search_fields = ('articulo__descripcion', 'articulo__cod_articulo', 'referencia')
    date_hierarchy = 'fecha'

    @admin.display(description="Fecha")
    def fecha_fmt(self, obj):
        return obj.fecha.strftime("%d/%m/%Y %H:%M")

    def has_add_permission(self, request): return False

    def has_delete_permission(self, request, obj=None): return False

    def has_change_permission(self, request, obj=None): return False


# --- MOVIMIENTOS INTERNOS (LEGACY) ---

class ItemMovimientoStockInline(admin.TabularInline):
    model = ItemMovimientoStock
    extra = 1
    autocomplete_fields = ['articulo']


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'serie', 'numero', 'tipo_movimiento', 'estado', 'origen_destino_display')
    list_filter = ('estado', 'tipo_movimiento', 'fecha', 'serie')
    search_fields = ('numero', 'observaciones')
    inlines = [ItemMovimientoStockInline]
    autocomplete_fields = ['serie', 'deposito_origen', 'deposito_destino']

    readonly_fields = ('numero',)

    fieldsets = (
        ('Cabecera', {
            'fields': ('fecha', 'serie', 'numero', 'estado')
        }),
        ('Configuración de Movimiento', {
            'fields': ('tipo_movimiento', ('deposito_origen', 'deposito_destino'))
        }),
        ('Detalles', {
            'fields': ('observaciones',)
        }),
    )

    @admin.display(description="Origen -> Destino")
    def origen_destino_display(self, obj):
        origen = obj.deposito_origen.nombre if obj.deposito_origen else "N/A"
        destino = obj.deposito_destino.nombre if obj.deposito_destino else "N/A"

        if obj.tipo_movimiento == MovimientoStock.Tipo.TRANSFERENCIA:
            return f"{origen} -> {destino}"
        elif obj.tipo_movimiento == MovimientoStock.Tipo.ENTRADA:
            return f"Entra a: {destino}"
        else:
            return f"Sale de: {origen}"

    def save_model(self, request, obj, form, change):
        if not obj.creado_por:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        # Importante: El MovimientoStock ahora usa StockManager internamente
        form.instance.aplicar_stock()


# =========================================================
#  NUEVA GESTIÓN DE TRANSFERENCIAS (ENTERPRISE LOGISTICS)
# =========================================================

class ItemTransferenciaInline(admin.TabularInline):
    model = ItemTransferencia
    extra = 1
    autocomplete_fields = ['articulo']


@admin.register(TransferenciaInterna)
class TransferenciaInternaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'origen', 'destino', 'estado_visual', 'items_count')
    list_filter = ('estado', 'origen', 'destino')
    inlines = [ItemTransferenciaInline]
    autocomplete_fields = ['origen', 'destino']

    actions = ['accion_despachar', 'accion_recibir']

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.estado != 'BR':
            return ['origen', 'destino', 'fecha']
        return []

    @admin.display(description="Estado")
    def estado_visual(self, obj):
        colors = {
            'BR': 'gray',
            'TR': 'orange',  # En tránsito
            'CP': 'green',  # Completada
            'AN': 'red'
        }
        color = colors.get(obj.estado, 'black')
        label = obj.get_estado_display()
        return format_html(f'<span style="color: {color}; font-weight: bold;">{label}</span>')

    @admin.display(description="Items")
    def items_count(self, obj):
        return obj.items.count()

    @admin.action(description="🚚 DESPACHAR Mercadería (Salida)")
    def accion_despachar(self, request, queryset):
        ok = 0
        errores = 0
        for trf in queryset:
            try:
                TransferenciaService.despachar_transferencia(trf)
                ok += 1
            except Exception as e:
                self.message_user(request, f"Error en TRF #{trf.pk}: {e}", level=messages.ERROR)
                errores += 1

        if ok: self.message_user(request, f"✅ {ok} transferencias despachadas (Stock en tránsito).")

    @admin.action(description="📥 RECIBIR Mercadería (Entrada)")
    def accion_recibir(self, request, queryset):
        ok = 0
        errores = 0
        for trf in queryset:
            try:
                TransferenciaService.recibir_transferencia(trf)
                ok += 1
            except Exception as e:
                self.message_user(request, f"Error en TRF #{trf.pk}: {e}", level=messages.ERROR)
                errores += 1

        if ok: self.message_user(request, f"✅ {ok} transferencias recibidas e ingresadas a stock.")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)


# =========================================================
#  AJUSTES MANUALES DE STOCK (EXCEPCIONES)
# =========================================================

@admin.register(MotivoAjuste)
class MotivoAjusteAdmin(admin.ModelAdmin):
    search_fields = ['nombre']


class ItemAjusteStockInline(admin.TabularInline):
    model = ItemAjusteStock
    extra = 1
    autocomplete_fields = ['articulo']


@admin.register(AjusteStock)
class AjusteStockAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'motivo', 'deposito', 'estado_visual', 'creado_por')
    list_filter = ('estado', 'motivo', 'deposito', 'fecha')
    search_fields = ('observaciones',)
    inlines = [ItemAjusteStockInline]
    autocomplete_fields = ['deposito', 'motivo']
    actions = ['accion_confirmar']

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.estado == 'CN':
            return ['fecha', 'deposito', 'motivo', 'observaciones']
        return []

    @admin.display(description="Estado")
    def estado_visual(self, obj):
        colors = {'BR': 'gray', 'CN': 'green', 'AN': 'red'}
        color = colors.get(obj.estado, 'black')
        label = obj.get_estado_display()
        return format_html(f'<span style="color: {color}; font-weight: bold;">{label}</span>')

    @admin.action(description="✅ CONFIRMAR Ajuste de Stock")
    def accion_confirmar(self, request, queryset):
        ok = 0
        errores = 0
        for ajuste in queryset:
            try:
                AjusteService.confirmar_ajuste(ajuste)
                ok += 1
            except Exception as e:
                self.message_user(request, f"Error en Ajuste #{ajuste.pk}: {e}", level=messages.ERROR)
                errores += 1

        if ok: self.message_user(request, f"✅ {ok} ajustes confirmados correctamente.")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)


# =========================================================
#  NUEVA GESTIÓN ENTERPRISE DE STOCK (CORE)
# =========================================================

@admin.register(TipoStock)
class TipoStockAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'es_fisico', 'es_vendible', 'es_reservado')
    list_editable = ('es_fisico', 'es_vendible', 'es_reservado')
    search_fields = ('nombre', 'codigo')
    help_text = "Defina el comportamiento matemático del stock."


@admin.register(BalanceStock)
class BalanceStockAdmin(admin.ModelAdmin):
    """
    Vista técnica para ver el saldo desagregado (Snapshot).
    """
    list_display = ('articulo', 'deposito', 'tipo_stock', 'cantidad', 'ultima_actualizacion')
    list_filter = ('tipo_stock', 'deposito', 'articulo__rubro')
    search_fields = ('articulo__cod_articulo', 'articulo__descripcion')

    # Solo lectura: El balance se toca SOLO via StockManager, no a mano.
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('reporte-valorizacion/', self.admin_site.admin_view(reporte_valorizacion_view),
                 name='inventario_reporte_valorizacion'),
        ]
        return custom_urls + urls

    change_list_template = "admin/inventario/balance_stock/change_list_custom.html"


@admin.register(MovimientoStockLedger)
class MovimientoStockLedgerAdmin(admin.ModelAdmin):
    """
    Auditoría Forense del Ledger. Fuente de la verdad inmutable.
    """
    list_display = ('fecha_fmt', 'articulo', 'cantidad', 'tipo_stock', 'origen_sistema', 'origen_referencia', 'usuario')
    list_filter = ('tipo_stock', 'origen_sistema', 'fecha_movimiento')
    search_fields = ('articulo__cod_articulo', 'origen_referencia')
    date_hierarchy = 'fecha_movimiento'

    @admin.display(description="Fecha")
    def fecha_fmt(self, obj): return obj.fecha_movimiento.strftime('%d/%m/%Y %H:%M')

    # El Ledger es SAGRADO e INMUTABLE. Nadie lo toca manualmente.
    def has_add_permission(self, request): return False

    def has_change_permission(self, request, obj=None): return False

    def has_delete_permission(self, request, obj=None): return False


@admin.register(StockArticulo)
class StockArticuloAdmin(admin.ModelAdmin):
    """
    Vista de la Tabla Legacy (Para verificar compatibilidad).
    """
    list_display = ('articulo', 'deposito', 'cantidad_real', 'cantidad_comprometida', 'cantidad_disponible')
    list_filter = ('deposito',)
    search_fields = ('articulo__descripcion', 'articulo__cod_articulo')
    # Solo lectura en Admin para forzar uso de Movimientos
    list_editable = []


auditlog.register(Articulo)
auditlog.register(Marca)