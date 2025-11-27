# ventas/views.py (VERSIÓN FINAL CORREGIDA)

import json
from decimal import Decimal
from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from dataclasses import asdict as dc_asdict

# --- CORRECCIÓN CRÍTICA: Importamos Money ---
from djmoney.money import Money

# Modelos
from inventario.models import Articulo, StockArticulo
from .models import ComprobanteVenta, ComprobanteVentaItem, Cliente
from parametros.models import TipoComprobante

# Servicios y Serializers
from .services import TaxCalculatorService, PricingService
from .serializers import ComprobanteVentaSerializer, ComprobanteVentaCreateSerializer

from django.http import HttpResponse
from django.template.loader import render_to_string
import weasyprint

# --- Vistas de API para el Admin ---

@staff_member_required
def get_precio_articulo(request, pk):
    """
    Vista de fallback que devuelve el precio de venta base de un artículo.
    """
    try:
        articulo = Articulo.objects.get(pk=pk)
        # Convertimos a float/str para JSON. Usamos precio_venta_monto directamente
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
            # Ahora Money está importado y esto funcionará
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
                # Robustez: soportar 'precio' o 'precio_monto'
                monto_str = item_data.get('precio_monto', item_data.get('precio', '0'))
                monto = Decimal(str(monto_str))
                # Asumimos moneda base por ahora (ARS)
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

        # Construimos objetos fake solo si tienen artículo válido
        fake_items = []
        for item in items_data:
            if item.get('articulo'):
                try:
                    fake_items.append(FakeItem(item))
                except Exception:
                    continue  # Ignorar items mal formados

        fake_comprobante = FakeComprobante(fake_items)

        # Cálculos
        subtotal = sum((item.subtotal for item in fake_items), Money(0, 'ARS'))

        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(fake_comprobante, 'venta')
        total_impuestos = sum(desglose_impuestos.values())

        total = subtotal + Money(total_impuestos, subtotal.currency)

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


# --- ViewSet para la API REST pública (DRF) ---

class ComprobanteVentaViewSet(viewsets.ModelViewSet):
    # Importación local para evitar dependencias circulares si las hubiera
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
                comprobante = ComprobanteVenta.objects.create(**serializer.validated_data)

                for item_data in items_data:
                    item_creado = ComprobanteVentaItem.objects.create(comprobante=comprobante, **item_data)

                    if comprobante.estado == 'FN' and comprobante.tipo_comprobante.afecta_stock:
                        articulo = item_creado.articulo
                        cantidad_a_descontar = item_creado.cantidad
                        deposito_venta = comprobante.deposito

                        if not deposito_venta:
                            raise ValidationError("No se ha especificado un depósito para la venta.")

                        # Bloqueo pesimista para evitar condiciones de carrera en stock
                        stock_obj = StockArticulo.objects.select_for_update().get(
                            articulo=articulo,
                            deposito=deposito_venta
                        )

                        if stock_obj.cantidad < cantidad_a_descontar:
                            raise ValidationError(
                                f"Stock insuficiente para {articulo.descripcion}. "
                                f"Disponible: {stock_obj.cantidad}, Solicitado: {cantidad_a_descontar}"
                            )

                        stock_obj.cantidad -= cantidad_a_descontar
                        stock_obj.save()

        except ValidationError as e:
            return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
        except Articulo.DoesNotExist:
            return Response({'error': 'Uno de los artículos en el comprobante no existe.'},
                            status=status.HTTP_400_BAD_REQUEST)
        except StockArticulo.DoesNotExist:
            return Response({
                'error': "Uno de los artículos no tiene un registro de stock en el depósito especificado."
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f"Error inesperado en el servidor: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        read_serializer = ComprobanteVentaSerializer(comprobante)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


@staff_member_required
def imprimir_comprobante_pdf(request, pk):
    """
    Genera un PDF para el comprobante de venta.
    """
    comprobante = get_object_or_404(ComprobanteVenta, pk=pk)

    # Contexto para el template
    context = {
        'comprobante': comprobante,
        'tenant': request.tenant,  # Django-tenants inyecta esto
    }

    # 1. Renderizar HTML
    html_string = render_to_string('ventas/comprobante_pdf.html', context)

    # 2. Generar PDF
    pdf_file = weasyprint.HTML(string=html_string).write_pdf()

    # 3. Devolver respuesta HTTP con el PDF
    response = HttpResponse(pdf_file, content_type='application/pdf')
    # 'inline' abre en el navegador, 'attachment' fuerza la descarga
    filename = f"Comprobante_{comprobante.numero_completo}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'

    return response