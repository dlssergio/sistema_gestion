# compras/cuenta_corriente_api.py
#
# ═══════════════════════════════════════════════════════════════════════════
#  MÓDULO: Cuenta Corriente de Proveedores
#  Criterio contable aplicado (Desde la perspectiva de Faro ERP):
#
#  DEBE  (+) ← Comprobantes de Compra (Facturas/ND) (aumentan nuestra deuda)
#  HABER (-) ← Órdenes de Pago, Notas de Crédito recibidas (reducen nuestra deuda)
#
#  Saldo = Σ(DEBE) - Σ(HABER)   [saldo positivo = le debemos al proveedor]
# ═══════════════════════════════════════════════════════════════════════════

from decimal import Decimal
from django.db.models import Sum, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Proveedor, ComprobanteCompra, OrdenPago, OrdenPagoImputacion, OrdenPagoValor


# ─── Utilidades ────────────────────────────────────────────────────────────

def _dec(v):
    try:
        return Decimal(str(v)) if v is not None else Decimal('0')
    except Exception:
        return Decimal('0')


def _f(v):
    return float(_dec(v))


def _iso(dt):
    return dt.isoformat() if dt else None


def _parse_date(s):
    if not s:
        return None
    try:
        import datetime
        return datetime.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _num_comp(comp):
    letra = (comp.letra or '').strip()
    pv = int(comp.punto_venta or 0)
    num = int(comp.numero or 0)
    return f"{letra} {pv:05d}-{num:08d}".strip()


def _num_op(op):
    return f"OP {int(op.numero or 0):08d}"


def _signo_comp(comp):
    """
    Retorna +1 si el comprobante es DEBE (Factura de proveedor, ND que nos envían)
    o -1 si es HABER (Nota de crédito que nos envían a favor).
    """
    tc = comp.tipo_comprobante
    if tc and tc.es_nota_credito:
        return -1
    return 1


# ─── CuentaCorrienteProveedoresService ─────────────────────────────────────

