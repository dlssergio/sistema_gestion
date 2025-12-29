# ventas/admin.py (FUSIONADO CORRECTAMENTE)

from auditlog.registry import auditlog
from django.contrib import admin
from django.urls import reverse, path
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from djmoney.money import Money
from .views import enviar_comprobante_por_email

from .models import (
    Cliente, ComprobanteVenta, ComprobanteVentaItem,
    PriceList, ProductPrice,
    Recibo, ReciboImputacion, ReciboValor,
    ComprobantePendienteCAE, DisenoImpresion
)
# Importamos todas las vistas necesarias
from .views import (
    get_precio_articulo, calcular_totales_api,
    get_precio_articulo_cliente, imprimir_comprobante_pdf,
    get_comprobante_venta_info
)
from .services import TaxCalculatorService
from .views import reporte_cuenta_corriente
from parametros.afip import AfipManager
from .admin_actions import generar_nota_credito


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('get_razon_social', 'get_cuit', 'editar_entidad_link', 'permite_cta_cte', 'boton_cta_cte')
    search_fields = ('entidad__razon_social', 'entidad__cuit')
    autocomplete_fields = ['price_list']
    actions = ['generar_recibo_cobranza']

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
        url = reverse('admin:entidades_entidad_add') + '?rol=cliente'
        return HttpResponseRedirect(url)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:cliente_pk>/cta-cte/',
                 self.admin_site.admin_view(reporte_cuenta_corriente),
                 name='ventas_cliente_ctacte'),
        ]
        return custom_urls + urls

    @admin.display(description="Cta. Cte.")
    def boton_cta_cte(self, obj):
        url = reverse('admin:ventas_cliente_ctacte', args=[obj.pk])
        return format_html('<a class="button" href="{}" target="_blank">📜 Ver Cta Cte</a>', url)

    @admin.action(description="💰 Generar Recibo de Cobro (Cargar Pendientes)")
    def generar_recibo_cobranza(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, "Por favor, seleccione solo un cliente para cobrar.", level=messages.WARNING)
            return

        cliente = queryset.first()
        # Buscamos comprobantes confirmados con saldo pendiente > 0
        pendientes = ComprobanteVenta.objects.filter(
            cliente=cliente,
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            saldo_pendiente__gt=0
        )

        if not pendientes.exists():
            self.message_user(request, f"El cliente {cliente} no tiene deuda pendiente.", level=messages.INFO)
            return

        # Creamos el recibo borrador (ahora Recibo permite serie null, así que no falla)
        recibo = Recibo.objects.create(
            cliente=cliente,
            fecha=timezone.now(),
            estado=Recibo.Estado.BORRADOR,
            creado_por=request.user
        )

        # Creamos las imputaciones automáticamente
        for comprobante in pendientes:
            ReciboImputacion.objects.create(
                recibo=recibo,
                comprobante=comprobante,
                monto_imputado=comprobante.saldo_pendiente
            )

        url = reverse('admin:ventas_recibo_change', args=[recibo.pk])
        self.message_user(request,
                          f"Recibo generado con {pendientes.count()} facturas pendientes. Cargue los valores de pago.")
        return redirect(url)


class ComprobanteVentaItemInline(admin.TabularInline):
    model = ComprobanteVentaItem
    extra = 1
    autocomplete_fields = ['articulo']
    readonly_fields = ('subtotal',)


