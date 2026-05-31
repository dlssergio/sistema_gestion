# compras/views.py
import json
from decimal import Decimal
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    ComprobanteCompra, ComprobanteCompraItem,
    Proveedor,
    ListaPreciosProveedor, ItemListaPreciosProveedor,
    OrdenPago, OrdenPagoImputacion, OrdenPagoValor,

    HistorialPrecioProveedor,
)
from inventario.models import Articulo, Deposito
from parametros.models import Moneda, TipoComprobante
from .serializers import (
    ProveedorListSerializer, ProveedorDetailSerializer, ProveedorWriteSerializer,
    ComprobanteCompraListSerializer, ComprobanteCompraDetailSerializer,
    ComprobanteCompraWriteSerializer,
    OrdenPagoListSerializer, OrdenPagoDetailSerializer,
    ListaPreciosProveedorListSerializer, ListaPreciosProveedorDetailSerializer,
    ItemListaPreciosSerializer,
)
from .services import CostCalculatorService


# ─────────────────────────────────────────────
#  PROVEEDOR
# ─────────────────────────────────────────────

class ProveedorViewSet(viewsets.ModelViewSet):
    """
    GET    /api/proveedores/           lista con saldo de deuda
    GET    /api/proveedores/{id}/      ficha completa con KPIs
    PATCH  /api/proveedores/{id}/      editar datos comerciales/bancarios
    GET    /api/proveedores/{id}/comprobantes/    historial de facturas
    GET    /api/proveedores/{id}/cuenta_corriente/ saldo y movimientos
    """
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields   = ['entidad__razon_social', 'entidad__cuit', 'nombre_fantasia', 'codigo_proveedor']
    ordering_fields = ['entidad__razon_social', 'codigo_proveedor', 'esta_activo']
    ordering        = ['entidad__razon_social']

    def get_queryset(self):
        qs = Proveedor.objects.select_related(
            'entidad', 'entidad__situacion_iva', 'moneda_compra'
        )
        activo = self.request.query_params.get('activo')
        if activo is not None:
            qs = qs.filter(esta_activo=(activo.lower() == 'true'))
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return ProveedorListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return ProveedorWriteSerializer
        return ProveedorDetailSerializer

    @action(detail=True, methods=['get'], url_path='comprobantes')
    def comprobantes(self, request, pk=None):
        """Historial de comprobantes de un proveedor."""
        proveedor = self.get_object()
        qs = ComprobanteCompra.objects.filter(
            proveedor=proveedor
        ).select_related('tipo_comprobante').order_by('-fecha')

        estado = request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        serializer = ComprobanteCompraListSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='cuenta_corriente')
    def cuenta_corriente(self, request, pk=None):
        """
        Saldo y detalle de cuenta corriente del proveedor.
        Solo incluye comprobantes cuyo tipo_comprobante.mueve_cta_cte=True
        (facturas reales), excluyendo remitos, órdenes de compra, etc.
        """
        proveedor = self.get_object()

        # Solo comprobantes que afectan la deuda (facturas, notas de crédito/débito)
        facturas = ComprobanteCompra.objects.filter(
            proveedor=proveedor,
            estado=ComprobanteCompra.Estado.CONFIRMADO,
            condicion_compra=ComprobanteCompra.CondicionCompra.CTA_CTE,
            tipo_comprobante__mueve_cta_cte=True,
            saldo_pendiente__gt=0,              # solo con saldo pendiente
        ).select_related('tipo_comprobante').order_by('-fecha')

        agg = ComprobanteCompra.objects.filter(
            proveedor=proveedor,
            estado=ComprobanteCompra.Estado.CONFIRMADO,
            condicion_compra=ComprobanteCompra.CondicionCompra.CTA_CTE,
            tipo_comprobante__mueve_cta_cte=True,
        ).aggregate(
            total_deuda=Sum('saldo_pendiente'),
            total_facturado=Sum('total'),
        )

        movimientos = []
        for f in facturas:
            movimientos.append({
                'id':              f.id,
                'fecha':           f.fecha,
                'numero':          f"{str(f.punto_venta or 0).zfill(4)}-{str(f.numero or 0).zfill(8)}",
                'tipo':            f.tipo_comprobante.nombre,
                'letra':           f.letra,
                'total':           float(f.total or 0),
                'saldo_pendiente': float(f.saldo_pendiente or 0),
                'estado':          f.get_estado_display(),
            })

        return Response({
            'proveedor_id':    proveedor.pk,
            'razon_social':    proveedor.entidad.razon_social,
            'saldo_deuda':     float(agg['total_deuda'] or 0),
            'total_facturado': float(agg['total_facturado'] or 0),
            'movimientos':     movimientos,
        })


