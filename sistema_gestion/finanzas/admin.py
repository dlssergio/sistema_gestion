# finanzas/admin.py (VERSIÓN FINAL COMPLETA CON URL EXPORTACIÓN)

from django.contrib import admin
from django.urls import reverse, path
from django.utils.html import format_html
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from .models import (
    TipoValor, Banco, CuentaFondo, Cheque, MovimientoFondo,
    CentroCosto, TransferenciaInterna,
    RegimenRetencion, CertificadoRetencion,
    Tarjeta, CuponTarjeta, PlanTarjeta, LiquidacionTarjeta,
    PlanCuota
)
from .forms import LiquidacionTarjetaForm
from .views import reporte_cashflow_view, libro_iva_view, exportar_libro_iva_view


@admin.register(CentroCosto)
class CentroCostoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'activo')
    search_fields = ('nombre', 'codigo')
    list_filter = ('activo',)


@admin.register(TipoValor)
class TipoValorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'es_cheque', 'es_tarjeta', 'es_retencion', 'requiere_banco')
    list_filter = ('es_cheque', 'es_tarjeta')
    search_fields = ('nombre',)


@admin.register(Banco)
class BancoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo_bcra')
    search_fields = ('nombre', 'codigo_bcra')


@admin.register(CuentaFondo)
class CuentaFondoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'moneda', 'saldo_actual_fmt', 'banco', 'activa')
    list_filter = ('tipo', 'moneda', 'activa')
    search_fields = ('nombre', 'cbu', 'alias')
    autocomplete_fields = ['banco', 'moneda']

    @admin.display(description="Saldo Actual")
    def saldo_actual_fmt(self, obj):
        color = "red" if obj.saldo_monto < 0 else "green"
        # Formateamos antes de pasar al HTML
        valor = f"{obj.saldo_monto:,.2f}"
        return format_html(
            '<strong style="color: {}; font-size: 1.1em;">{} {}</strong>',
            color, obj.moneda.simbolo, valor
        )