@admin.register(ComprobanteVenta)
class ComprobanteVentaAdmin(admin.ModelAdmin):
    # --- Templates Personalizados ---
    change_form_template = "admin/ventas/comprobanteventa/change_form.html"
    change_list_template = "admin/ventas/comprobanteventa/change_list.html"  # Diagnóstico

    list_display = (
        'numero_completo', 'cliente', 'fecha', 'condicion_venta', 'total', 'saldo_visual', 'estado_pago_visual',
        'boton_imprimir_lista')
    list_filter = ('estado', 'cliente', 'fecha', 'condicion_venta', 'serie')
    search_fields = ('numero', 'cliente__entidad__razon_social')
    inlines = [ComprobanteVentaItemInline]
    autocomplete_fields = ['cliente', 'serie','comprobante_asociado']

    # Campos de solo lectura (incluyendo el botón de imprimir y campos AFIP)
    readonly_fields = (
        'tipo_comprobante', 'letra', 'punto_venta', 'numero',
        'subtotal', 'impuestos_desglosados', 'total',
        'saldo_pendiente', 'boton_imprimir_detalle',
        'cae', 'vto_cae', 'afip_resultado', 'afip_observaciones', 'afip_error'
    )

    # Organización visual del formulario
    fieldsets = (
        ('Encabezado de Venta', {
            'fields': (
                ('serie', 'fecha'),
                ('cliente', 'condicion_venta'),
                ('estado', 'boton_imprimir_detalle')
            )
        }),
        # --- NUEVA SECCIÓN DE VINCULACIÓN ---
        ('Referencias (Notas de Crédito/Débito)', {
            'fields': ('comprobante_asociado', 'referencia_externa'),
            'description': 'Obligatorio para Notas de Crédito/Débito. Seleccione la factura que se anula.',
            'classes': ('collapse',),  # Aparece cerrado por defecto para no molestar en ventas normales
        }),
        # ------------------------------------
        ('Detalles Técnicos', {
            'classes': ('collapse',),
            'fields': ('tipo_comprobante', 'letra', 'punto_venta', 'numero')
        }),
        ('Totales', {
            'classes': ('show',),
            'fields': ('subtotal', 'impuestos_desglosados', 'total', 'saldo_pendiente')
        }),
        ('Facturación Electrónica (AFIP)', {
            'classes': ('collapse',),
            'fields': (
                ('cae', 'vto_cae'),
                ('afip_resultado', 'afip_error'),
                'afip_observaciones'
            ),
            'description': 'Información oficial devuelta por los servidores de AFIP.'
        })
    )

    class Media:
        js = ('admin/js/comprobante_venta_admin.js',)

    # --- Configuración de URLs (API y Diagnóstico) ---
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('api/get-precio-articulo/<str:pk>/',
                 self.admin_site.admin_view(get_precio_articulo),
                 name='ventas_get_precio_articulo'),
            path('api/get-precio-articulo-cliente/<int:cliente_pk>/<str:articulo_pk>/',
                 self.admin_site.admin_view(get_precio_articulo_cliente),
                 name='ventas_get_precio_articulo_cliente'),
            path('api/calcular-totales/',
                 self.admin_site.admin_view(calcular_totales_api),
                 name='ventas_calcular_totales_api'),
            path('<int:pk>/imprimir/',
                 self.admin_site.admin_view(imprimir_comprobante_pdf),
                 name='ventas_comprobanteventa_imprimir'),
            path('api/get-comprobante-info/<int:pk>/',
                 self.admin_site.admin_view(get_comprobante_venta_info),
                 name='ventas_get_comprobante_info'),
            # URL DIAGNÓSTICO
            path('diagnostico-afip/',
                 self.admin_site.admin_view(self.vista_diagnostico),
                 name='ventas_diagnostico_afip'),
        ]
        return custom_urls + urls

    # --- Vista de Diagnóstico ---
    def vista_diagnostico(self, request):
        # 1. Instanciamos el Manager
        try:
            afip = AfipManager()
            # Ahora esta función devuelve TODO: Estado servidores + Lista de comprobantes (A, B, C, etc.)
            status = afip.consultar_estado_servicio()
        except Exception as e:
            # Si falla antes de conectar (ej: certificados no encontrados)
            status = {'online': False, 'error': f"Error de Inicialización: {str(e)}"}

        # 2. Preparamos el contexto para el HTML
        # Nota: Usamos la clave 'status' porque así lo espera la plantilla HTML nueva
        context = dict(
            self.admin_site.each_context(request),
            title="Diagnóstico de Conexión AFIP",
            status=status,
        )

        # 3. Renderizamos
        # Asegúrate de que tu archivo HTML esté en esta ruta exacta:
        return render(request, "admin/ventas/diagnostico_afip.html", context)

    # --- Acciones Personalizadas ---
    actions = ['solicitar_cae_afip', 'enviar_email_accion', generar_nota_credito]

    @admin.action(description="🌍 Solicitar CAE a AFIP (Manual)")
    def solicitar_cae_afip(self, request, queryset):
        manager = None
        try:
            manager = AfipManager()
            status = manager.consultar_estado_servicio()
            if not status['online']:
                self.message_user(request, "⚠️ Alerta: Los servicios de AFIP parecen estar caídos.",
                                  level=messages.WARNING)
        except Exception as e:
            self.message_user(request, f"Error de Configuración: {e}", level=messages.ERROR)
            return

        procesados = 0
        for comp in queryset:
            if comp.cae: continue

            try:
                if manager.emitir_comprobante(comp):
                    procesados += 1
            except Exception as e:
                self.message_user(request, f"Error en comprobante #{comp.numero}: {e}", level=messages.ERROR)

        if procesados > 0:
            self.message_user(request, f"✅ Se autorizaron {procesados} comprobantes.")

    @admin.action(description="📧 Enviar comprobante por Email al Cliente")
    def enviar_email_accion(self, request, queryset):
        enviados = 0
        errores = 0

        for comp in queryset:
            # Solo enviamos si tiene CAE (está aprobada)
            if not comp.cae:
                self.message_user(request, f"Omitido #{comp.numero}: No tiene CAE (no es oficial).",
                                  level=messages.WARNING)
                continue

            exito, mensaje = enviar_comprobante_por_email(comp, request)

            if exito:
                enviados += 1
            else:
                errores += 1
                self.message_user(request, f"Error #{comp.numero}: {mensaje}", level=messages.ERROR)

        if enviados > 0:
            self.message_user(request, f"✅ Se enviaron {enviados} correos con éxito.", level=messages.SUCCESS)

    # --- Lógica de Redirección Contado ---
    def response_add(self, request, obj, post_url_continue=None):
        return self._redirect_if_contado(request, obj) or super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        return self._redirect_if_contado(request, obj) or super().response_change(request, obj)

    def _redirect_if_contado(self, request, obj):
        # Verificamos si es Contado, Confirmado y tiene Saldo
        if obj.condicion_venta == ComprobanteVenta.CondicionVenta.CONTADO and \
                obj.saldo_pendiente > 0 and \
                obj.estado == ComprobanteVenta.Estado.CONFIRMADO:

            # --- CORRECCIÓN AQUÍ: DETECTAR SI ES DEVOLUCIÓN ---
            # Si el comprobante mueve stock positivo (es NC) o es tipo 'Devolucion'
            origen_fondos = Recibo.Origen.CONTADO  # Por defecto cobro

            # Si el signo de stock es positivo (1), es una Nota de Crédito/Devolución
            if obj.tipo_comprobante.signo_stock == 1:
                origen_fondos = Recibo.Origen.DEVOLUCION

            # Creamos el recibo con el origen correcto
            recibo = Recibo.objects.create(
                cliente=obj.cliente,
                fecha=obj.fecha,
                estado=Recibo.Estado.BORRADOR,
                creado_por=request.user,
                origen=origen_fondos  # <--- ASIGNAMOS EL ORIGEN DETECTADO
            )

            ReciboImputacion.objects.create(recibo=recibo, comprobante=obj, monto_imputado=obj.saldo_pendiente)

            msg_tipo = "DEVOLUCIÓN" if origen_fondos == Recibo.Origen.DEVOLUCION else "COBRO"
            self.message_user(request,
                              f"⚠️ Operación CONTADO registrada. Se generó un Recibo de {msg_tipo}. Por favor verifique los valores.",
                              level=messages.WARNING)

            return redirect(reverse('admin:ventas_recibo_change', args=[recibo.pk]))

        return None

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, extra_context)

    # --- Visuales ---
    @admin.display(description="Saldo", ordering='saldo_pendiente')
    def saldo_visual(self, obj):
        color = "red" if obj.saldo_pendiente > 0 else "green"
        return format_html('<span style="color: {}; font-weight: bold;">${}</span>', color, obj.saldo_pendiente)

    @admin.display(description="Estado")
    def estado_pago_visual(self, obj):
        estado = obj.estado_pago
        colors = {'PAGADO': 'green', 'IMPAGO': 'red', 'PARCIAL': 'orange'}
        return format_html(
            '<span style="background:{}; color:white; padding:3px 6px; border-radius:4px; font-size:10px;">{}</span>',
            colors.get(estado, 'gray'), estado)

    @admin.display(description="PDF")
    def boton_imprimir_lista(self, obj):
        if obj.pk:
            url = reverse('admin:ventas_comprobanteventa_imprimir', args=[obj.pk])
            return format_html('<a class="button" href="{}" target="_blank" title="Imprimir">🖨️</a>', url)
        return "-"

    @admin.display(description="Imprimir")
    def boton_imprimir_detalle(self, obj):
        if obj.pk:
            url = reverse('admin:ventas_comprobanteventa_imprimir', args=[obj.pk])
            return format_html('<a class="button" href="{}" target="_blank">🖨️ Generar PDF</a>', url)
        return "(Guarde para imprimir)"

    @admin.display(description='Impuestos')
    def impuestos_desglosados(self, obj):
        if not obj.impuestos: return "N/A"
        html = "<ul>"
        for nombre, monto in obj.impuestos.items():
            html += f"<li><strong>{nombre}:</strong> ${float(monto):,.2f}</li>"
        html += "</ul>"
        return format_html(html)

    # --- Filtros y Guardado ---
    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if 'app_label' in request.GET and request.GET['model_name'] == 'reciboimputacion':
            queryset = queryset.filter(estado=ComprobanteVenta.Estado.CONFIRMADO, saldo_pendiente__gt=0)
            cliente_id = request.GET.get('cliente_id')
            if cliente_id:
                queryset = queryset.filter(cliente_id=cliente_id)
        return queryset, use_distinct

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        obj = form.instance
        if not obj.pk: return

        moneda_base = 'ARS'
        if obj.items.exists() and obj.items.first().articulo.precio_venta_moneda:
            moneda_base = obj.items.first().articulo.precio_venta_moneda.simbolo

        subtotal_calculado = sum(item.subtotal for item in obj.items.all())
        if not isinstance(subtotal_calculado, Money):
            subtotal_calculado = Money(subtotal_calculado, moneda_base)

        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(obj, 'venta')
        obj.impuestos = {k: str(v) for k, v in desglose_impuestos.items()}

        total_impuestos_decimal = sum(desglose_impuestos.values())
        impuestos_money = Money(total_impuestos_decimal, moneda_base)
        total_money = subtotal_calculado + impuestos_money

        obj.subtotal = subtotal_calculado.amount
        obj.total = total_money.amount
        obj.saldo_pendiente = obj.total
        obj.save()


