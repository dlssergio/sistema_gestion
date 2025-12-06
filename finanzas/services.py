from django.db.models import Sum, F
from django.utils import timezone
from decimal import Decimal

# Modelos
from finanzas.models import CuentaFondo, Cheque
from ventas.models import ComprobanteVenta
from compras.models import ComprobanteCompra


class DashboardService:
    @staticmethod
    def get_metricas_financieras():
        hoy = timezone.now()
        inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 1. LIQUIDEZ ACTUAL (Caja + Bancos)
        # Sumamos el saldo de todas las cuentas activas
        liquidez = CuentaFondo.objects.filter(activa=True).aggregate(
            total=Sum('saldo_monto')
        )['total'] or Decimal(0)

        # 2. A COBRAR (Deuda Clientes + Cheques en Cartera)
        deuda_clientes = ComprobanteVenta.objects.filter(
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            saldo_pendiente__gt=0
        ).aggregate(total=Sum('saldo_pendiente'))['total'] or Decimal(0)

        cheques_cartera = Cheque.objects.filter(
            estado=Cheque.Estado.EN_CARTERA
        ).aggregate(total=Sum('monto'))['total'] or Decimal(0)

        a_cobrar = deuda_clientes + cheques_cartera

        # 3. A PAGAR (Deuda Proveedores)
        a_pagar = ComprobanteCompra.objects.filter(
            estado=ComprobanteCompra.Estado.CONFIRMADO,
            saldo_pendiente__gt=0
        ).aggregate(total=Sum('saldo_pendiente'))['total'] or Decimal(0)

        # 4. RESULTADO DEL MES (Estimado)
        # Ventas del mes (Total facturado)
        ventas_mes = ComprobanteVenta.objects.filter(
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            fecha__gte=inicio_mes
        ).aggregate(total=Sum('total'))['total'] or Decimal(0)

        # Costo de Mercadería Vendida (Aproximado usando costo actual)
        # Nota: Para precisión contable exacta se requeriría historizar costos,
        # pero esto es excelente para un tablero de control rápido.
        items_vendidos = ComprobanteVenta.objects.filter(
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            fecha__gte=inicio_mes
        ).values_list('items__cantidad', 'items__articulo__precio_costo_monto')

        costo_mes = sum(cant * costo for cant, costo in items_vendidos if cant and costo)

        resultado_mes = ventas_mes - costo_mes

        return {
            'liquidez': liquidez,
            'a_cobrar': a_cobrar,
            'a_pagar': a_pagar,
            'resultado_mes': resultado_mes,
            'ventas_mes': ventas_mes,  # Dato extra útil
            'cheques_cartera': cheques_cartera  # Dato extra útil
        }