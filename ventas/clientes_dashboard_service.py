from decimal import Decimal
from django.db.models import Sum, Avg
from django.utils import timezone

from .models import Cliente, ComprobanteVenta, Recibo


def _to_decimal(value):
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _to_float(value):
    return float(_to_decimal(value))


def _format_datetime(dt):
    if not dt:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return None


def _normalize_condicion(value):
    if value is None:
        return ""

    raw = str(value).strip().upper()

    mapping = {
        "CC": "CC",
        "CTA_CTE": "CC",
        "CTACTE": "CC",
        "CUENTA_CORRIENTE": "CC",
        "CUENTA CORRIENTE": "CC",
        "CUENTA CTE": "CC",
        "CUENTACTE": "CC",

        "CO": "CO",
        "CONTADO": "CO",
        "CASH": "CO",
    }
    return mapping.get(raw, raw)


def _clasificar_condicion(comp, cliente):
    """
    Clasificación robusta para dashboard ejecutivo.

    Reglas:
    1) Si condicion_venta está bien informada, usarla.
    2) Si no está informada:
       - si el cliente NO permite cta cte -> contado
       - si permite cta cte -> analizar saldo / recibos
    3) Si el comprobante tiene saldo pendiente y el cliente opera con cta cte,
       para tablero ejecutivo conviene tratarlo como deuda cta cte.
    """
    cond = _normalize_condicion(getattr(comp, 'condicion_venta', None))

    if cond == "CC":
        return "CC"

    if cond == "CO":
        saldo = _to_decimal(getattr(comp, 'saldo_pendiente', 0))
        # Si quedó saldo pendiente en un comprobante contado,
        # para tablero financiero lo mostramos como deuda de contado pendiente.
        return "CO" if saldo > 0 else "CO"

    if not getattr(cliente, 'permite_cta_cte', False):
        return "CO"

    saldo = _to_decimal(getattr(comp, 'saldo_pendiente', 0))
    if saldo > 0:
        return "CC"

    return "CO"