# --- RESTO DE LOS ADMINS (SIN CAMBIOS) ---

class ProductPriceInline(admin.TabularInline):
    model = ProductPrice
    extra = 1
    autocomplete_fields = ['product', 'price_moneda']
    fields = ('product', 'price_monto', 'price_moneda', 'min_quantity', 'max_quantity')
    readonly_fields = ('costo_referencia',)

    def costo_referencia(self, obj):
        if obj.product: return obj.product.precio_costo
        return "-"

    costo_referencia.short_description = "Costo Actual (Ref)"


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_default', 'valid_from', 'valid_until')
    search_fields = ('name', 'code')
    inlines = [ProductPriceInline]

    class Media: js = ('admin/js/price_list_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [path('api/get-precio-articulo/<str:pk>/', self.admin_site.admin_view(get_precio_articulo),
                            name='pricelist_get_precio_articulo')]
        return custom_urls + urls


@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = ('product', 'price_list', 'price', 'min_quantity')
    list_filter = ('price_list', 'product__rubro', 'product__marca')
    search_fields = ('product__descripcion', 'product__cod_articulo', 'price_list__name')
    autocomplete_fields = ['product', 'price_list', 'price_moneda']
    actions = ['actualizar_precios_masivo']

    @admin.display(description="Actualizado")
    def actualizado_hace(self, obj):
        return "-"

    @admin.action(description="📈 Actualizar precios seleccionados (Masivo)")
    def actualizar_precios_masivo(self, request, queryset):
        if 'apply' in request.POST:
            try:
                metodo = request.POST.get('metodo')
                tipo_redondeo = request.POST.get('redondeo')
                actualizados = 0
                errores = 0
                factor_porcentaje = 1
                factor_markup = 1
                formula_str = ""

                if metodo == 'porcentaje':
                    val = Decimal(request.POST.get('porcentaje', 0))
                    factor_porcentaje = 1 + (val / 100)
                elif metodo == 'markup':
                    val = Decimal(request.POST.get('markup', 0))
                    factor_markup = 1 + (val / 100)
                elif metodo == 'formula':
                    formula_str = request.POST.get('formula', '').lower().strip()

                for precio_obj in queryset:
                    nuevo_monto = Decimal(0)
                    try:
                        if metodo == 'porcentaje':
                            nuevo_monto = precio_obj.price_monto * factor_porcentaje
                        elif metodo == 'markup':
                            costo = precio_obj.product.precio_costo_monto
                            if costo <= 0: errores += 1; continue
                            nuevo_monto = costo * factor_markup
                        elif metodo == 'formula':
                            costo = float(precio_obj.product.precio_costo_monto)
                            precio_actual = float(precio_obj.price_monto)
                            contexto = {'costo': costo, 'precio': precio_actual, 'abs': abs, 'min': min, 'max': max}
                            resultado = eval(formula_str, {"__builtins__": None}, contexto)
                            nuevo_monto = Decimal(str(resultado))
                    except Exception:
                        errores += 1;
                        continue

                    if tipo_redondeo == 'entero':
                        nuevo_monto = nuevo_monto.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                    elif tipo_redondeo == 'diez':
                        nuevo_monto = (nuevo_monto / 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 10
                    else:
                        nuevo_monto = nuevo_monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                    precio_obj.price_monto = nuevo_monto
                    precio_obj.save()
                    actualizados += 1

                mensaje = f"✅ Se actualizaron {actualizados} precios."
                if errores > 0: mensaje += f" ⚠️ Hubo {errores} errores."
                self.message_user(request, mensaje)
                return HttpResponseRedirect(request.get_full_path())

            except (ValueError, TypeError, SyntaxError) as e:
                self.message_user(request, f"❌ Error en el cálculo: {str(e)}", level=messages.ERROR)

        return render(request, 'admin/ventas/productprice/actualizar_precios.html',
                      context={'queryset': queryset, 'title': 'Actualización Masiva de Precios'})


class ReciboImputacionInline(admin.TabularInline):
    model = ReciboImputacion
    extra = 1
    autocomplete_fields = ['comprobante']
    fields = ('comprobante', 'total_original_display', 'monto_imputado')
    readonly_fields = ('total_original_display',)

    def total_original_display(self, obj):
        if obj.comprobante: return f"${obj.comprobante.total:,.2f}"
        return "-"

    total_original_display.short_description = "Total Original"


class ReciboValorInline(admin.TabularInline):
    model = ReciboValor
    extra = 1
    autocomplete_fields = ['destino', 'banco_origen']


@admin.register(Recibo)
class ReciboAdmin(admin.ModelAdmin):
    list_display = ('numero', 'cliente', 'fecha', 'monto_total', 'estado', 'finanzas_aplicadas')
    list_filter = ('estado', 'fecha')
    search_fields = ('numero', 'cliente__entidad__razon_social')
    autocomplete_fields = ['cliente', 'serie']
    inlines = [ReciboImputacionInline, ReciboValorInline]
    readonly_fields = ('numero', 'finanzas_aplicadas', 'monto_total', 'creado_por')
    fieldsets = (
        ('Encabezado', {'fields': ('serie', 'fecha', 'cliente', 'estado')}),
        ('Auditoría', {'fields': ('creado_por', 'finanzas_aplicadas', 'observaciones')})
    )

    class Media:
        js = ('admin/js/recibo_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('api/get-comprobante-info/<int:pk>/', self.admin_site.admin_view(get_comprobante_venta_info),
                 name='ventas_get_comprobante_info')]
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
        if obj.estado == Recibo.Estado.CONFIRMADO and not obj.finanzas_aplicadas:
            try:
                obj.aplicar_finanzas()
                self.message_user(request, "✅ Recibo aplicado con éxito.")
            except Exception as e:
                obj.estado = Recibo.Estado.BORRADOR
                obj.save()
                self.message_user(request, f"❌ No se pudo confirmar: {e}", level=messages.ERROR)

        if obj.estado == Recibo.Estado.ANULADO and obj.finanzas_aplicadas:
            obj.revertir_finanzas()
            self.message_user(request, "⚠️ Recibo ANULADO. Saldos revertidos.")


