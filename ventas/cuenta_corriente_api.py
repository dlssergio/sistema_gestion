# ventas/cuenta_corriente_api.py
#
# ═══════════════════════════════════════════════════════════════════════════
#  MÓDULO: Cuenta Corriente de Clientes
#  Criterio contable aplicado:
#
#  DEBE  (+) ← Facturas CC, Notas de Débito (aumentan la deuda del cliente)
#  HABER (-) ← Recibos de cobranza, Notas de Crédito (reducen la deuda)
#
#  Saldo = Σ(DEBE) - Σ(HABER)   [saldo positivo = cliente nos debe]
#
#  RESUMEN DE CUENTA (a una fecha):
#    Saldo anterior  = movimientos ANTES de fecha_desde
#    Movimientos     = movimientos ENTRE fecha_desde y fecha_hasta
#    Saldo final     = saldo_anterior + Σ(período)
#
#  ESTADO DE CUENTA (extracción bancaria):
#    Todos los movimientos con saldo acumulado cronológico.
# ═══════════════════════════════════════════════════════════════════════════

from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Cliente, ComprobanteVenta, Recibo, ReciboImputacion, ReciboValor


# ─── utilidades ────────────────────────────────────────────────────────────

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
    pv    = int(comp.punto_venta or 0)
    num   = int(comp.numero or 0)
    return f"{letra} {pv:05d}-{num:08d}".strip()

def _num_recibo(rec):
    return f"X {int(rec.numero or 0):08d}"

def _signo_comp(comp):
    """
    Retorna +1 si el comprobante es DEBE (factura, ND) o -1 si es HABER (NC).
    Usa el campo es_nota_credito del TipoComprobante.
    """
    tc = comp.tipo_comprobante
    if tc and tc.es_nota_credito:
        return -1
    return 1


# ─── CuentaCorrienteService ────────────────────────────────────────────────

