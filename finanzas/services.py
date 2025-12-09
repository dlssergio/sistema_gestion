from django.db.models import Sum
from django.db.models.functions import TruncDay
from django.utils import timezone
from decimal import Decimal
import json

# Modelos
from finanzas.models import CuentaFondo, Cheque
from ventas.models import ComprobanteVenta
from compras.models import ComprobanteCompra


class DashboardService:
    @staticmethod
    def get_metricas_financieras():
        hoy = timezone.now()
        # Primer día del mes actual
        inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # --- 1. KPIs ESCALARES (Lo que ya tenías) ---
        liquidez = CuentaFondo.objects.filter(activa=True).aggregate(
            total=Sum('saldo_monto')
        )['total'] or Decimal(0)

        deuda_clientes = ComprobanteVenta.objects.filter(
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            saldo_pendiente__gt=0
        ).aggregate(total=Sum('saldo_pendiente'))['total'] or Decimal(0)

        cheques_cartera = Cheque.objects.filter(
            estado=Cheque.Estado.EN_CARTERA
        ).aggregate(total=Sum('monto'))['total'] or Decimal(0)

        a_cobrar = deuda_clientes + cheques_cartera

        a_pagar = ComprobanteCompra.objects.filter(
            estado=ComprobanteCompra.Estado.CONFIRMADO,
            saldo_pendiente__gt=0
        ).aggregate(total=Sum('saldo_pendiente'))['total'] or Decimal(0)

        ventas_mes = ComprobanteVenta.objects.filter(
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            fecha__gte=inicio_mes
        ).aggregate(total=Sum('total'))['total'] or Decimal(0)

        # --- 2. DATOS PARA GRÁFICOS (Evolución de Ventas) ---
        # Agrupamos ventas por día del mes actual
        ventas_diarias = ComprobanteVenta.objects.filter(
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            fecha__gte=inicio_mes
        ).annotate(dia=TruncDay('fecha')).values('dia').annotate(total=Sum('total')).order_by('dia')

        # Preparamos arrays para Chart.js
        labels = []
        data = []

        if ventas_diarias:
            for v in ventas_diarias:
                # Formato día: "08/12"
                labels.append(v['dia'].strftime("%d/%m"))
                data.append(float(v['total']))
        else:
            # Si no hay ventas, mostramos el día de hoy en cero
            labels.append(hoy.strftime("%d/%m"))
            data.append(0)

        return {
            'liquidez': liquidez,
            'a_cobrar': a_cobrar,
            'a_pagar': a_pagar,
            'ventas_mes': ventas_mes,
            'cheques_cartera': cheques_cartera,
            # Datos serializados para JS
            'chart_labels': json.dumps(labels),
            'chart_data': json.dumps(data)
        }