@admin.register(ComprobantePendienteCAE)
class ComprobantePendienteCAEAdmin(ComprobanteVentaAdmin):
    """
    BANDEJA DE TRABAJO: Solo muestra comprobantes FISCALES que NO TIENEN CAE.
    Ideal para el operador que factura a fin de día.
    """
    list_display = ('numero', 'cliente', 'total', 'afip_error_visual', 'boton_solicitar_cae')
    list_display_links = ('numero',)

    # Desactivamos creación, solo es para procesar
    def has_add_permission(self, request): return False

    def get_queryset(self, request):
        """Filtro Mágico: Solo Fiscales Confirmados SIN CAE"""
        return super().get_queryset(request).filter(
            tipo_comprobante__es_fiscal=True,
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            cae__isnull=True
        )

    @admin.display(description="Estado AFIP")
    def afip_error_visual(self, obj):
        if obj.afip_error:
            return format_html('<span style="color:red;">❌ {}</span>', obj.afip_error[:100])
        return format_html('<span style="color:orange;">⏳ Pendiente</span>')

    @admin.display(description="Acción")
    def boton_solicitar_cae(self, obj):
        # Usamos un input hidden para simular la acción masiva sobre un solo item
        return format_html(
            '''<a class="button" style="background-color: #28a745;" 
               href="../comprobanteventa/?_selected_action={}&action=solicitar_cae_afip">
               🚀 Solicitar CAE
               </a>''',
            obj.pk
        )

