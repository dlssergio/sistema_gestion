# finanzas/admin.py (VERSIÓN FINAL DEFINITIVA)

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from .models import TipoValor, Banco, CuentaFondo, Cheque, MovimientoFondo, CentroCosto, TransferenciaInterna


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

    # CORRECCIÓN: Formateamos el número a texto ANTES de pasarlo al HTML
    @admin.display(description="Saldo Actual")
    def saldo_actual_fmt(self, obj):
        color = "red" if obj.saldo_monto < 0 else "green"
        # Convertimos a string con formato: 1,234.56
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

    # Acción personalizada: Depositar Cheques (Punto 1)
    @admin.action(description="🏦 Depositar Cheques Seleccionados")
    def depositar_cheques(self, request, queryset):
        # 1. Validar que solo sean cheques en cartera
        cheques_validos = queryset.filter(estado=Cheque.Estado.EN_CARTERA)
        cheques_invalidos = queryset.exclude(estado=Cheque.Estado.EN_CARTERA)

        if cheques_invalidos.exists():
            self.message_user(request, "⚠️ Se omitieron cheques que NO están en cartera.", level=messages.WARNING)
            if not cheques_validos.exists(): return

        # 2. Procesar Formulario (POST con 'apply')
        if 'apply' in request.POST:
            cuenta_id = request.POST.get('cuenta_destino')
            fecha = request.POST.get('fecha_deposito')

            try:
                cuenta = CuentaFondo.objects.get(pk=cuenta_id)

                with transaction.atomic():
                    count = 0
                    total = 0
                    for cheque in cheques_validos:
                        # a. Actualizar Cheque
                        cheque.estado = Cheque.Estado.DEPOSITADO
                        cheque.save()

                        # b. Crear Movimiento en el Banco (Ingreso)
                        MovimientoFondo.objects.create(
                            fecha=fecha,
                            cuenta=cuenta,
                            tipo_movimiento=MovimientoFondo.TipoMov.INGRESO,
                            tipo_valor=None,  # Opcional: podrías buscar el TipoValor 'Cheque'
                            monto_ingreso=cheque.monto,
                            concepto=f"Depósito Cheque #{cheque.numero} ({cheque.banco})",
                            usuario=request.user,
                            cheque=cheque
                        )

                        # c. Actualizar Saldo Banco
                        cuenta.saldo_monto += cheque.monto
                        cuenta.save()

                        count += 1
                        total += cheque.monto

                self.message_user(request, f"✅ Se depositaron {count} cheques. Total acreditado: ${total:,.2f}")
                return redirect(request.get_full_path())

            except Exception as e:
                self.message_user(request, f"Error: {e}", level=messages.ERROR)

        # 3. Renderizar Formulario Intermedio (GET)
        cuentas_banco = CuentaFondo.objects.filter(tipo=CuentaFondo.Tipo.BANCO, activa=True)
        return render(request, 'admin/finanzas/cheque/depositar.html', context={
            'queryset': cheques_validos,
            'cuentas_banco': cuentas_banco
        })

    fieldsets = (
        ('Identificación', {
            'fields': (
                ('numero', 'referencia_bancaria'),
                ('tipo_cheque', 'origen'),
                'estado'
            )
        }),
        ('Valores y Fechas', {
            'fields': (
                ('monto', 'moneda'),
                'banco',
                ('fecha_emision', 'fecha_pago')
            )
        }),
        ('Datos del Tercero', {
            'fields': (
                ('cuit_librador', 'nombre_librador'),
                'observaciones'
            )
        }),
    )


@admin.register(MovimientoFondo)
class MovimientoFondoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'cuenta', 'concepto_corto', 'ingreso_fmt', 'egreso_fmt', 'conciliado', 'centro_costo')
    list_filter = ('cuenta', 'tipo_movimiento', 'conciliado', 'fecha')
    search_fields = ('concepto', 'monto_ingreso', 'monto_egreso')
    autocomplete_fields = ['cuenta', 'tipo_valor', 'cheque', 'centro_costo', 'usuario']
    actions = ['marcar_conciliado', 'desmarcar_conciliado']

    def concepto_corto(self, obj):
        return (obj.concepto[:40] + '..') if len(obj.concepto) > 40 else obj.concepto

    # CORRECCIÓN AQUÍ TAMBIÉN: Formateo previo
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

    ingreso_fmt.short_description = "Ingreso"
    egreso_fmt.short_description = "Egreso"

    fieldsets = (
        ('Detalle del Movimiento', {
            'fields': (
                ('fecha', 'usuario'),
                'cuenta',
                ('tipo_movimiento', 'tipo_valor'),
                ('monto_ingreso', 'monto_egreso'),
                'concepto'
            )
        }),
        ('Clasificación', {
            'fields': ('centro_costo', 'cheque')
        }),
        ('Conciliación Bancaria', {
            'fields': ('conciliado', 'fecha_conciliacion'),
            'classes': ('collapse',)  # Oculto por defecto para no molestar
        }),
    )

    # Asignar usuario automáticamente
    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.usuario_id:
            obj.usuario = request.user
        super().save_model(request, obj, form, change)

    # Acciones de Conciliación (Punto 3)
    @admin.action(description="✅ Marcar como Conciliado")
    def marcar_conciliado(self, request, queryset):
        updated = queryset.update(conciliado=True, fecha_conciliacion=timezone.now())
        self.message_user(request, f"{updated} movimientos conciliados.")

    @admin.action(description="❌ Desmarcar Conciliación")
    def desmarcar_conciliado(self, request, queryset):
        updated = queryset.update(conciliado=False, fecha_conciliacion=None)
        self.message_user(request, f"{updated} movimientos desmarcados.")


@admin.register(TransferenciaInterna)
class TransferenciaInternaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'origen', 'destino', 'monto', 'estado', 'finanzas_aplicadas')
    list_filter = ('estado', 'fecha', 'origen', 'destino')
    autocomplete_fields = ['origen', 'destino']
    readonly_fields = ('finanzas_aplicadas', 'creado_por')

    fieldsets = (
        ('Detalles', {
            'fields': ('fecha', 'estado', 'creado_por')
        }),
        ('Movimiento', {
            'fields': ('origen', 'destino', 'monto')
        }),
        ('Referencias', {
            'fields': ('concepto', 'referencia')
        })
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk: obj.creado_por = request.user
        super().save_model(request, obj, form, change)