class CuentaCorrienteService:

    # ── Punto de entrada ──────────────────────────────────────────────────
    @classmethod
    def build_extracto(cls, cliente, *, fecha_desde=None, fecha_hasta=None,
                       tipo_filtro='', page=1, page_size=50):
        hoy = timezone.localdate()

        saldo_anterior = Decimal('0')
        if fecha_desde:
            saldo_anterior = cls._saldo_al_cierre(cliente, hasta=fecha_desde - timezone.timedelta(days=1))

        movs = cls._movimientos(cliente, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
                                tipo_filtro=tipo_filtro)

        acum = saldo_anterior
        for m in movs:
            acum += _dec(m['debe']) - _dec(m['haber'])
            m['saldo'] = _f(acum)

        total_movs = len(movs)
        page_size  = min(max(1, page_size), 200)
        page       = max(1, page)
        total_pages = max(1, -(-total_movs // page_size))
        page        = min(page, total_pages)
        movs_pagina = movs[(page-1)*page_size : page*page_size]

        saldo_final = _f(acum)

        return {
            'saldo_anterior':  _f(saldo_anterior),
            'saldo_final':     saldo_final,
            'movimientos':     movs_pagina,
            'paginacion': {
                'total':       total_movs,
                'page':        page,
                'page_size':   page_size,
                'total_pages': total_pages,
            },
        }

    @classmethod
    def build_resumen(cls, cliente, *, fecha_desde=None, fecha_hasta=None):
        hoy = timezone.localdate()

        saldo_anterior = Decimal('0')
        if fecha_desde:
            saldo_anterior = cls._saldo_al_cierre(cliente, hasta=fecha_desde - timezone.timedelta(days=1))

        movs = cls._movimientos(cliente, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)

        total_debe  = sum(_dec(m['debe'])  for m in movs)
        total_haber = sum(_dec(m['haber']) for m in movs)
        saldo_periodo  = total_debe - total_haber
        saldo_final    = saldo_anterior + saldo_periodo

        desglose = {}
        for m in movs:
            key = m['tipo']
            if key not in desglose:
                desglose[key] = {'tipo': key, 'clase': m['clase'], 'cantidad': 0, 'debe': 0.0, 'haber': 0.0}
            desglose[key]['cantidad'] += 1
            desglose[key]['debe']     = round(desglose[key]['debe']  + _f(m['debe']),  2)
            desglose[key]['haber']    = round(desglose[key]['haber'] + _f(m['haber']), 2)

        return {
            'saldo_anterior':  _f(saldo_anterior),
            'total_debe':      _f(total_debe),
            'total_haber':     _f(total_haber),
            'saldo_periodo':   _f(saldo_periodo),
            'saldo_final':     _f(saldo_final),
            'cantidad_movimientos': len(movs),
            'desglose':        sorted(desglose.values(), key=lambda x: x['tipo']),
        }

    # ── Saldo al cierre de una fecha ──────────────────────────────────────
    @classmethod
    def _saldo_al_cierre(cls, cliente, hasta):
        comps = ComprobanteVenta.objects.filter(
            cliente=cliente,
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            condicion_venta=ComprobanteVenta.CondicionVenta.CTA_CTE,
            fecha__date__lte=hasta,
        ).select_related('tipo_comprobante')

        debe_total = Decimal('0')
        haber_total = Decimal('0')
        for c in comps:
            codigo_afip = getattr(c.tipo_comprobante, 'codigo_afip', '')
            if codigo_afip in ['091', '092', '991', '992', 'remito', 'pedido']:
                continue

            signo = _signo_comp(c)
            if signo > 0:
                debe_total += _dec(c.total)
            else:
                haber_total += _dec(c.total)

        recibos = Recibo.objects.filter(
            cliente=cliente,
            estado=Recibo.Estado.CONFIRMADO,
            origen=Recibo.Origen.COBRANZA,
            fecha__date__lte=hasta,
        ).aggregate(total=Sum('monto_total'))

        haber_total += _dec(recibos.get('total'))
        return debe_total - haber_total

    # ── Movimientos del período ───────────────────────────────────────────
    @classmethod
    def _movimientos(cls, cliente, *, fecha_desde=None, fecha_hasta=None, tipo_filtro=''):
        movs = []
        incl_comp = tipo_filtro in ('', 'comprobante')
        incl_recibo = tipo_filtro in ('', 'recibo')

        if incl_comp:
            qs = (
                ComprobanteVenta.objects
                .filter(
                    cliente=cliente,
                    estado=ComprobanteVenta.Estado.CONFIRMADO,
                    condicion_venta=ComprobanteVenta.CondicionVenta.CTA_CTE,
                )
                .select_related('tipo_comprobante')
                .order_by('fecha', 'numero')
            )
            if fecha_desde:
                qs = qs.filter(fecha__date__gte=fecha_desde)
            if fecha_hasta:
                qs = qs.filter(fecha__date__lte=fecha_hasta)

            for c in qs:
                codigo_afip = getattr(c.tipo_comprobante, 'codigo_afip', '')
                if codigo_afip in ['091', '092', '991', '992', 'remito', 'pedido']:
                    continue

                signo = _signo_comp(c)
                tipo_nom = c.tipo_comprobante.nombre if c.tipo_comprobante else 'Comprobante'
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
                    'estado_pago': c.estado_pago,
                    'saldo_pendiente': _f(c.saldo_pendiente),
                })

        if incl_recibo:
            qs = (
                Recibo.objects
                .filter(
                    cliente=cliente,
                    estado=Recibo.Estado.CONFIRMADO,
                    origen=Recibo.Origen.COBRANZA,
                )
                .order_by('fecha', 'numero')
            )
            if fecha_desde:
                qs = qs.filter(fecha__date__gte=fecha_desde)
            if fecha_hasta:
                qs = qs.filter(fecha__date__lte=fecha_hasta)

            for r in qs:
                movs.append({
                    'id': r.pk,
                    'fecha': _iso(r.fecha),
                    'tipo': 'Recibo',
                    'clase': 'recibo',
                    'es_nc': False,
                    'numero': _num_recibo(r),
                    'debe': 0.0,
                    'haber': _f(r.monto_total),
                    'saldo': 0.0,
                    'ref_id': r.pk,
                    'estado_pago': None,
                    'saldo_pendiente': None,
                })

        movs.sort(key=lambda x: (x['fecha'] or '', x['id']))
        return movs

    # ── Comprobantes impagos ──────────────────────────────────────────────
    @classmethod
    def comprobantes_impagos(cls, cliente):
        hoy      = timezone.localdate()
        dias_vec = int(cliente.dias_vencimiento or 0)
        result   = []

        for c in (
            ComprobanteVenta.objects
            .filter(cliente=cliente,
                    estado=ComprobanteVenta.Estado.CONFIRMADO,
                    saldo_pendiente__gt=0)
            .select_related('tipo_comprobante')
            .order_by('fecha', 'numero')
        ):
            # Escudo: Evitamos que notas de pedido con saldo muestren como impagos
            codigo_afip = getattr(c.tipo_comprobante, 'codigo_afip', '')
            if codigo_afip in ['091', '092', '991', '992', 'remito', 'pedido']:
                continue

            fecha_base = c.fecha.date() if c.fecha else hoy
            fecha_venc = fecha_base + timezone.timedelta(days=dias_vec)
            vencido    = fecha_venc < hoy
            dias_mora  = max(0, (hoy - fecha_venc).days) if vencido else 0

            result.append({
                'id':                c.pk,
                'fecha':             _iso(c.fecha),
                'fecha_vencimiento': fecha_venc.isoformat(),
                'tipo':              c.tipo_comprobante.nombre if c.tipo_comprobante else 'Comprobante',
                'numero':            _num_comp(c),
                'total':             _f(c.total),
                'saldo_pendiente':   _f(c.saldo_pendiente),
                'pagado':            _f(c.total - c.saldo_pendiente),
                'vencido':           vencido,
                'dias_mora':         dias_mora,
                'estado_pago':       c.estado_pago,
            })
        return result

    # ── Recibos con detalle ───────────────────────────────────────────────
    @classmethod
    def recibos_detalle(cls, cliente):
        result = []
        for r in (
            Recibo.objects
            .filter(cliente=cliente, estado=Recibo.Estado.CONFIRMADO)
            .select_related('created_by')
            .prefetch_related(
                'imputaciones__comprobante__tipo_comprobante',
                'valores__tipo', 'valores__destino',
            )
            .order_by('-fecha', '-numero')[:50]
        ):
            result.append({
                'id':           r.pk,
                'numero':       _num_recibo(r),
                'fecha':        _iso(r.fecha),
                'origen':       r.origen,
                'monto_total':  _f(r.monto_total),
                'observaciones':r.observaciones or '',
                'created_by':   (r.created_by.get_full_name() or r.created_by.username) if r.created_by else None,
                'imputaciones': [
                    {
                        'comp_id':     i.comprobante.pk,
                        'comp_tipo':   i.comprobante.tipo_comprobante.nombre if i.comprobante.tipo_comprobante else '—',
                        'comp_numero': _num_comp(i.comprobante),
                        'monto':       _f(i.monto_imputado),
                    }
                    for i in r.imputaciones.all()
                ],
                'valores': [
                    {
                        'tipo':       v.tipo.nombre if v.tipo else '—',
                        'destino':    v.destino.nombre if v.destino else '—',
                        'monto':      _f(v.monto),
                        'referencia': v.referencia or '',
                    }
                    for v in r.valores.all()
                ],
            })
        return result

    # ── Resumen financiero (KPIs del header) ──────────────────────────────
    @classmethod
    def kpis_cliente(cls, cliente):
        hoy      = timezone.localdate()
        dias_vec = int(cliente.dias_vencimiento or 0)

        saldo_total      = Decimal('0')
        deuda_vencida    = Decimal('0')
        deuda_no_vencida = Decimal('0')
        aging = {'0_30': Decimal('0'), '31_60': Decimal('0'), '61_90': Decimal('0'), '90_plus': Decimal('0')}
        n_impagos = 0

        for c in ComprobanteVenta.objects.filter(
            cliente=cliente,
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            saldo_pendiente__gt=0,
        ):
            # Escudo para no contar KPIs de remitos
            codigo_afip = getattr(c.tipo_comprobante, 'codigo_afip', '')
            if codigo_afip in ['091', '092', '991', '992', 'remito', 'pedido']:
                continue

            s = _dec(c.saldo_pendiente)
            if s <= 0:
                continue
            n_impagos  += 1
            saldo_total += s
            fecha_base   = c.fecha.date() if c.fecha else hoy
            fecha_venc   = fecha_base + timezone.timedelta(days=dias_vec)
            if fecha_venc < hoy:
                deuda_vencida += s
                dias_mora = (hoy - fecha_venc).days
                if   dias_mora <= 30: aging['0_30']    += s
                elif dias_mora <= 60: aging['31_60']   += s
                elif dias_mora <= 90: aging['61_90']   += s
                else:                 aging['90_plus'] += s
            else:
                deuda_no_vencida += s

        limite    = _dec(cliente.limite_credito or 0)
        disponible = limite - saldo_total

        if disponible < 0 or aging['90_plus'] > 0:
            riesgo = 'EXCEDIDO'
        elif deuda_vencida > 0:
            riesgo = 'SEGUIMIENTO'
        else:
            riesgo = 'NORMAL'

        fecha_30d  = hoy - timezone.timedelta(days=30)
        fecha_90d  = hoy - timezone.timedelta(days=90)
        fecha_12m  = hoy - timezone.timedelta(days=365)
        base_qs    = ComprobanteVenta.objects.filter(
            cliente=cliente, estado=ComprobanteVenta.Estado.CONFIRMADO
        ).exclude(tipo_comprobante__codigo_afip__in=['091', '092', '991', '992', 'remito', 'pedido'])

        def _venta(desde):
            r = base_qs.filter(fecha__date__gte=desde).aggregate(t=Sum('total'), c=Count('id'))
            return _f(r['t']), (r['c'] or 0)

        v30, c30   = _venta(fecha_30d)
        v90, c90   = _venta(fecha_90d)
        v12, c12   = _venta(fecha_12m)
        ticket_90  = round(v90 / c90, 2) if c90 else 0.0

        cobrado_30 = _f(
            Recibo.objects.filter(
                cliente=cliente, estado=Recibo.Estado.CONFIRMADO,
                fecha__date__gte=fecha_30d,
            ).aggregate(t=Sum('monto_total'))['t']
        )

        ultima = base_qs.order_by('-fecha').values_list('fecha', flat=True).first()
        dias_sin = (hoy - ultima.date()).days if ultima else None

        return {
            'saldo_total':           _f(saldo_total),
            'deuda_vencida':         _f(deuda_vencida),
            'deuda_no_vencida':      _f(deuda_no_vencida),
            'limite_credito':        _f(limite),
            'credito_disponible':    _f(disponible),
            'comprobantes_impagos':  n_impagos,
            'riesgo':                riesgo,
            'permite_cta_cte':       cliente.permite_cta_cte,
            'dias_vencimiento':      dias_vec,
            'aging': {
                'bucket_0_30':    _f(aging['0_30']),
                'bucket_31_60':   _f(aging['31_60']),
                'bucket_61_90':   _f(aging['61_90']),
                'bucket_90_plus': _f(aging['90_plus']),
            },
            'kpis': {
                'total_vendido_30d':        v30,
                'count_30d':                c30,
                'total_vendido_90d':        v90,
                'count_90d':                c90,
                'total_vendido_12m':        v12,
                'count_12m':                c12,
                'ticket_promedio_90d':      ticket_90,
                'dias_desde_ultima_compra': dias_sin,
                'total_cobrado_30d':        cobrado_30,
            },
        }


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def cuenta_corriente_api(request, pk):
    cliente = get_object_or_404(
        Cliente.objects.select_related('entidad', 'vendedor'), pk=pk
    )
    fecha_desde  = _parse_date(request.query_params.get('fecha_desde'))
    fecha_hasta  = _parse_date(request.query_params.get('fecha_hasta'))
    tipo_filtro  = (request.query_params.get('tipo') or '').lower().strip()
    modo         = (request.query_params.get('modo') or 'extracto').lower()

    try:    page      = max(1, int(request.query_params.get('page', 1)))
    except: page      = 1
    try:    page_size = min(200, max(1, int(request.query_params.get('page_size', 50))))
    except: page_size = 50

    data = {}

    if modo == 'resumen':
        data['resumen_periodo'] = CuentaCorrienteService.build_resumen(
            cliente, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
        )
    else:
        extracto = CuentaCorrienteService.build_extracto(
            cliente, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
            tipo_filtro=tipo_filtro, page=page, page_size=page_size
        )
        data.update(extracto)

    data['kpis']                 = CuentaCorrienteService.kpis_cliente(cliente)
    data['comprobantes_impagos'] = CuentaCorrienteService.comprobantes_impagos(cliente)
    data['recibos']              = CuentaCorrienteService.recibos_detalle(cliente)
    data['cliente'] = {
        'id':              cliente.pk,
        'codigo_cliente':  cliente.codigo_cliente,
        'razon_social':    cliente.entidad.razon_social,
        'cuit':            cliente.entidad.cuit,
        'email':           cliente.contacto_email or cliente.entidad.email,
        'permite_cta_cte': cliente.permite_cta_cte,
        'limite_credito':  _f(cliente.limite_credito),
        'dias_vencimiento':int(cliente.dias_vencimiento or 0),
        'vendedor':        (
            cliente.vendedor.get_full_name() or cliente.vendedor.username
            if cliente.vendedor else None
        ),
    }

    return Response(data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def comprobantes_impagos_api(request, pk):
    cliente = get_object_or_404(Cliente.objects.select_related('entidad'), pk=pk)
    data    = CuentaCorrienteService.comprobantes_impagos(cliente)
    return Response({'results': data, 'count': len(data)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recibos_cliente_api(request, pk):
    cliente = get_object_or_404(Cliente.objects.select_related('entidad'), pk=pk)
    data    = CuentaCorrienteService.recibos_detalle(cliente)
    return Response({'results': data, 'count': len(data)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def resumen_cartera_api(request):
    hoy = timezone.localdate()
    fecha_hasta  = _parse_date(request.query_params.get('fecha_hasta')) or hoy
    search       = (request.query_params.get('search') or '').strip().lower()
    riesgo_fil   = (request.query_params.get('riesgo') or '').upper()
    con_saldo    = request.query_params.get('con_saldo', '').lower() in ('true', '1', 'yes')
    ordering     = request.query_params.get('ordering', '-saldo_total')

    ids_con_comp = set(
        ComprobanteVenta.objects
        .filter(estado=ComprobanteVenta.Estado.CONFIRMADO,
                fecha__date__lte=fecha_hasta)
        .values_list('cliente_id', flat=True).distinct()
    )
    ids_con_rec = set(
        Recibo.objects
        .filter(estado=Recibo.Estado.CONFIRMADO,
                fecha__date__lte=fecha_hasta)
        .values_list('cliente_id', flat=True).distinct()
    )
    all_ids = ids_con_comp | ids_con_rec

    clientes_qs = (
        Cliente.objects.filter(pk__in=all_ids)
        .select_related('entidad', 'entidad__situacion_iva')
    )

    resultado = []
    for c in clientes_qs:
        saldo = CuentaCorrienteService._saldo_al_cierre(c, hasta=fecha_hasta)

        if con_saldo and saldo <= 0:
            continue

        deuda_vencida = Decimal('0')
        dias_vec = int(c.dias_vencimiento or 0)
        for comp in ComprobanteVenta.objects.filter(
            cliente=c,
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            saldo_pendiente__gt=0,
            fecha__date__lte=fecha_hasta,
        ):
            codigo_afip = getattr(comp.tipo_comprobante, 'codigo_afip', '')
            if codigo_afip in ['091', '092', '991', '992', 'remito', 'pedido']:
                continue

            fecha_venc = (comp.fecha.date() if comp.fecha else hoy) + timezone.timedelta(days=dias_vec)
            if fecha_venc < fecha_hasta:
                deuda_vencida += _dec(comp.saldo_pendiente)

        limite = _dec(c.limite_credito or 0)
        if limite > 0 and saldo > limite:
            riesgo = 'EXCEDIDO'
        elif deuda_vencida > 0:
            riesgo = 'SEGUIMIENTO'
        else:
            riesgo = 'NORMAL'

        if riesgo_fil and riesgo != riesgo_fil:
            continue

        razon = c.entidad.razon_social if c.entidad else f'Cliente #{c.pk}'
        cuit  = c.entidad.cuit if c.entidad else ''
        if search and not any(search in x.lower() for x in [razon, cuit, c.codigo_cliente or '']):
            continue

        ultimo_mov = ComprobanteVenta.objects.filter(
            cliente=c, estado=ComprobanteVenta.Estado.CONFIRMADO,
            fecha__date__lte=fecha_hasta,
        ).exclude(tipo_comprobante__codigo_afip__in=['091', '092', '991', '992', 'remito', 'pedido']).order_by('-fecha').values_list('fecha', flat=True).first()

        resultado.append({
            'id':              c.pk,
            'codigo':          c.codigo_cliente or '',
            'razon_social':    razon,
            'cuit':            cuit,
            'permite_cta_cte': c.permite_cta_cte,
            'limite_credito':  _f(limite),
            'saldo_total':     _f(saldo),
            'deuda_vencida':   _f(deuda_vencida),
            'deuda_no_vencida':_f(max(saldo - deuda_vencida, Decimal('0'))),
            'riesgo':          riesgo,
            'ultima_actividad':_iso(ultimo_mov),
        })

    reverse = ordering.startswith('-')
    key     = ordering.lstrip('-')
    valid_keys = {'saldo_total', 'razon_social', 'deuda_vencida', 'riesgo'}
    if key in valid_keys:
        resultado.sort(key=lambda x: (x.get(key) or 0) if key != 'razon_social' else (x.get(key) or ''),
                       reverse=reverse)
    else:
        resultado.sort(key=lambda x: x['saldo_total'], reverse=True)

    totales = {
        'clientes':   len(resultado),
        'saldo':      round(sum(r['saldo_total']     for r in resultado), 2),
        'vencida':    round(sum(r['deuda_vencida']   for r in resultado), 2),
        'no_vencida': round(sum(r['deuda_no_vencida']for r in resultado), 2),
        'excedidos':  sum(1 for r in resultado if r['riesgo'] == 'EXCEDIDO'),
        'en_seguimiento': sum(1 for r in resultado if r['riesgo'] == 'SEGUIMIENTO'),
        'fecha_hasta':fecha_hasta.isoformat(),
    }

    return Response({'results': resultado, 'totales': totales})