# ventas/views.py (VERSIÓN DEFINITIVA: SMTP DB + HTML DB + APIS)

import json
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.db import transaction, models
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
# --- IMPORT NUEVO PARA RENDERIZAR HTML DESDE BD ---
from django.template import Template, Context
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from dataclasses import asdict as dc_asdict

# --- IMPORTS PARA EMAIL Y CONEXIÓN DINÁMICA ---
from django.core.mail import EmailMessage, get_connection
from django.conf import settings

from .utils_pdf import generar_qr_afip
from .models import DisenoImpresion

# Externos
from djmoney.money import Money
import weasyprint

# Modelos
from inventario.models import Articulo
from .models import ComprobanteVenta, ComprobanteVentaItem, Cliente, Recibo
from parametros.models import TipoComprobante, SerieDocumento
from parametros.models import ConfiguracionEmpresa
from parametros.models import ConfiguracionSMTP

# Servicios y Serializers
from .services import TaxCalculatorService, PricingService
from .serializers import ComprobanteVentaSerializer, ComprobanteVentaCreateSerializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated


# ==============================================================================
# --- VISTAS API Y REPORTES (INTACTAS) ---
# ==============================================================================

@staff_member_required
def get_precio_articulo(request, pk):
    try:
        articulo = Articulo.objects.get(pk=pk)
        data = {'precio': str(articulo.precio_venta_monto)}
        return JsonResponse(data)
    except Articulo.DoesNotExist:
        return JsonResponse({'error': 'Artículo no encontrado'}, status=404)