class ClienteDashboardService:
    @classmethod
    def build_dashboard(cls, cliente: Cliente):
        hoy = timezone.localdate()

        comprobantes_con_saldo = (
            ComprobanteVenta.objects
            .filter(
                cliente=cliente,
                estado=ComprobanteVenta.Estado.CONFIRMADO,
                saldo_pendiente__gt=0,
            )
            .select_related('tipo_comprobante')
            .order_by('fecha', 'numero')
        )

        saldo_total = _to_decimal(
            comprobantes_con_saldo.aggregate(total=Sum('saldo_pendiente')).get('total')
        )

        deuda_vencida = Decimal("0.00")
        deuda_no_vencida = Decimal("0.00")
        comprobantes_impagos = 0

        aging_0_30 = Decimal("0.00")
        aging_31_60 = Decimal("0.00")
        aging_61_90 = Decimal("0.00")
        aging_90_plus = Decimal("0.00")

        deuda_cta_cte = Decimal("0.00")
        deuda_contado = Decimal("0.00")

        detalle_clasificacion = []

        for comp in comprobantes_con_saldo:
            saldo = _to_decimal(comp.saldo_pendiente)
            if saldo <= 0:
                continue

            comprobantes_impagos += 1

            clasificacion = _clasificar_condicion(comp, cliente)

            if clasificacion == "CC":
                deuda_cta_cte += saldo
            else:
                deuda_contado += saldo

            detalle_clasificacion.append({
                'id': comp.pk,
                'numero': comp.numero_completo,
                'condicion_original': getattr(comp, 'condicion_venta', None),
                'clasificacion_dashboard': clasificacion,
                'saldo': _to_float(saldo),
            })

            fecha_base = comp.fecha.date() if comp.fecha else hoy
            dias_venc = int(cliente.dias_vencimiento or 0)
            fecha_vencimiento = fecha_base + timezone.timedelta(days=dias_venc)

            if fecha_vencimiento < hoy:
                deuda_vencida += saldo
                dias_mora = (hoy - fecha_vencimiento).days

                if dias_mora <= 30:
                    aging_0_30 += saldo
                elif dias_mora <= 60:
                    aging_31_60 += saldo
                elif dias_mora <= 90:
                    aging_61_90 += saldo
                else:
                    aging_90_plus += saldo
            else:
                deuda_no_vencida += saldo

        # Si por datos legacy quedó todo en cero pero existe saldo,
        # forzamos consistencia para que el tablero nunca quede incoherente.
        if saldo_total > 0 and deuda_cta_cte == 0 and deuda_contado == 0:
            if getattr(cliente, 'permite_cta_cte', False):
                deuda_cta_cte = saldo_total
            else:
                deuda_contado = saldo_total

        limite_credito = _to_decimal(cliente.limite_credito or 0)
        credito_disponible = limite_credito - saldo_total

        if credito_disponible < 0 or aging_90_plus > 0:
            riesgo = "EXCEDIDO"
        elif deuda_vencida > 0:
            riesgo = "SEGUIMIENTO"
        else:
            riesgo = "NORMAL"

        comprobantes_confirmados = (
            ComprobanteVenta.objects
            .filter(
                cliente=cliente,
                estado=ComprobanteVenta.Estado.CONFIRMADO,
            )
            .select_related('tipo_comprobante')
            .order_by('-fecha', '-numero')
        )

        ultima_venta_obj = comprobantes_confirmados.first()
        ultima_venta = None
        if ultima_venta_obj:
            ultima_venta = {
                'id': ultima_venta_obj.pk,
                'fecha': _format_datetime(ultima_venta_obj.fecha),
                'numero': ultima_venta_obj.numero_completo,
                'tipo': getattr(ultima_venta_obj.tipo_comprobante, 'nombre', 'Comprobante'),
                'total': _to_float(ultima_venta_obj.total),
                'saldo': _to_float(ultima_venta_obj.saldo_pendiente),
                'estado': ultima_venta_obj.estado,
            }

        fecha_30d = hoy - timezone.timedelta(days=30)
        fecha_90d = hoy - timezone.timedelta(days=90)

        comprobantes_30d = comprobantes_confirmados.filter(fecha__date__gte=fecha_30d)
        comprobantes_90d = comprobantes_confirmados.filter(fecha__date__gte=fecha_90d)

        total_vendido_30d = _to_decimal(
            comprobantes_30d.aggregate(total=Sum('total')).get('total')
        )

        cantidad_comprobantes_90d = comprobantes_90d.count()

        ticket_promedio_90d = _to_decimal(
            comprobantes_90d.aggregate(avg=Avg('total')).get('avg')
        )

        dias_desde_ultima_compra = None
        if ultima_venta_obj and ultima_venta_obj.fecha:
            dias_desde_ultima_compra = (hoy - ultima_venta_obj.fecha.date()).days

        ultimos_comprobantes = []
        for comp in comprobantes_confirmados[:8]:
            ultimos_comprobantes.append({
                'id': comp.pk,
                'fecha': _format_datetime(comp.fecha),
                'numero': comp.numero_completo,
                'tipo': getattr(comp.tipo_comprobante, 'nombre', 'Comprobante'),
                'condicion_venta': getattr(comp, 'condicion_venta', None),
                'total': _to_float(comp.total),
                'saldo': _to_float(comp.saldo_pendiente),
                'estado': comp.estado,
                'estado_pago': comp.estado_pago,
            })

        # Para cuenta corriente histórica del panel lateral
        facturas_cta_cte = [
            f for f in comprobantes_confirmados
            if _clasificar_condicion(f, cliente) == "CC"
        ]

        recibos = list(
            Recibo.objects.filter(
                cliente=cliente,
                estado=Recibo.Estado.CONFIRMADO,
                origen=Recibo.Origen.COBRANZA,
            ).values(
                'id',
                'fecha',
                'numero',
                'monto_total',
            )
        )

        movimientos = []

        for f in facturas_cta_cte:
            numero = f"{(f.letra or '').strip()} {int(f.punto_venta or 0):05d}-{int(f.numero or 0):08d}".strip()
            movimientos.append({
                'id': f.pk,
                'fecha': f.fecha,
                'tipo': 'Factura',
                'numero': numero,
                'debe': _to_decimal(f.total),
                'haber': Decimal("0.00"),
            })

        for r in recibos:
            movimientos.append({
                'id': r.get('id'),
                'fecha': r.get('fecha'),
                'tipo': 'Recibo',
                'numero': f"X {int(r.get('numero') or 0):08d}",
                'debe': Decimal("0.00"),
                'haber': _to_decimal(r.get('monto_total')),
            })

        movimientos = sorted(movimientos, key=lambda x: x['fecha'] or timezone.now())

        saldo_acumulado = Decimal("0.00")
        movimientos_cta_cte = []

        for mov in movimientos:
            saldo_acumulado += _to_decimal(mov['debe']) - _to_decimal(mov['haber'])
            movimientos_cta_cte.append({
                'id': mov['id'],
                'fecha': _format_datetime(mov['fecha']),
                'tipo': mov['tipo'],
                'numero': mov['numero'],
                'debe': _to_float(mov['debe']),
                'haber': _to_float(mov['haber']),
                'saldo': _to_float(saldo_acumulado),
            })

        # Sin límite — el frontend pagina o filtra según necesite
        # movimientos_cta_cte = movimientos_cta_cte[-10:]

        return {
            'cliente_id': cliente.pk,
            'saldo_total': _to_float(saldo_total),
            'deuda_vencida': _to_float(deuda_vencida),
            'deuda_no_vencida': _to_float(deuda_no_vencida),
            'deuda_cta_cte': _to_float(deuda_cta_cte),
            'deuda_contado': _to_float(deuda_contado),
            'limite_credito': _to_float(limite_credito),
            'credito_disponible': _to_float(credito_disponible),
            'comprobantes_impagos': comprobantes_impagos,
            'riesgo': riesgo,
            'aging': {
                'bucket_0_30': _to_float(aging_0_30),
                'bucket_31_60': _to_float(aging_31_60),
                'bucket_61_90': _to_float(aging_61_90),
                'bucket_90_plus': _to_float(aging_90_plus),
            },
            'ultima_venta': ultima_venta,
            'kpis': {
                'cantidad_comprobantes_90d': cantidad_comprobantes_90d,
                'total_vendido_30d': _to_float(total_vendido_30d),
                'ticket_promedio_90d': _to_float(ticket_promedio_90d),
                'dias_desde_ultima_compra': dias_desde_ultima_compra,
            },
            'ultimos_comprobantes': ultimos_comprobantes,
            'movimientos_cta_cte': movimientos_cta_cte,
            'debug_clasificacion': detalle_clasificacion,
        }