@admin.register(Cheque)
class ChequeAdmin(admin.ModelAdmin):
    list_display = ('numero', 'tipo_cheque_display', 'banco', 'monto', 'fecha_pago', 'estado', 'origen')
    list_filter = ('estado', 'origen', 'tipo_cheque', 'fecha_pago', 'banco')
    search_fields = ('numero', 'referencia_bancaria', 'cuit_librador', 'nombre_librador')
    autocomplete_fields = ['banco', 'moneda']
    actions = ['depositar_cheques']

    @admin.display(description="Formato")
    def tipo_cheque_display(self, obj):
        icon = "📱" if obj.tipo_cheque == 'ECH' else "📄"
        return f"{icon} {obj.get_tipo_cheque_display()}"

    @admin.action(description="🏦 Depositar Cheques Seleccionados")
    def depositar_cheques(self, request, queryset):
        cheques_validos = queryset.filter(estado=Cheque.Estado.EN_CARTERA)
        cheques_invalidos = queryset.exclude(estado=Cheque.Estado.EN_CARTERA)

        if cheques_invalidos.exists():
            self.message_user(request, "⚠️ Se omitieron cheques que NO están en cartera.", level=messages.WARNING)
            if not cheques_validos.exists(): return

        if 'apply' in request.POST:
            cuenta_id = request.POST.get('cuenta_destino')
            fecha = request.POST.get('fecha_deposito')

            try:
                cuenta = CuentaFondo.objects.get(pk=cuenta_id)
                with transaction.atomic():
                    count = 0
                    total = 0
                    for cheque in cheques_validos:
                        cheque.estado = Cheque.Estado.DEPOSITADO
                        cheque.save()

                        MovimientoFondo.objects.create(
                            fecha=fecha,
                            cuenta=cuenta,
                            tipo_movimiento=MovimientoFondo.TipoMov.INGRESO,
                            tipo_valor=None,
                            monto_ingreso=cheque.monto,
                            concepto=f"Depósito Cheque #{cheque.numero} ({cheque.banco})",
                            usuario=request.user,
                            cheque=cheque
                        )
                        cuenta.saldo_monto += cheque.monto
                        cuenta.save()
                        count += 1
                        total += cheque.monto

                self.message_user(request, f"✅ Se depositaron {count} cheques. Total acreditado: ${total:,.2f}")
                return redirect(request.get_full_path())

            except Exception as e:
                self.message_user(request, f"Error: {e}", level=messages.ERROR)

        cuentas_banco = CuentaFondo.objects.filter(tipo=CuentaFondo.Tipo.BANCO, activa=True)
        return render(request, 'admin/finanzas/cheque/depositar.html', context={
            'queryset': cheques_validos,
            'cuentas_banco': cuentas_banco
        })

    fieldsets = (
        ('Identificación', {'fields': (('numero', 'referencia_bancaria'), ('tipo_cheque', 'origen'), 'estado')}),
        ('Valores y Fechas', {'fields': (('monto', 'moneda'), 'banco', ('fecha_emision', 'fecha_pago'))}),
        ('Datos del Tercero', {'fields': (('cuit_librador', 'nombre_librador'), 'observaciones')}),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [path('reporte-cashflow/', self.admin_site.admin_view(reporte_cashflow_view),
                            name='finanzas_reporte_cashflow')]
        return custom_urls + urls

    change_list_template = "admin/finanzas/cheque/change_list_custom.html"


@admin.register(MovimientoFondo)
class MovimientoFondoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'cuenta', 'concepto_corto', 'ingreso_fmt', 'egreso_fmt', 'conciliado', 'centro_costo')
    list_filter = ('cuenta', 'tipo_movimiento', 'conciliado', 'fecha')
    search_fields = ('concepto', 'monto_ingreso', 'monto_egreso')
    autocomplete_fields = ['cuenta', 'tipo_valor', 'cheque', 'centro_costo', 'usuario']
    actions = ['marcar_conciliado', 'desmarcar_conciliado']
    ordering = ('-fecha', '-id')

    def concepto_corto(self, obj):
        return (obj.concepto[:40] + '..') if len(obj.concepto) > 40 else obj.concepto

    # --- CORRECCIÓN AQUÍ: Usar {} simple porque ya formateamos con f-string ---
    def ingreso_fmt(self, obj):
        if obj.monto_ingreso > 0:
            val = f"{obj.monto_ingreso:,.2f}"
            return format_html('<span style="color:green;">+${}</span>', val)
        return "-"

    def egreso_fmt(self, obj):
        if obj.monto_egreso > 0:
            val = f"{obj.monto_egreso:,.2f}"
            return format_html('<span style="color:red;">-${}</span>', val)
        return "-"

    # --------------------------------------------------------------------------

    ingreso_fmt.short_description = "Ingreso"
    egreso_fmt.short_description = "Egreso"

    fieldsets = (
        ('Detalle del Movimiento', {'fields': (
            ('fecha', 'usuario'), 'cuenta', ('tipo_movimiento', 'tipo_valor'), ('monto_ingreso', 'monto_egreso'),
            'concepto')}),
        ('Clasificación', {'fields': ('centro_costo', 'cheque', 'cupon')}),
        ('Conciliación Bancaria', {'fields': ('conciliado', 'fecha_conciliacion'), 'classes': ('collapse',)}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.usuario_id: obj.usuario = request.user
        es_nuevo = not obj.pk
        super().save_model(request, obj, form, change)

        if es_nuevo:
            cuenta = obj.cuenta
            saldo_ant = cuenta.saldo_monto
            if obj.tipo_movimiento == MovimientoFondo.TipoMov.INGRESO:
                cuenta.saldo_monto += obj.monto_ingreso
            elif obj.tipo_movimiento == MovimientoFondo.TipoMov.EGRESO:
                cuenta.saldo_monto -= obj.monto_egreso
            cuenta.save()
            self.message_user(request,
                              f"✅ Movimiento registrado. Saldo actualizado: ${saldo_ant:,.2f} -> ${cuenta.saldo_monto:,.2f}",
                              level=messages.SUCCESS)

    @admin.action(description="✅ Marcar como Conciliado")
    def marcar_conciliado(self, request, queryset):
        queryset.update(conciliado=True, fecha_conciliacion=timezone.now())
        self.message_user(request, "Movimientos conciliados.")

    @admin.action(description="❌ Desmarcar Conciliación")
    def desmarcar_conciliado(self, request, queryset):
        queryset.update(conciliado=False, fecha_conciliacion=None)
        self.message_user(request, "Movimientos desmarcados.")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('libro-iva/', self.admin_site.admin_view(libro_iva_view), name='finanzas_libro_iva'),
            path('libro-iva/exportar/', self.admin_site.admin_view(exportar_libro_iva_view),
                 name='finanzas_libro_iva_export'),  # <--- URL NUEVA
        ]
        return custom_urls + urls

    change_list_template = "admin/finanzas/movimientofondo/change_list_custom.html"


@admin.register(TransferenciaInterna)
class TransferenciaInternaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'origen', 'destino', 'monto', 'estado', 'finanzas_aplicadas')
    list_filter = ('estado', 'fecha', 'origen', 'destino')
    autocomplete_fields = ['origen', 'destino']
    readonly_fields = ('finanzas_aplicadas', 'creado_por')

    fieldsets = (
        ('Detalles', {'fields': ('fecha', 'estado', 'creado_por')}),
        ('Movimiento', {'fields': ('origen', 'destino', 'monto')}),
        ('Referencias', {'fields': ('concepto', 'referencia')})
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk: obj.creado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(RegimenRetencion)
class RegimenRetencionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'impuesto', 'codigo_afip', 'alicuota_inscripto', 'monto_no_imponible')
    list_filter = ('impuesto',)
    search_fields = ('nombre', 'codigo_afip')


@admin.register(CertificadoRetencion)
class CertificadoRetencionAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'numero', 'proveedor', 'regimen', 'importe_retenido')
    list_filter = ('regimen__impuesto', 'fecha', 'proveedor')
    search_fields = ('numero', 'proveedor__entidad__razon_social')
    readonly_fields = ('token_validacion',)


# --- GESTIÓN DE TARJETAS Y LIQUIDACIONES ---