class CuentaCorrienteProveedoresService:

    @classmethod
    def build_extracto(cls, proveedor, *, fecha_desde=None, fecha_hasta=None,
                       tipo_filtro='', page=1, page_size=50):
        saldo_anterior = Decimal('0')
        if fecha_desde:
            saldo_anterior = cls._saldo_al_cierre(proveedor, hasta=fecha_desde - timezone.timedelta(days=1))

        movs = cls._movimientos(proveedor, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
                                tipo_filtro=tipo_filtro)

        acum = saldo_anterior
        for m in movs:
            acum += _dec(m['debe']) - _dec(m['haber'])
            m['saldo'] = _f(acum)

        total_movs = len(movs)
        page_size = min(max(1, page_size), 200)
        page = max(1, page)
        total_pages = max(1, -(-total_movs // page_size))
        page = min(page, total_pages)
        movs_pagina = movs[(page - 1) * page_size: page * page_size]

        saldo_final = _f(acum)

        return {
            'saldo_anterior': _f(saldo_anterior),
            'saldo_final': saldo_final,
            'movimientos': movs_pagina,
            'paginacion': {
                'total': total_movs,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
            },
        }

    @classmethod
    def build_resumen(cls, proveedor, *, fecha_desde=None, fecha_hasta=None):
        saldo_anterior = Decimal('0')
        if fecha_desde:
            saldo_anterior = cls._saldo_al_cierre(proveedor, hasta=fecha_desde - timezone.timedelta(days=1))

        movs = cls._movimientos(proveedor, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)

        total_debe = sum(_dec(m['debe']) for m in movs)
        total_haber = sum(_dec(m['haber']) for m in movs)
        saldo_periodo = total_debe - total_haber
        saldo_final = saldo_anterior + saldo_periodo

        desglose = {}
        for m in movs:
            key = m['tipo']
            if key not in desglose:
                desglose[key] = {'tipo': key, 'clase': m['clase'], 'cantidad': 0, 'debe': 0.0, 'haber': 0.0}
            desglose[key]['cantidad'] += 1
            desglose[key]['debe'] = round(desglose[key]['debe'] + _f(m['debe']), 2)
            desglose[key]['haber'] = round(desglose[key]['haber'] + _f(m['haber']), 2)

        return {
            'saldo_anterior': _f(saldo_anterior),
            'total_debe': _f(total_debe),
            'total_haber': _f(total_haber),
            'saldo_periodo': _f(saldo_periodo),
            'saldo_final': _f(saldo_final),
            'cantidad_movimientos': len(movs),
            'desglose': sorted(desglose.values(), key=lambda x: x['tipo']),
        }

    @classmethod
    def _saldo_al_cierre(cls, proveedor, hasta):
        comps = ComprobanteCompra.objects.filter(
            proveedor=proveedor,
            estado=ComprobanteCompra.Estado.CONFIRMADO,
            condicion_compra=ComprobanteCompra.CondicionCompra.CTA_CTE,
            fecha__date__lte=hasta,
        ).select_related('tipo_comprobante')

        debe_total = Decimal('0')
        haber_total = Decimal('0')
        for c in comps:
            signo = _signo_comp(c)
            if signo > 0:
                debe_total += _dec(c.total)
            else:
                haber_total += _dec(c.total)

        ordenes = OrdenPago.objects.filter(
            proveedor=proveedor,
            estado=OrdenPago.Estado.CONFIRMADO,
            fecha__date__lte=hasta,
        ).aggregate(total=Sum('monto_total'))

        haber_total += _dec(ordenes.get('total'))

        return debe_total - haber_total

    @classmethod
    def _movimientos(cls, proveedor, *, fecha_desde=None, fecha_hasta=None, tipo_filtro=''):
        movs = []
        incl_comp = tipo_filtro in ('', 'comprobante')
        incl_op = tipo_filtro in ('', 'orden_pago')

        if incl_comp:
            qs = (
                ComprobanteCompra.objects
                .filter(
                    proveedor=proveedor,
                    estado=ComprobanteCompra.Estado.CONFIRMADO,
                    condicion_compra=ComprobanteCompra.CondicionCompra.CTA_CTE,
                )
                .select_related('tipo_comprobante')
                .order_by('fecha', 'numero')
            )
            if fecha_desde: qs = qs.filter(fecha__date__gte=fecha_desde)
            if fecha_hasta: qs = qs.filter(fecha__date__lte=fecha_hasta)

            for c in qs:
                signo = _signo_comp(c)
                tipo_nom = c.tipo_comprobante.nombre if c.tipo_comprobante else 'Factura'
                debe = _f(c.total) if signo > 0 else 0.0
                haber = _f(c.total) if signo < 0 else 0.0
                movs.append({
                    'id': c.pk,
                    'fecha': _iso(c.fecha),
                    'tipo': tipo_nom,
                    'clase': 'comprobante',
                    'es_nc': signo < 0,
                    'numero': _num_comp(c),
                    'debe': debe,
                    'haber': haber,
                    'saldo': 0.0,
                    'ref_id': c.pk,
                    'saldo_pendiente': _f(c.saldo_pendiente),
                })

        if incl_op:
            qs = (
                OrdenPago.objects
                .filter(
                    proveedor=proveedor,
                    estado=OrdenPago.Estado.CONFIRMADO,
                )
                .order_by('fecha', 'numero')
            )
            if fecha_desde: qs = qs.filter(fecha__date__gte=fecha_desde)
            if fecha_hasta: qs = qs.filter(fecha__date__lte=fecha_hasta)

            for op in qs:
                movs.append({
                    'id': op.pk,
                    'fecha': _iso(op.fecha),
                    'tipo': 'Orden de Pago',
                    'clase': 'orden_pago',
                    'es_nc': False,
                    'numero': _num_op(op),
                    'debe': 0.0,
                    'haber': _f(op.monto_total),
                    'saldo': 0.0,
                    'ref_id': op.pk,
                    'saldo_pendiente': None,
                })

        movs.sort(key=lambda x: (x['fecha'] or '', x['id']))
        return movs

    @classmethod
    def comprobantes_impagos(cls, proveedor):
        hoy = timezone.localdate()
        dias_plazo = int(proveedor.plazo_pago_dias or 0)
        result = []

        for c in (
                ComprobanteCompra.objects
                        .filter(proveedor=proveedor,
                                estado=ComprobanteCompra.Estado.CONFIRMADO,
                                saldo_pendiente__gt=0)
                        .select_related('tipo_comprobante')
                        .order_by('fecha', 'numero')
        ):
            fecha_base = c.fecha.date() if c.fecha else hoy
            fecha_venc = fecha_base + timezone.timedelta(days=dias_plazo)
            vencido = fecha_venc < hoy
            dias_mora = max(0, (hoy - fecha_venc).days) if vencido else 0

            result.append({
                'id': c.pk,
                'fecha': _iso(c.fecha),
                'fecha_vencimiento': fecha_venc.isoformat(),
                'tipo': c.tipo_comprobante.nombre if c.tipo_comprobante else 'Comprobante',
                'numero': _num_comp(c),
                'total': _f(c.total),
                'saldo_pendiente': _f(c.saldo_pendiente),
                'pagado': _f(c.total - c.saldo_pendiente),
                'vencido': vencido,
                'dias_mora': dias_mora,
            })
        return result

    @classmethod
    def ordenes_pago_detalle(cls, proveedor):
        result = []
        for op in (
                OrdenPago.objects
                        .filter(proveedor=proveedor, estado=OrdenPago.Estado.CONFIRMADO)
                        .select_related('created_by')
                        .prefetch_related(
                    'imputaciones__comprobante__tipo_comprobante',
                    'valores__tipo', 'valores__origen',
                )
                        .order_by('-fecha', '-numero')[:50]
        ):
            result.append({
                'id': op.pk,
                'numero': _num_op(op),
                'fecha': _iso(op.fecha),
                'monto_total': _f(op.monto_total),
                'observaciones': op.observaciones or '',
                'created_by': (op.created_by.get_full_name() or op.created_by.username) if op.created_by else None,
                'imputaciones': [
                    {
                        'comp_id': i.comprobante.pk,
                        'comp_tipo': i.comprobante.tipo_comprobante.nombre if i.comprobante.tipo_comprobante else '—',
                        'comp_numero': _num_comp(i.comprobante),
                        'monto': _f(i.monto_imputado),
                    }
                    for i in op.imputaciones.all()
                ],
                'valores': [
                    {
                        'tipo': v.tipo.nombre if v.tipo else '—',
                        'origen': v.origen.nombre if v.origen else '—',
                        'monto': _f(v.monto),
                        'referencia': v.referencia or '',
                    }
                    for v in op.valores.all()
                ],
            })
        return result

    @classmethod
    def kpis_proveedor(cls, proveedor):
        hoy = timezone.localdate()
        dias_plazo = int(proveedor.plazo_pago_dias or 0)

        saldo_total = Decimal('0')
        deuda_vencida = Decimal('0')
        deuda_no_vencida = Decimal('0')
        aging = {'0_30': Decimal('0'), '31_60': Decimal('0'), '61_90': Decimal('0'), '90_plus': Decimal('0')}
        n_impagos = 0

        for c in ComprobanteCompra.objects.filter(
                proveedor=proveedor,
                estado=ComprobanteCompra.Estado.CONFIRMADO,
                saldo_pendiente__gt=0,
        ):
            s = _dec(c.saldo_pendiente)
            if s <= 0: continue
            n_impagos += 1
            saldo_total += s
            fecha_base = c.fecha.date() if c.fecha else hoy
            fecha_venc = fecha_base + timezone.timedelta(days=dias_plazo)
            if fecha_venc < hoy:
                deuda_vencida += s
                dias_mora = (hoy - fecha_venc).days
                if dias_mora <= 30:
                    aging['0_30'] += s
                elif dias_mora <= 60:
                    aging['31_60'] += s
                elif dias_mora <= 90:
                    aging['61_90'] += s
                else:
                    aging['90_plus'] += s
            else:
                deuda_no_vencida += s

        limite = _dec(proveedor.limite_credito or 0)
        disponible = limite - saldo_total

        if limite > 0 and disponible < 0:
            riesgo = 'EXCEDIDO'
        elif deuda_vencida > 0:
            riesgo = 'MORA'
        else:
            riesgo = 'AL_DIA'

        fecha_30d = hoy - timezone.timedelta(days=30)
        compras_30d = _f(
            ComprobanteCompra.objects.filter(
                proveedor=proveedor, estado=ComprobanteCompra.Estado.CONFIRMADO, fecha__date__gte=fecha_30d
            ).aggregate(t=Sum('total'))['t']
        )
        pagos_30d = _f(
            OrdenPago.objects.filter(
                proveedor=proveedor, estado=OrdenPago.Estado.CONFIRMADO, fecha__date__gte=fecha_30d
            ).aggregate(t=Sum('monto_total'))['t']
        )

        return {
            'saldo_total': _f(saldo_total),
            'deuda_vencida': _f(deuda_vencida),
            'deuda_no_vencida': _f(deuda_no_vencida),
            'limite_credito': _f(limite),
            'credito_disponible': _f(disponible),
            'comprobantes_impagos': n_impagos,
            'riesgo': riesgo,
            'plazo_pago_dias': dias_plazo,
            'aging': {
                'bucket_0_30': _f(aging['0_30']),
                'bucket_31_60': _f(aging['31_60']),
                'bucket_61_90': _f(aging['61_90']),
                'bucket_90_plus': _f(aging['90_plus']),
            },
            'kpis': {
                'total_comprado_30d': compras_30d,
                'total_pagado_30d': pagos_30d,
            },
        }


# ─── ENDPOINTS API ─────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def cc_proveedor_api(request, pk):
    proveedor = get_object_or_404(Proveedor.objects.select_related('entidad'), pk=pk)
    fecha_desde = _parse_date(request.query_params.get('fecha_desde'))
    fecha_hasta = _parse_date(request.query_params.get('fecha_hasta'))
    tipo_filtro = (request.query_params.get('tipo') or '').lower().strip()
    modo = (request.query_params.get('modo') or 'extracto').lower()

    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except:
        page = 1
    try:
        page_size = min(200, max(1, int(request.query_params.get('page_size', 50))))
    except:
        page_size = 50

    data = {}
    if modo == 'resumen':
        data['resumen_periodo'] = CuentaCorrienteProveedoresService.build_resumen(proveedor, fecha_desde=fecha_desde,
                                                                                  fecha_hasta=fecha_hasta)
    else:
        data.update(CuentaCorrienteProveedoresService.build_extracto(proveedor, fecha_desde=fecha_desde,
                                                                     fecha_hasta=fecha_hasta, tipo_filtro=tipo_filtro,
                                                                     page=page, page_size=page_size))

    data['kpis'] = CuentaCorrienteProveedoresService.kpis_proveedor(proveedor)
    data['comprobantes_impagos'] = CuentaCorrienteProveedoresService.comprobantes_impagos(proveedor)
    data['ordenes_pago'] = CuentaCorrienteProveedoresService.ordenes_pago_detalle(proveedor)
    data['proveedor'] = {
        'id': proveedor.pk,
        'codigo': proveedor.codigo_proveedor,
        'razon_social': proveedor.entidad.razon_social,
        'cuit': proveedor.entidad.cuit,
        'limite_credito': _f(proveedor.limite_credito),
    }
    return Response(data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def compras_impagas_api(request, pk):
    proveedor = get_object_or_404(Proveedor.objects.select_related('entidad'), pk=pk)
    data = CuentaCorrienteProveedoresService.comprobantes_impagos(proveedor)
    return Response({'results': data, 'count': len(data)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ordenes_pago_api(request, pk):
    proveedor = get_object_or_404(Proveedor.objects.select_related('entidad'), pk=pk)
    data = CuentaCorrienteProveedoresService.ordenes_pago_detalle(proveedor)
    return Response({'results': data, 'count': len(data)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def resumen_cartera_proveedores_api(request):
    hoy = timezone.localdate()
    fecha_hasta = _parse_date(request.query_params.get('fecha_hasta')) or hoy
    search = (request.query_params.get('search') or '').strip().lower()
    con_saldo = request.query_params.get('con_saldo', '').lower() in ('true', '1', 'yes')

    ids_con_comp = set(ComprobanteCompra.objects.filter(estado=ComprobanteCompra.Estado.CONFIRMADO,
                                                        fecha__date__lte=fecha_hasta).values_list('proveedor_id',
                                                                                                  flat=True))
    ids_con_op = set(
        OrdenPago.objects.filter(estado=OrdenPago.Estado.CONFIRMADO, fecha__date__lte=fecha_hasta).values_list(
            'proveedor_id', flat=True))

    proveedores_qs = Proveedor.objects.filter(pk__in=(ids_con_comp | ids_con_op)).select_related('entidad')

    resultado = []
    for p in proveedores_qs:
        saldo = CuentaCorrienteProveedoresService._saldo_al_cierre(p, hasta=fecha_hasta)
        if con_saldo and saldo <= 0: continue

        deuda_vencida = Decimal('0')
        dias_plazo = int(p.plazo_pago_dias or 0)
        for comp in ComprobanteCompra.objects.filter(proveedor=p, estado=ComprobanteCompra.Estado.CONFIRMADO,
                                                     saldo_pendiente__gt=0, fecha__date__lte=fecha_hasta):
            if ((comp.fecha.date() if comp.fecha else hoy) + timezone.timedelta(days=dias_plazo)) < fecha_hasta:
                deuda_vencida += _dec(comp.saldo_pendiente)

        razon = p.entidad.razon_social if p.entidad else f'Prov #{p.pk}'
        if search and not any(
                search in x.lower() for x in [razon, p.entidad.cuit if p.entidad else '', p.codigo_proveedor or '']):
            continue

        resultado.append({
            'id': p.pk,
            'codigo': p.codigo_proveedor or '',
            'razon_social': razon,
            'saldo_total': _f(saldo),
            'deuda_vencida': _f(deuda_vencida),
        })

    resultado.sort(key=lambda x: x['saldo_total'], reverse=True)
    return Response({'results': resultado, 'totales': {'proveedores': len(resultado),
                                                       'saldo_total': sum(r['saldo_total'] for r in resultado)}})