# ─────────────────────────────────────────────
#  COMPROBANTES DE COMPRA
# ─────────────────────────────────────────────

class ComprobanteCompraViewSet(viewsets.ModelViewSet):
    """
    GET    /api/comprobantes-compra/            lista con filtros
    POST   /api/comprobantes-compra/            crear en borrador
    GET    /api/comprobantes-compra/{id}/       detalle con ítems
    PATCH  /api/comprobantes-compra/{id}/       editar (solo borrador)
    POST   /api/comprobantes-compra/{id}/confirmar/
    POST   /api/comprobantes-compra/{id}/anular/
    """
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields   = ['proveedor__entidad__razon_social', 'numero']
    ordering        = ['-fecha', '-id']

    def get_queryset(self):
        qs = ComprobanteCompra.objects.select_related(
            'proveedor__entidad', 'tipo_comprobante', 'deposito'
        ).prefetch_related('items__articulo')

        # Filtros
        proveedor = self.request.query_params.get('proveedor')
        estado    = self.request.query_params.get('estado')
        desde     = self.request.query_params.get('desde')
        hasta     = self.request.query_params.get('hasta')

        if proveedor: qs = qs.filter(proveedor_id=proveedor)
        if estado:    qs = qs.filter(estado=estado)
        if desde:     qs = qs.filter(fecha__date__gte=desde)
        if hasta:     qs = qs.filter(fecha__date__lte=hasta)

        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return ComprobanteCompraListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return ComprobanteCompraWriteSerializer
        return ComprobanteCompraDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                items_data  = serializer.validated_data.pop('items')
                compra      = ComprobanteCompra.objects.create(**serializer.validated_data)

                total = Decimal(0)
                for item in items_data:
                    costo = item.get('precio_costo_unitario_monto', Decimal(0))
                    ComprobanteCompraItem.objects.create(
                        comprobante=compra,
                        articulo=item['articulo'],
                        cantidad=item['cantidad'],
                        precio_costo_unitario_monto=costo,
                    )
                    total += Decimal(str(item['cantidad'])) * Decimal(str(costo))

                compra.subtotal       = total
                compra.total          = total
                compra.saldo_pendiente = total
                compra.save(update_fields=['subtotal', 'total', 'saldo_pendiente'])

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            ComprobanteCompraDetailSerializer(compra).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'])
    def confirmar(self, request, pk=None):
        compra = self.get_object()
        if compra.estado != ComprobanteCompra.Estado.BORRADOR:
            return Response(
                {'error': f'Solo se pueden confirmar comprobantes en Borrador. Estado actual: {compra.get_estado_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not compra.items.exists():
            return Response({'error': 'El comprobante no tiene ítems.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            compra.estado = ComprobanteCompra.Estado.CONFIRMADO
            compra.save(update_fields=['estado'])

            # Aplicar movimientos de stock según el tipo de comprobante
            tipo = compra.tipo_comprobante
            if tipo.mueve_stock and not compra.stock_aplicado:
                from .services import ComprasStockService
                if tipo.afecta_stock_fisico:
                    # Factura / Remito → ingreso físico (stock REAL)
                    ComprasStockService.procesar_recepcion_mercaderia(compra)
                else:
                    # Orden de Compra → stock "A Recibir" (RCPT)
                    ComprasStockService.confirmar_orden_compra(compra)

        # Recargar desde DB para reflejar stock_aplicado actualizado
        compra.refresh_from_db()
        return Response(ComprobanteCompraDetailSerializer(compra).data)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        compra = self.get_object()
        if compra.estado == ComprobanteCompra.Estado.ANULADO:
            return Response({'error': 'El comprobante ya está anulado.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            compra.estado = ComprobanteCompra.Estado.ANULADO
            compra.save(update_fields=['estado'])

        return Response(ComprobanteCompraDetailSerializer(compra).data)


# ─────────────────────────────────────────────
#  ÓRDENES DE PAGO
# ─────────────────────────────────────────────

class OrdenPagoViewSet(viewsets.ModelViewSet):
    """
    GET    /api/ordenes-pago/           lista
    POST   /api/ordenes-pago/           crear
    GET    /api/ordenes-pago/{id}/      detalle
    POST   /api/ordenes-pago/{id}/confirmar/
    POST   /api/ordenes-pago/{id}/anular/
    """
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields   = ['proveedor__entidad__razon_social', 'numero']
    ordering        = ['-fecha', '-id']

    def get_queryset(self):
        qs = OrdenPago.objects.select_related(
            'proveedor__entidad'
        ).prefetch_related('imputaciones__comprobante', 'valores__tipo', 'valores__origen')

        proveedor = self.request.query_params.get('proveedor')
        estado    = self.request.query_params.get('estado')
        if proveedor: qs = qs.filter(proveedor_id=proveedor)
        if estado:    qs = qs.filter(estado=estado)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return OrdenPagoListSerializer
        return OrdenPagoDetailSerializer

    @action(detail=True, methods=['post'])
    def confirmar(self, request, pk=None):
        op = self.get_object()
        if op.estado != OrdenPago.Estado.BORRADOR:
            return Response({'error': 'Solo se pueden confirmar órdenes en Borrador.'}, status=400)

        with transaction.atomic():
            op.estado = OrdenPago.Estado.CONFIRMADO
            op.save(update_fields=['estado'])
            op.aplicar_finanzas()

        return Response(OrdenPagoDetailSerializer(op).data)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        op = self.get_object()
        if op.estado == OrdenPago.Estado.ANULADO:
            return Response({'error': 'La orden ya está anulada.'}, status=400)

        with transaction.atomic():
            op.estado = OrdenPago.Estado.ANULADO
            op.save(update_fields=['estado'])

        return Response(OrdenPagoDetailSerializer(op).data)


# ─────────────────────────────────────────────
#  LISTAS DE PRECIOS
# ─────────────────────────────────────────────

class ListaPreciosProveedorViewSet(viewsets.ModelViewSet):
    """
    GET  /api/listas-precios/           lista
    GET  /api/listas-precios/{id}/      detalle con ítems
    POST /api/listas-precios/{id}/agregar_item/
    """
    filter_backends = [filters.SearchFilter]
    search_fields   = ['nombre', 'proveedor__entidad__razon_social']

    def get_queryset(self):
        qs = ListaPreciosProveedor.objects.select_related(
            'proveedor__entidad'
        ).prefetch_related('items__articulo')
        proveedor = self.request.query_params.get('proveedor')
        if proveedor:
            qs = qs.filter(proveedor_id=proveedor)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return ListaPreciosProveedorListSerializer
        return ListaPreciosProveedorDetailSerializer

    @action(detail=True, methods=['post'], url_path='agregar_item')
    def agregar_item(self, request, pk=None):
        lista = self.get_object()
        serializer = ItemListaPreciosSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(lista_precios=lista)
        return Response(ItemListaPreciosSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='items/(?P<item_pk>[^/.]+)')
    def eliminar_item(self, request, pk=None, item_pk=None):
        item = get_object_or_404(ItemListaPreciosProveedor, pk=item_pk, lista_precios_id=pk)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['patch'], url_path='items/(?P<item_pk>[^/.]+)/editar')
    def editar_item(self, request, pk=None, item_pk=None):
        """PATCH /api/listas-precios/{id}/items/{item_pk}/editar/"""
        item = get_object_or_404(ItemListaPreciosProveedor, pk=item_pk, lista_precios_id=pk)
        serializer = ItemListaPreciosSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='bulk/ajuste-precio')
    def bulk_ajuste_precio(self, request, pk=None):
        """
        POST /api/listas-precios/{id}/bulk/ajuste-precio/
        Body: { tipo: 'porcentaje'|'monto_fijo', valor: float, operacion: 'aumentar'|'reducir',
                item_ids: [id, ...] | null (null = todos) }
        Actualiza precio_lista_monto en masa. El signal pre_save registra historial por cada ítem.
        """
        lista = self.get_object()
        tipo      = request.data.get('tipo', 'porcentaje')
        valor     = Decimal(str(request.data.get('valor', 0)))
        operacion = request.data.get('operacion', 'aumentar')
        item_ids  = request.data.get('item_ids', None)
        motivo    = request.data.get('motivo', 'Ajuste masivo de precio.')

        if valor <= 0:
            return Response({'error': 'El valor debe ser mayor a cero.'}, status=400)

        qs = ItemListaPreciosProveedor.objects.filter(lista_precios=lista)
        if item_ids:
            qs = qs.filter(pk__in=item_ids)

        actualizados = 0
        errores = []
        with transaction.atomic():
            for item in qs.select_for_update():
                try:
                    precio_actual = item.precio_lista_monto
                    if tipo == 'porcentaje':
                        delta = precio_actual * (valor / Decimal('100'))
                    else:
                        delta = valor
                    nuevo = precio_actual + delta if operacion == 'aumentar' else precio_actual - delta
                    if nuevo <= 0:
                        errores.append(f"{item.articulo.cod_articulo}: precio resultante <= 0, saltado.")
                        continue
                    # Registrar historial manualmente con motivo personalizado
                    HistorialPrecioProveedor.objects.create(
                        item=item,
                        precio_lista_anterior=item.precio_lista,
                        precio_lista_nuevo=Money(nuevo, item.precio_lista_moneda.simbolo),
                        motivo=motivo,
                    )
                    ItemListaPreciosProveedor.objects.filter(pk=item.pk).update(precio_lista_monto=nuevo)
                    actualizados += 1
                except Exception as e:
                    errores.append(str(e))

        return Response({
            'actualizados': actualizados,
            'errores': errores,
            'mensaje': f'{actualizados} artículo(s) actualizados.'
        })

    @action(detail=True, methods=['post'], url_path='bulk/descuentos')
    def bulk_descuentos(self, request, pk=None):
        """
        POST /api/listas-precios/{id}/bulk/descuentos/
        Body: { tipo: 'adicionales'|'financieros'|'bonificacion', accion: 'reemplazar'|'agregar'|'limpiar',
                valores: [5.0, 3.0] | float, item_ids: [...] | null }
        """
        lista     = self.get_object()
        tipo      = request.data.get('tipo', 'adicionales')
        accion    = request.data.get('accion', 'reemplazar')
        valores   = request.data.get('valores', [])
        item_ids  = request.data.get('item_ids', None)

        qs = ItemListaPreciosProveedor.objects.filter(lista_precios=lista)
        if item_ids:
            qs = qs.filter(pk__in=item_ids)

        actualizados = 0
        with transaction.atomic():
            for item in qs.select_for_update():
                if tipo == 'bonificacion':
                    ItemListaPreciosProveedor.objects.filter(pk=item.pk).update(
                        bonificacion_porcentaje=Decimal(str(valores)) if valores else 0
                    )
                elif tipo == 'adicionales':
                    if accion == 'limpiar':
                        nuevos = []
                    elif accion == 'agregar':
                        nuevos = list(item.descuentos_adicionales) + [float(v) for v in valores]
                    else:
                        nuevos = [float(v) for v in valores]
                    ItemListaPreciosProveedor.objects.filter(pk=item.pk).update(descuentos_adicionales=nuevos)
                else:  # financieros
                    if accion == 'limpiar':
                        nuevos = []
                    elif accion == 'agregar':
                        nuevos = list(item.descuentos_financieros) + [float(v) for v in valores]
                    else:
                        nuevos = [float(v) for v in valores]
                    ItemListaPreciosProveedor.objects.filter(pk=item.pk).update(descuentos_financieros=nuevos)
                actualizados += 1

        return Response({'actualizados': actualizados, 'mensaje': f'{actualizados} artículo(s) actualizados.'})

    @action(detail=True, methods=['post'], url_path='bulk/copiar-lista')
    def copiar_lista(self, request, pk=None):
        """
        POST /api/listas-precios/{id}/bulk/copiar-lista/
        Body: { nombre: str, vigente_desde: date, vigente_hasta: date|null, es_principal: bool }
        Crea una nueva lista con todos los ítems de esta como base.
        """
        lista_origen = self.get_object()
        nombre       = request.data.get('nombre', f'Copia de {lista_origen.nombre}')
        from django.utils import timezone as tz
        vigente_desde = request.data.get('vigente_desde', tz.now().date().isoformat())
        vigente_hasta = request.data.get('vigente_hasta', None)
        es_principal  = request.data.get('es_principal', False)

        from compras.models import ListaPreciosProveedor as LP
        with transaction.atomic():
            nueva_lista = LP.objects.create(
                proveedor=lista_origen.proveedor,
                nombre=nombre,
                vigente_desde=vigente_desde,
                vigente_hasta=vigente_hasta or None,
                es_activa=True,
                es_principal=es_principal,
            )
            items_origen = ItemListaPreciosProveedor.objects.filter(lista_precios=lista_origen)
            nuevos_items = []
            for item in items_origen:
                nuevos_items.append(ItemListaPreciosProveedor(
                    lista_precios=nueva_lista,
                    articulo=item.articulo,
                    unidad_medida_compra=item.unidad_medida_compra,
                    precio_lista_monto=item.precio_lista_monto,
                    precio_lista_moneda=item.precio_lista_moneda,
                    bonificacion_porcentaje=item.bonificacion_porcentaje,
                    descuentos_adicionales=list(item.descuentos_adicionales),
                    descuentos_financieros=list(item.descuentos_financieros),
                    cantidad_minima=item.cantidad_minima,
                    codigo_articulo_proveedor=item.codigo_articulo_proveedor,
                ))
            ItemListaPreciosProveedor.objects.bulk_create(nuevos_items)

        from compras.serializers import ListaPreciosProveedorListSerializer
        return Response(ListaPreciosProveedorListSerializer(nueva_lista).data, status=201)

    @action(detail=True, methods=['get'], url_path='exportar-csv')
    def exportar_csv(self, request, pk=None):
        """GET /api/listas-precios/{id}/exportar-csv/"""
        import csv
        from django.http import HttpResponse
        lista = self.get_object()
        items = ItemListaPreciosProveedor.objects.filter(
            lista_precios=lista
        ).select_related('articulo', 'precio_lista_moneda', 'unidad_medida_compra')

        resp = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        resp['Content-Disposition'] = f'attachment; filename="lista_{lista.id}_{lista.nombre}.csv"'
        writer = csv.writer(resp, delimiter=';')
        writer.writerow(['cod_articulo', 'descripcion', 'unidad', 'precio_lista', 'moneda',
                         'bonificacion_%', 'descuentos_adicionales', 'descuentos_financieros',
                         'cantidad_minima', 'cod_proveedor', 'costo_efectivo'])
        for item in items:
            try:
                ce = float(item.costo_efectivo.amount)
            except Exception:
                ce = ''
            writer.writerow([
                item.articulo.cod_articulo, item.articulo.descripcion,
                item.unidad_medida_compra.simbolo if item.unidad_medida_compra else 'UN',
                str(item.precio_lista_monto).replace('.', ','),
                item.precio_lista_moneda.simbolo if item.precio_lista_moneda else 'ARS',
                str(item.bonificacion_porcentaje).replace('.', ','),
                ','.join(str(d) for d in item.descuentos_adicionales),
                ','.join(str(d) for d in item.descuentos_financieros),
                str(item.cantidad_minima).replace('.', ','),
                item.codigo_articulo_proveedor,
                str(ce).replace('.', ',') if ce != '' else '',
            ])
        return resp

    @action(detail=True, methods=['get'], url_path='historial')
    def historial_precios(self, request, pk=None):
        """GET /api/listas-precios/{id}/historial/?articulo_id=X"""
        lista = self.get_object()
        qs = HistorialPrecioProveedor.objects.filter(
            item__lista_precios=lista
        ).select_related('item__articulo').order_by('-fecha_cambio')

        articulo_id = request.query_params.get('articulo_id')
        if articulo_id:
            qs = qs.filter(item__articulo_id=articulo_id)

        data = [{
            'id':              h.id,
            'articulo':        h.item.articulo.descripcion,
            'cod_articulo':    h.item.articulo.cod_articulo,
            'precio_anterior': float(h.precio_lista_anterior.amount),
            'precio_nuevo':    float(h.precio_lista_nuevo.amount),
            'moneda':          h.precio_lista_anterior.currency.code,
            'variacion_pct':   round(
                (float(h.precio_lista_nuevo.amount) - float(h.precio_lista_anterior.amount))
                / float(h.precio_lista_anterior.amount) * 100, 2
            ) if h.precio_lista_anterior.amount else 0,
            'fecha':           h.fecha_cambio,
            'motivo':          h.motivo,
        } for h in qs[:200]]
        return Response(data)


# ─────────────────────────────────────────────
#  VISTAS AUXILIARES (admin / legacy)
# ─────────────────────────────────────────────

@staff_member_required
def get_precio_proveedor_json(request, proveedor_pk, articulo_pk):
    try:
        from djmoney.money import Money
        articulo          = get_object_or_404(Articulo, pk=articulo_pk)
        cantidad          = Decimal(request.GET.get('cantidad', 1))
        item_precio       = CostCalculatorService.get_latest_price(proveedor_pk, articulo_pk, cantidad)
        costo_final_money = None

        if item_precio:
            try:
                costo_final_money = item_precio.costo_efectivo
            except Exception:
                costo_final_money = getattr(item_precio, 'precio_lista', None)

        if not costo_final_money:
            costo_final_money = articulo.precio_costo

        if not isinstance(costo_final_money, Money):
            costo_final_money = Money(costo_final_money, 'ARS')

        moneda_obj = Moneda.objects.filter(simbolo=costo_final_money.currency.code).first()

        return JsonResponse({
            'amount':        f"{costo_final_money.amount:.4f}",
            'currency_code': costo_final_money.currency.code,
            'currency_id':   moneda_obj.id if moneda_obj else 1,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
def get_comprobante_info(request, pk):
    try:
        comp = ComprobanteCompra.objects.get(pk=pk)
        return JsonResponse({
            'saldo': str(comp.saldo_pendiente),
            'total': str(comp.total),
            'id':    comp.pk,
        })
    except ComprobanteCompra.DoesNotExist:
        return JsonResponse({'error': 'Comprobante no encontrado'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
@require_POST
def calcular_totales_compra_api(request):
    """
    Vista legacy usada por el admin de Django para calcular totales.
    Se mantiene para compatibilidad con compras/admin.py.
    """
    try:
        import json as _json
        from djmoney.money import Money as _Money
        data = _json.loads(request.body)
        items_data = data.get('items', [])

        subtotal_val = Decimal(0)
        for item in items_data:
            cantidad = Decimal(str(item.get('cantidad', 0)))
            raw_precio = item.get('precio_costo_unitario', 0)
            if isinstance(raw_precio, dict):
                monto = Decimal(str(raw_precio.get('amount', 0)))
            else:
                monto = Decimal(str(raw_precio))
            subtotal_val += cantidad * monto

        return JsonResponse({
            'subtotal':         f"{subtotal_val:,.2f}",
            'currency_symbol':  'ARS',
            'impuestos':        {},
            'total':            f"{subtotal_val:,.2f}",
        })
    except Exception:
        return JsonResponse({
            'subtotal': '0.00', 'currency_symbol': 'ARS',
            'impuestos': {}, 'total': '0.00',
        })