@admin.register(DisenoImpresion)
class DisenoImpresionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'archivo_template', 'usa_html_bd', 'tiene_email_custom')
    search_fields = ('nombre',)
    help_text = "Define las plantillas HTML que se usarán para generar los PDFs."

    fieldsets = (
        ('Configuración Básica', {
            'fields': ('nombre', 'archivo_template')
        }),
        ('Diseño Avanzado (HTML)', {
            'fields': ('contenido_html',),
            'description': 'Pegue aquí el código HTML/Jinja2 completo para sobreescribir el archivo físico.',
            'classes': ('collapse',),  # Aparecerá contraído para no molestar si no se usa
        }),
        ('Personalización Email', {
            'fields': ('asunto_email', 'cuerpo_email'),
            'description': 'Use {cliente}, {numero}, {fecha}, {empresa} como variables.',
            'classes': ('collapse',),  # Oculto por defecto para limpiar la vista
        }),
    )

    # Columna calculada para ver rápido quién usa BD
    @admin.display(boolean=True, description="Usa HTML en BD")
    def usa_html_bd(self, obj):
        return bool(obj.contenido_html)

    @admin.display(boolean=True, description="Email Custom")
    def tiene_email_custom(self, obj):
        return bool(obj.cuerpo_email)


auditlog.register(ComprobanteVenta)
auditlog.register(Cliente)