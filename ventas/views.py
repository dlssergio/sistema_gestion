# ventas/views.py (VERSIÓN FINAL DEFINITIVA)

import json
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.db import transaction, models
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from dataclasses import asdict as dc_asdict

# Externos
from djmoney.money import Money
import weasyprint

# Modelos
from inventario.models import Articulo, StockArticulo
from .models import ComprobanteVenta, ComprobanteVentaItem, Cliente, Recibo
from parametros.models import TipoComprobante, SerieDocumento

# Servicios y Serializers
from .services import TaxCalculatorService, PricingService
from .serializers import ComprobanteVentaSerializer, ComprobanteVentaCreateSerializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated


# ... otros imports ...


# --- Vistas de API para el Admin ---

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
        import traceback
        traceback.print_exc()
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
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=400)


@staff_member_required
def get_comprobante_venta_info(request, pk):
    """
    API para obtener saldo y total de una factura de venta.
    """
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


# --- REPORTE CUENTA CORRIENTE ---

@staff_member_required
def reporte_cuenta_corriente(request, cliente_pk):
    cliente = get_object_or_404(Cliente, pk=cliente_pk)

    # 1. Facturas (Debe) - SOLO CTA CTE
    facturas = ComprobanteVenta.objects.filter(
        cliente=cliente,
        estado=ComprobanteVenta.Estado.CONFIRMADO,
        condicion_venta=ComprobanteVenta.CondicionVenta.CTA_CTE
    ).annotate(
        monto_debe=models.F('total'),
        monto_haber=models.Value(0, output_field=models.DecimalField()),
        tipo_doc=models.Value('Factura', output_field=models.CharField())
    ).values('fecha', 'numero', 'letra', 'punto_venta', 'monto_debe', 'monto_haber', 'tipo_doc', 'id')

    # 2. Recibos (Haber) - SOLO COBRANZA (No Contado)
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

    # 3. Unir y Ordenar
    movimientos = sorted(list(facturas) + list(recibos), key=lambda x: x['fecha'])

    # 4. Calcular Saldo
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


# --- API REST / PDF ---

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

                # 1. ASIGNACIÓN AUTOMÁTICA DE SERIE (Numeración)
                # Si no viene serie, buscamos una activa para este tipo de comprobante y punto de venta
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
                    # Si no hay serie, quedará sin numerar (o deberíamos lanzar error,
                    # pero dejémoslo pasar para no bloquear si falta config)

                # 2. CREAR CABECERA
                comprobante = ComprobanteVenta.objects.create(**datos_comprobante)

                # 3. CREAR ÍTEMS Y CALCULAR SUBTOTAL
                subtotal_acumulado = Decimal(0)

                for item_data in items_data:
                    # Guardamos el ítem
                    item_creado = ComprobanteVentaItem.objects.create(comprobante=comprobante, **item_data)

                    # Sumamos al subtotal (Cantidad * Precio)
                    subtotal_acumulado += item_creado.subtotal

                    # 4. DESCUENTO DE STOCK
                    if comprobante.estado == ComprobanteVenta.Estado.CONFIRMADO and comprobante.tipo_comprobante.afecta_stock:
                        articulo = item_creado.articulo
                        cantidad_a_descontar = item_creado.cantidad
                        deposito_venta = comprobante.deposito

                        # Si no tiene depósito, intentamos usar el de la serie o el default
                        if not deposito_venta:
                            if comprobante.serie and comprobante.serie.deposito_defecto:
                                deposito_venta = comprobante.serie.deposito_defecto
                            else:
                                from inventario.models import Deposito
                                deposito_venta = Deposito.objects.filter(es_principal=True).first()

                            # Actualizamos el comprobante con el depósito encontrado
                            if deposito_venta:
                                comprobante.deposito = deposito_venta
                                comprobante.save(update_fields=['deposito'])

                        if not deposito_venta:
                            raise ValidationError("No se pudo determinar un depósito para descontar stock.")

                        stock_obj = StockArticulo.objects.select_for_update().get(
                            articulo=articulo,
                            deposito=deposito_venta
                        )

                        # (Opcional) Validación estricta de stock negativo
                        # if stock_obj.cantidad < cantidad_a_descontar:
                        #    raise ValidationError(f"Stock insuficiente para {articulo.descripcion}.")

                        stock_obj.cantidad -= cantidad_a_descontar
                        stock_obj.save()

                # 5. CÁLCULO DE TOTALES E IMPUESTOS (El Fix del $0.00)
                # Usamos el servicio de impuestos para calcular IVA, etc.
                desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(comprobante, 'venta')
                total_impuestos = sum(desglose_impuestos.values())

                # Convertimos todo a Decimal/Money para guardar
                # Asumimos moneda base ARS por defecto para simplificar API
                comprobante.subtotal = subtotal_acumulado
                comprobante.impuestos = {k: str(v) for k, v in desglose_impuestos.items()}
                comprobante.total = subtotal_acumulado + total_impuestos

                # El saldo inicial es igual al total (si es cta cte) o 0 (si es contado, se ajustará con recibo)
                # Por ahora lo dejamos como deuda total, luego el recibo lo baja.
                comprobante.saldo_pendiente = comprobante.total

                comprobante.stock_aplicado = True
                comprobante.save()

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteVentaSerializer(comprobante)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


@staff_member_required
def imprimir_comprobante_pdf(request, pk):
    comprobante = get_object_or_404(ComprobanteVenta, pk=pk)
    context = {'comprobante': comprobante, 'tenant': request.tenant}
    html_string = render_to_string('ventas/comprobante_pdf.html', context)
    pdf_file = weasyprint.HTML(string=html_string).write_pdf()
    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f"Comprobante_{comprobante.numero_completo}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


# --- GENERACIÓN DE PDF PARA API (POS) ---

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generar_pdf_venta_api(request, pk):
    """
    Genera el PDF del comprobante para ser consumido por el Frontend (Vue.js).
    Usa WeasyPrint y el template existente.
    """
    comprobante = get_object_or_404(ComprobanteVenta, pk=pk)

    # Contexto para el template
    # 'tenant' viene del middleware de django-tenants
    # 'configuracion' la buscamos para tener el logo y datos fiscales
    from parametros.models import ConfiguracionEmpresa
    config = ConfiguracionEmpresa.objects.first()

    context = {
        'comprobante': comprobante,
        'tenant': request.tenant,
        'config': config,  # Pasamos la config para usar el logo en el HTML
        'request': request  # Necesario para construir URLs absolutas de imágenes
    }

    html_string = render_to_string('ventas/comprobante_pdf.html', context, request=request)

    # Generar PDF
    pdf_file = weasyprint.HTML(
        string=html_string,
        base_url=request.build_absolute_uri()
    ).write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f"Comprobante_{comprobante.numero_completo}.pdf"
    # 'inline' para que el navegador intente mostrarlo en lugar de solo descargar
    response['Content-Disposition'] = f'inline; filename="{filename}"'

    return response