@staff_member_required
def get_precio_articulo_cliente(request, cliente_pk, articulo_pk):
    """
    Vista de API que devuelve el desglose de precios completo para un artículo y cliente.
    """
    try:
        articulo = get_object_or_404(Articulo, pk=articulo_pk)
        cliente = get_object_or_404(Cliente, pk=cliente_pk)
        cantidad = Decimal(request.GET.get('cantidad', '1'))

        pricing_data = PricingService.get_product_pricing(articulo, cliente, cantidad)
        data = dc_asdict(pricing_data)

        def format_for_json(obj):
            if isinstance(obj, Money):
                return f"{obj.amount:.2f}"
            if isinstance(obj, Decimal):
                return f"{obj:.2f}"
            if isinstance(obj, dict):
                return {k: format_for_json(v) for k, v in obj.items()}
            return obj

        json_safe_data = {k: format_for_json(v) for k, v in data.items()}
        return JsonResponse(json_safe_data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@staff_member_required
@require_POST
def calcular_totales_api(request):
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])

        class FakeItem:
            def __init__(self, item_data):
                self.articulo = Articulo.objects.get(pk=item_data.get('articulo'))
                self.cantidad = Decimal(item_data.get('cantidad', '0'))
                monto_str = item_data.get('precio_monto', item_data.get('precio', '0'))
                monto = Decimal(str(monto_str))
                self.precio_unitario_original = Money(monto, 'ARS')

            @property
            def subtotal(self):
                return self.cantidad * self.precio_unitario_original

        class FakeComprobante:
            def __init__(self, items_list):
                self.items_list = items_list
                tipo_id = data.get('tipo_comprobante')
                self.tipo_comprobante = TipoComprobante.objects.get(pk=tipo_id) if tipo_id else None

            @property
            def items(self): return self

            def all(self): return self.items_list

        fake_items = []
        for item in items_data:
            if item.get('articulo'):
                try:
                    fake_items.append(FakeItem(item))
                except Exception:
                    continue

        fake_comprobante = FakeComprobante(fake_items)
        subtotal = sum((item.subtotal for item in fake_items), Money(0, 'ARS'))
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(fake_comprobante, 'venta')
        total = subtotal + Money(sum(desglose_impuestos.values()), subtotal.currency)

        return JsonResponse({
            'subtotal': f"{subtotal.amount:,.2f}",
            'currency_symbol': subtotal.currency.code,
            'impuestos': {k: f"{v:,.2f}" for k, v in desglose_impuestos.items()},
            'total': f"{total.amount:,.2f}"
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@staff_member_required
def get_comprobante_venta_info(request, pk):
    try:
        comp = ComprobanteVenta.objects.get(pk=pk)
        return JsonResponse({
            'saldo': str(comp.saldo_pendiente),
            'total': str(comp.total),
            'id': comp.pk
        })
    except ComprobanteVenta.DoesNotExist:
        return JsonResponse({'error': 'Comprobante no encontrado'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
def reporte_cuenta_corriente(request, cliente_pk):
    cliente = get_object_or_404(Cliente, pk=cliente_pk)

    facturas = ComprobanteVenta.objects.filter(
        cliente=cliente,
        estado=ComprobanteVenta.Estado.CONFIRMADO,
        condicion_venta=ComprobanteVenta.CondicionVenta.CTA_CTE
    ).annotate(
        monto_debe=models.F('total'),
        monto_haber=models.Value(0, output_field=models.DecimalField()),
        tipo_doc=models.Value('Factura', output_field=models.CharField())
    ).values('fecha', 'numero', 'letra', 'punto_venta', 'monto_debe', 'monto_haber', 'tipo_doc', 'id')

    recibos = Recibo.objects.filter(
        cliente=cliente,
        estado=Recibo.Estado.CONFIRMADO,
        origen=Recibo.Origen.COBRANZA
    ).annotate(
        monto_debe=models.Value(0, output_field=models.DecimalField()),
        monto_haber=models.F('monto_total'),
        tipo_doc=models.Value('Recibo', output_field=models.CharField()),
        letra=models.Value('X', output_field=models.CharField()),
        punto_venta=models.Value(0, output_field=models.IntegerField())
    ).values('fecha', 'numero', 'letra', 'punto_venta', 'monto_debe', 'monto_haber', 'tipo_doc', 'id')

    movimientos = sorted(list(facturas) + list(recibos), key=lambda x: x['fecha'])

    saldo = 0
    for mov in movimientos:
        saldo += (mov['monto_debe'] - mov['monto_haber'])
        mov['saldo_acumulado'] = saldo

    return render(request, 'ventas/reporte_cta_cte.html', {
        'cliente': cliente,
        'movimientos': movimientos,
        'saldo_final': saldo,
        'hoy': timezone.now()
    })


class ComprobanteVentaViewSet(viewsets.ModelViewSet):
    from .serializers import ComprobanteVentaSerializer, ComprobanteVentaCreateSerializer
    queryset = ComprobanteVenta.objects.all().order_by('-fecha', '-numero')
    search_fields = ['numero', 'cliente__entidad__razon_social']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ComprobanteVentaCreateSerializer
        return ComprobanteVentaSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                items_data = serializer.validated_data.pop('items')
                datos_comprobante = serializer.validated_data

                if not datos_comprobante.get('serie'):
                    tipo = datos_comprobante.get('tipo_comprobante')
                    punto_venta = datos_comprobante.get('punto_venta', 1)
                    serie = SerieDocumento.objects.filter(
                        tipo_comprobante=tipo,
                        punto_venta=punto_venta,
                        activo=True
                    ).first()
                    if serie:
                        datos_comprobante['serie'] = serie

                if not datos_comprobante.get('deposito'):
                    if datos_comprobante.get('serie') and datos_comprobante['serie'].deposito_defecto:
                        datos_comprobante['deposito'] = datos_comprobante['serie'].deposito_defecto
                    else:
                        from inventario.models import Deposito
                        principal = Deposito.objects.filter(es_principal=True).first()
                        if principal:
                            datos_comprobante['deposito'] = principal

                comprobante = ComprobanteVenta.objects.create(**datos_comprobante)
                subtotal_acumulado = Decimal(0)

                for item_data in items_data:
                    item_creado = ComprobanteVentaItem.objects.create(comprobante=comprobante, **item_data)
                    subtotal_acumulado += item_creado.subtotal

                desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(comprobante, 'venta')
                total_impuestos = sum(desglose_impuestos.values())

                comprobante.subtotal = subtotal_acumulado
                comprobante.impuestos = {k: str(v) for k, v in desglose_impuestos.items()}
                comprobante.total = subtotal_acumulado + total_impuestos
                comprobante.saldo_pendiente = comprobante.total
                comprobante.save()

                pagos_data = request.data.get('pagos', [])
                if pagos_data and comprobante.condicion_venta == ComprobanteVenta.CondicionVenta.CONTADO:
                    recibo = Recibo.objects.create(
                        cliente=comprobante.cliente,
                        fecha=comprobante.fecha,
                        estado=Recibo.Estado.CONFIRMADO,
                        origen=Recibo.Origen.CONTADO,
                        observaciones=f"Cobro auto. Factura {comprobante.numero_completo}",
                        creado_por=request.user
                    )
                    # Crear Valores (Efectivo, etc)
                    from finanzas.models import TipoValor, CuentaFondo
                    caja_default = CuentaFondo.objects.first()  # Simplificación: Primera caja
                    tipo_efectivo = TipoValor.objects.filter(nombre__icontains="Efectivo").first()

                    total_pagado = Decimal(0)
                    for p in pagos_data:
                        monto = Decimal(str(p.get('monto', 0)))
                        if monto > 0:
                            # Crear ReciboValor
                            # (Aquí deberías buscar el TipoValor real según p['metodo'])
                            pass
                            # ... Lógica de creación de ReciboValor ...

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteVentaSerializer(comprobante)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


# ==============================================================================
# --- SECCIÓN REFACTORIZADA: PDF Y EMAILS AVANZADOS ---
# ==============================================================================

def obtener_contexto_pdf(comprobante, request=None):
    """
    Prepara todo el diccionario de datos necesario para el PDF.
    """
    config = ConfiguracionEmpresa.objects.first()

    # Roles Fiscales
    discrimina_iva = comprobante.letra in ['A', 'B', 'M']
    es_monotributo = comprobante.letra == 'C'

    items_impresion = []
    subtotal_visual_acumulado = Decimal(0)

    for item in comprobante.items.all():
        precio_neto_guardado = item.precio_unitario_original
        cantidad = item.cantidad

        try:
            tasa = item.articulo.iva if item.articulo and item.articulo.iva else Decimal("21.00")
        except:
            tasa = Decimal("21.00")

        factor_iva = 1 + (tasa / 100)

        if es_monotributo:
            precio_unitario_mostrar = precio_neto_guardado * factor_iva
            subtotal_linea = precio_unitario_mostrar * cantidad
        else:
            precio_unitario_mostrar = precio_neto_guardado
            subtotal_linea = precio_unitario_mostrar * cantidad

        subtotal_visual_acumulado += subtotal_linea

        items_impresion.append({
            'codigo': item.articulo.cod_articulo if item.articulo else '-',
            'descripcion': item.articulo.descripcion,
            'cantidad': cantidad,
            'unidad': 'Unid.',
            'precio_unitario': precio_unitario_mostrar,
            'subtotal': subtotal_linea
        })

    subtotal_comprobante = subtotal_visual_acumulado

    if discrimina_iva:
        mostrar_tabla_impuestos = True
        total_iva_calculado = comprobante.total - subtotal_comprobante
    else:
        mostrar_tabla_impuestos = False
        total_iva_calculado = Decimal(0)

    qr_afip = generar_qr_afip(comprobante)

    logo_url = None
    if config and config.logo and request:
        logo_url = request.build_absolute_uri(config.logo.url)

    # Selección Dinámica de Reporte (Archivo o BD)
    template_name = 'ventas/pdf/factura_premium.html'  # Default
    if comprobante.serie and comprobante.serie.diseno_impresion:
        # El template name se usa como fallback o referencia
        template_name = comprobante.serie.diseno_impresion.archivo_template

    return {
        'comprobante': comprobante,
        'items_impresion': items_impresion,
        'empresa': config.entidad if config else None,
        'config': config,
        'logo_url': logo_url,
        'discrimina_iva': discrimina_iva,
        'es_monotributo': es_monotributo,
        'subtotal_comprobante': subtotal_comprobante,
        'total_iva_calculado': total_iva_calculado,
        'mostrar_tabla_impuestos': mostrar_tabla_impuestos,
        'qr_afip': qr_afip,
        'template_name': template_name
    }


def generar_pdf_bytes(comprobante, request):
    """
    Genera el archivo PDF en memoria y devuelve los bytes.
    SOPORTE AVANZADO: Renderiza desde archivo físico O desde código HTML en BD.
    """
    context_dict = obtener_contexto_pdf(comprobante, request)
    # Sacamos el nombre por defecto del contexto para limpieza
    default_template_name = context_dict.pop('template_name')

    html_string = ""

    # 1. Verificar si hay un diseño personalizado cargado en Base de Datos
    # (Asumiendo que has agregado el campo 'contenido_html' al modelo DisenoImpresion)
    diseno = None
    if comprobante.serie and comprobante.serie.diseno_impresion:
        diseno = comprobante.serie.diseno_impresion

    # Si el diseño tiene contenido HTML guardado, lo usamos (Prioridad Alta)
    if diseno and hasattr(diseno, 'contenido_html') and diseno.contenido_html:
        try:
            template = Template(diseno.contenido_html)
            context = Context(context_dict)
            html_string = template.render(context)
        except Exception as e:
            # Fallback de seguridad si falla el renderizado del HTML de la BD
            print(f"Error renderizando plantilla de BD: {e}. Usando archivo por defecto.")
            html_string = render_to_string(default_template_name, context_dict, request=request)
    else:
        # 2. Si no, usamos el archivo físico (Comportamiento Estándar)
        html_string = render_to_string(default_template_name, context_dict, request=request)

    pdf_file = weasyprint.HTML(
        string=html_string,
        base_url=request.build_absolute_uri()
    ).write_pdf()

    return pdf_file


# En ventas/views.py

def enviar_comprobante_por_email(comprobante, request):
    """
    Envía el comprobante por email usando configuración SMTP de Base de Datos.
    Soporta HTML completo en el cuerpo del mensaje.
    """
    # 1. Validar Email del Cliente
    entidad = comprobante.cliente.entidad
    email_destino = getattr(entidad, 'email', None)
    if not email_destino:
        return False, f"El cliente '{entidad.razon_social}' no tiene un email cargado."

    # 2. Buscar Configuración SMTP Activa
    config_smtp = ConfiguracionSMTP.objects.filter(activo=True).first()
    if not config_smtp:
        return False, "Error: No hay un servidor de correo configurado (Parámetros > Config SMTP)."

    host_real = config_smtp.host_custom if config_smtp.host == 'custom' else config_smtp.host

    try:
        # 3. Establecer Conexión
        connection = get_connection(
            host=host_real,
            port=config_smtp.puerto,
            username=config_smtp.usuario,
            password=config_smtp.password,
            use_tls=config_smtp.usar_tls,
            use_ssl=config_smtp.usar_ssl
        )

        # 4. Generar PDF
        pdf_content = generar_pdf_bytes(comprobante, request)
        filename = f"{comprobante.tipo_comprobante.nombre}_{comprobante.numero_completo}.pdf"

        # 5. Preparar Variables para la Plantilla
        nombre_empresa = getattr(comprobante, 'empresa_nombre_fantasia', 'Nuestra Empresa')

        # Diccionario de contexto (Datos que puedes usar en el HTML)
        context_data = {
            'cliente': entidad.razon_social,
            'numero': comprobante.numero_completo,
            'fecha': comprobante.fecha.strftime('%d/%m/%Y'),
            'empresa': nombre_empresa,
            'vencimiento': comprobante.vto_cae.strftime('%d/%m/%Y') if comprobante.vto_cae else '-',
            'total': f"${comprobante.total:,.2f}",
            'link_pago': "https://tupagina.com/pagar"  # Ejemplo futuro
        }

        # 6. Definir Asunto y Cuerpo por defecto
        subject = f"Su Comprobante {comprobante.numero_completo} - {nombre_empresa}"
        body_html = f"""
        <p>Estimado/a <strong>{entidad.razon_social}</strong>:</p>
        <p>Adjuntamos su comprobante electrónico <strong>{comprobante.numero_completo}</strong>.</p>
        <p>Atte,<br>{nombre_empresa}</p>
        """

        # 7. Procesar Plantilla Personalizada (Si existe)
        if comprobante.serie and comprobante.serie.diseno_impresion:
            diseno = comprobante.serie.diseno_impresion

            # Asunto (Este sigue usando format simple porque no lleva HTML)
            if diseno.asunto_email:
                try:
                    subject = diseno.asunto_email.format(**context_data)
                except:
                    pass  # Si falla el formato, usa el original sin romper

            # Cuerpo HTML (Usamos el Motor de Django)
            if diseno.cuerpo_email:
                try:
                    # Esto permite usar CSS { } y variables {{ }} sin conflictos
                    template_email = Template(diseno.cuerpo_email)
                    context_email = Context(context_data)
                    body_html = template_email.render(context_email)
                except Exception as e:
                    print(f"Error renderizando email: {e}")
                    # Si falla, usamos el body por defecto, pero no detenemos el envío.

        # 8. Crear Email
        email = EmailMessage(
            subject=subject,
            body=body_html,  # Aquí va el HTML procesado
            from_email=config_smtp.email_from,
            to=[email_destino],
            connection=connection
        )

        # ¡CLAVE! Avisamos que el contenido es HTML
        email.content_subtype = "html"

        email.attach(filename, pdf_content, 'application/pdf')
        email.send()

        return True, f"Enviado correctamente a {email_destino}"

    except Exception as e:
        return False, f"Error técnico SMTP: {str(e)}"


@staff_member_required
def imprimir_comprobante_pdf(request, pk):
    """
    Vista original de descarga: ahora solo llama a la función generadora.
    """
    comprobante = get_object_or_404(ComprobanteVenta, pk=pk)
    pdf_bytes = generar_pdf_bytes(comprobante, request)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"Comprobante_{comprobante.numero_completo}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generar_pdf_venta_api(request, pk):
    # Vista API Legacy
    comprobante = get_object_or_404(ComprobanteVenta, pk=pk)
    config = ConfiguracionEmpresa.objects.first()

    context = {
        'comprobante': comprobante,
        'tenant': request.tenant,
        'config': config,
        'request': request
    }

    html_string = render_to_string('ventas/comprobante_pdf.html', context, request=request)
    pdf_file = weasyprint.HTML(
        string=html_string,
        base_url=request.build_absolute_uri()
    ).write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f"Comprobante_{comprobante.numero_completo}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response