@admin.register(Tarjeta)
class TarjetaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cuenta_contable')
    search_fields = ('nombre',)


class PlanCuotaInline(admin.TabularInline):
    model = PlanCuota
    extra = 1
    verbose_name = "Opción de Cuota"
    verbose_name_plural = "Tabla de Coeficientes e Intereses"
    fields = ('cuotas', 'coeficiente', 'tna')


@admin.register(PlanTarjeta)
class PlanTarjetaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tarjeta', 'activo')
    list_filter = ('tarjeta', 'activo')
    inlines = [PlanCuotaInline]


class CuponInline(admin.TabularInline):
    """
    Inline solo lectura para mostrar qué cupones quedaron asociados.
    """
    model = CuponTarjeta
    extra = 0
    fields = ('fecha_operacion', 'cupon', 'lote', 'monto', 'plan')
    readonly_fields = ('fecha_operacion', 'cupon', 'lote', 'monto', 'plan')
    can_delete = False

    def has_add_permission(self, request, obj=None): return False


@admin.register(LiquidacionTarjeta)
class LiquidacionTarjetaAdmin(admin.ModelAdmin):
    form = LiquidacionTarjetaForm

    list_display = ('fecha_liquidacion', 'tarjeta', 'numero_liquidacion', 'total_bruto', 'total_neto', 'procesada')
    list_filter = ('tarjeta', 'procesada')
    inlines = [CuponInline]

    fieldsets = (
        ('Encabezado', {'fields': ('fecha_liquidacion', 'numero_liquidacion', 'tarjeta', 'cuenta_banco')}),

        # --- SELECTOR DE CUPONES ---
        ('Selección de Cupones Pendientes', {
            'fields': ('cupones_pendientes',),
            'description': 'Seleccione los cupones de la izquierda para incluirlos en esta liquidación.'
        }),
        # -------------------------------------------

        ('Retenciones y Gastos',
         {'fields': (('comision', 'otros_gastos'), ('retencion_iva', 'retencion_iibb', 'retencion_ganancias'))}),
        ('Totales Calculados', {'fields': ('total_bruto', 'total_descuentos', 'total_neto', 'procesada')})
    )

    # Los totales son solo lectura porque se calculan solos
    readonly_fields = ('total_bruto', 'total_descuentos', 'total_neto', 'procesada')

    def save_model(self, request, obj, form, change):
        if not obj.pk: obj.creado_por = request.user
        super().save_model(request, obj, form, change)
        if not obj.procesada: obj.calcular_totales()

    actions = ['procesar_liquidacion_accion']

    @admin.action(description="⚡ Confirmar Liquidación")
    def procesar_liquidacion_accion(self, request, queryset):
        for liq in queryset:
            if liq.procesada:
                self.message_user(request, f"La liquidación {liq} ya estaba procesada.", level=messages.WARNING)
                continue
            try:
                # Recalcular por seguridad antes de confirmar
                liq.calcular_totales()
                liq.confirmar_liquidacion()
                self.message_user(request, f"Liquidación {liq} procesada. Neto: ${liq.total_neto:,.2f}",
                                  level=messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Error en {liq}: {e}", level=messages.ERROR)


@admin.register(CuponTarjeta)
class CuponTarjetaAdmin(admin.ModelAdmin):
    list_display = ('fecha_operacion', 'tarjeta', 'plan', 'cupon', 'monto', 'estado', 'liquidacion')
    list_filter = ('estado', 'tarjeta', 'liquidacion')
    search_fields = ('cupon', 'lote')
    date_hierarchy = 'fecha_operacion'

    actions = ['marcar_presentado', 'crear_liquidacion_masiva']

    @admin.action(description="Marcar como Presentados (Cierre Lote)")
    def marcar_presentado(self, request, queryset):
        queryset.update(estado=CuponTarjeta.Estado.PRESENTADO)
        self.message_user(request, "Cupones marcados como presentados.")

    @admin.action(description="📄 Crear Liquidación con Seleccionados")
    def crear_liquidacion_masiva(self, request, queryset):
        first = queryset.first()
        if queryset.filter(tarjeta__ne=first.tarjeta).exists():
            self.message_user(request, "Error: Seleccione cupones de la misma tarjeta.", level=messages.ERROR);
            return

        if queryset.filter(liquidacion__isnull=False).exists():
            self.message_user(request, "Error: Algunos cupones ya están liquidados.", level=messages.ERROR);
            return

        liq = LiquidacionTarjeta.objects.create(
            tarjeta=first.tarjeta,
            numero_liquidacion="BORRADOR-" + timezone.now().strftime("%H%M%S"),
            cuenta_banco=CuentaFondo.objects.filter(tipo=CuentaFondo.Tipo.BANCO).first(),
            creado_por=request.user
        )

        queryset.update(liquidacion=liq, estado=CuponTarjeta.Estado.PRESENTADO)
        liq.calcular_totales()

        self.message_user(request, f"Liquidación #{liq.pk} creada. Edítela para cargar gastos.")
        return redirect(reverse('admin:finanzas_liquidaciontarjeta_change', args=[liq.pk]))