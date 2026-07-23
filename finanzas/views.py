# finanzas/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import csv
from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .models import (
    Cheque, TipoValor, CuentaFondo, Banco,
    PlanCuota, MovimientoFondo, CentroCosto,
)
from .serializers import (
    TipoValorSerializer, CuentaFondoSerializer,
    BancoSerializer, PlanCuotaSerializer,
    ChequeSerializer, MovimientoFondoSerializer,
    MovimientoFondoWriteSerializer,
)
from .services import DashboardService, ReporteIVAService


# ─── Dashboard ────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_metrics_api(request):
    try:
        metrics = DashboardService.get_metricas_financieras()
        # Convertir Decimal → float para JSON
        return Response({k: float(v) if isinstance(v, Decimal) else v
                         for k, v in metrics.items()})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ─── Maestros (ReadOnly) ──────────────────────────────────────

class TipoValorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TipoValor.objects.all().order_by('nombre')
    serializer_class = TipoValorSerializer
    permission_classes = [IsAuthenticated]


class BancoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Banco.objects.all().order_by('nombre')
    serializer_class = BancoSerializer
    permission_classes = [IsAuthenticated]


class PlanCuotaViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PlanCuotaSerializer

    def get_queryset(self):
        qs = PlanCuota.objects.select_related('plan', 'plan__tarjeta').order_by(
            'plan__tarjeta__nombre', 'plan__nombre', 'cuotas')
        if plan_id := self.request.query_params.get('plan'):
            qs = qs.filter(plan_id=plan_id)
        if tarjeta_id := self.request.query_params.get('tarjeta'):
            qs = qs.filter(plan__tarjeta_id=tarjeta_id)
        return qs


# ─── Cuentas de Fondo / Cajas ─────────────────────────────────

class CuentaFondoViewSet(viewsets.ModelViewSet):
    """
    GET    /api/finanzas/cuentas-fondo/           lista con saldos
    GET    /api/finanzas/cuentas-fondo/{id}/      detalle
    GET    /api/finanzas/cuentas-fondo/{id}/movimientos/  extracto
    POST   /api/finanzas/cuentas-fondo/{id}/movimiento/   registrar ingreso/egreso manual
    """
    serializer_class = CuentaFondoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre']
    ordering = ['nombre']

    def get_queryset(self):
        qs = CuentaFondo.objects.all()
        if activa := self.request.query_params.get('activa'):
            qs = qs.filter(is_active=(activa.lower() == 'true'))
        if tipo := self.request.query_params.get('tipo'):
            qs = qs.filter(tipo=tipo)
        return qs

    @action(detail=True, methods=['get'], url_path='movimientos')
    def movimientos(self, request, pk=None):
        cuenta = self.get_object()
        qs = MovimientoFondo.objects.filter(cuenta=cuenta).select_related(
            'tipo_valor', 'usuario', 'cheque'
        ).order_by('-fecha', '-id')

        desde = request.query_params.get('desde')
        hasta = request.query_params.get('hasta')
        if desde: qs = qs.filter(fecha__date__gte=desde)
        if hasta: qs = qs.filter(fecha__date__lte=hasta)

        # Saldo acumulado
        movs = list(qs[:200])
        saldo = float(cuenta.saldo_monto)
        resultado = []
        for m in reversed(movs):
            resultado.insert(0, {
                'id':              m.id,
                'fecha':           m.fecha,
                'tipo_movimiento': m.tipo_movimiento,
                'tipo_movimiento_display': m.get_tipo_movimiento_display(),
                'tipo_valor':      m.tipo_valor.nombre if m.tipo_valor else '',
                'concepto':        m.concepto,
                'ingreso':         float(m.monto_ingreso),
                'egreso':          float(m.monto_egreso),
                'saldo':           round(saldo, 2),
                'conciliado':      m.conciliado,
                'usuario':         str(m.usuario) if m.usuario else '',
            })
            saldo -= float(m.monto_ingreso) - float(m.monto_egreso)

        return Response({
            'cuenta_id':   cuenta.id,
            'nombre':      cuenta.nombre,
            'tipo':        cuenta.tipo,
            'saldo_actual': float(cuenta.saldo_monto),
            'movimientos': resultado,
        })

    @action(detail=True, methods=['post'], url_path='movimiento')
    def registrar_movimiento(self, request, pk=None):
        """Registrar ingreso o egreso manual en la cuenta."""
        cuenta = self.get_object()
        tipo   = request.data.get('tipo_movimiento')  # 'IN' o 'EG'
        monto  = Decimal(str(request.data.get('monto', 0)))
        concepto = request.data.get('concepto', '')

        if tipo not in ('IN', 'EG'):
            return Response({'error': 'tipo_movimiento debe ser IN o EG.'}, status=400)
        if monto <= 0:
            return Response({'error': 'El monto debe ser positivo.'}, status=400)
        if not concepto.strip():
            return Response({'error': 'El concepto es obligatorio.'}, status=400)

        with transaction.atomic():
            MovimientoFondo.objects.create(
                cuenta         = cuenta,
                tipo_movimiento= tipo,
                monto_ingreso  = monto if tipo == 'IN' else Decimal(0),
                monto_egreso   = monto if tipo == 'EG' else Decimal(0),
                concepto       = concepto,
                usuario        = request.user,
            )
            if tipo == 'IN':
                CuentaFondo.objects.filter(pk=cuenta.pk).update(
                    saldo_monto=cuenta.saldo_monto + monto)
            else:
                CuentaFondo.objects.filter(pk=cuenta.pk).update(
                    saldo_monto=cuenta.saldo_monto - monto)

        cuenta.refresh_from_db()
        return Response(CuentaFondoSerializer(cuenta).data, status=201)


# ─── Cheques ──────────────────────────────────────────────────

class ChequeViewSet(viewsets.ModelViewSet):
    """
    GET    /api/finanzas/cheques/               lista con filtros
    POST   /api/finanzas/cheques/               registrar cheque
    PATCH  /api/finanzas/cheques/{id}/          editar
    POST   /api/finanzas/cheques/{id}/depositar/   → DEPOSITADO
    POST   /api/finanzas/cheques/{id}/cobrar/      → COBRADO
    POST   /api/finanzas/cheques/{id}/rechazar/    → RECHAZADO
    POST   /api/finanzas/cheques/{id}/anular/      → ANULADO
    """
    serializer_class = ChequeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['numero', 'nombre_librador', 'cuit_librador', 'banco__nombre']
    ordering = ['-fecha_pago', '-id']

    def get_queryset(self):
        qs = Cheque.objects.select_related('banco', 'moneda')
        if estado := self.request.query_params.get('estado'):
            qs = qs.filter(estado=estado)
        if origen := self.request.query_params.get('origen'):
            qs = qs.filter(origen=origen)
        if tipo := self.request.query_params.get('tipo_cheque'):
            qs = qs.filter(tipo_cheque=tipo)
        if desde := self.request.query_params.get('vence_desde'):
            qs = qs.filter(fecha_pago__gte=desde)
        if hasta := self.request.query_params.get('vence_hasta'):
            qs = qs.filter(fecha_pago__lte=hasta)
        return qs

    def _cambiar_estado(self, request, pk, nuevo_estado, estados_validos):
        cheque = self.get_object()
        if cheque.estado not in estados_validos:
            return Response(
                {'error': f'No se puede pasar al estado {nuevo_estado} desde {cheque.get_estado_display()}.'},
                status=400
            )
        cheque.estado = nuevo_estado
        cheque.save(update_fields=['estado'])
        return Response(ChequeSerializer(cheque).data)

    @action(detail=True, methods=['post'])
    def depositar(self, request, pk=None):
        return self._cambiar_estado(request, pk, Cheque.Estado.DEPOSITADO,
                                    [Cheque.Estado.EN_CARTERA])

    @action(detail=True, methods=['post'])
    def cobrar(self, request, pk=None):
        return self._cambiar_estado(request, pk, Cheque.Estado.COBRADO,
                                    [Cheque.Estado.EN_CARTERA, Cheque.Estado.DEPOSITADO])

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        return self._cambiar_estado(request, pk, Cheque.Estado.RECHAZADO,
                                    [Cheque.Estado.DEPOSITADO, Cheque.Estado.EN_CARTERA])

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        cheque = self.get_object()
        if cheque.estado == Cheque.Estado.ANULADO:
            return Response({'error': 'El cheque ya está anulado.'}, status=400)
        cheque.estado = Cheque.Estado.ANULADO
        cheque.save(update_fields=['estado'])
        return Response(ChequeSerializer(cheque).data)

    @action(detail=False, methods=['get'], url_path='resumen')
    def resumen(self, request):
        """KPIs de la cartera de cheques."""
        hoy = timezone.now().date()
        cartera = Cheque.objects.filter(
            origen=Cheque.Origen.TERCERO,
            estado=Cheque.Estado.EN_CARTERA
        )
        vencen_semana = cartera.filter(fecha_pago__lte=hoy + timedelta(days=7))
        return Response({
            'en_cartera_count': cartera.count(),
            'en_cartera_monto': float(cartera.aggregate(t=Sum('monto'))['t'] or 0),
            'vencen_7_dias_count': vencen_semana.count(),
            'vencen_7_dias_monto': float(vencen_semana.aggregate(t=Sum('monto'))['t'] or 0),
            'rechazados_mes': Cheque.objects.filter(
                estado=Cheque.Estado.RECHAZADO,
                fecha_emision__month=hoy.month,
                fecha_emision__year=hoy.year,
            ).count(),
        })


# ─── Movimientos (solo lectura) ───────────────────────────────

class MovimientoFondoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MovimientoFondoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-fecha', '-id']

    def get_queryset(self):
        qs = MovimientoFondo.objects.select_related('cuenta', 'tipo_valor', 'usuario')
        if cuenta := self.request.query_params.get('cuenta'):
            qs = qs.filter(cuenta_id=cuenta)
        if tipo := self.request.query_params.get('tipo_movimiento'):
            qs = qs.filter(tipo_movimiento=tipo)
        if desde := self.request.query_params.get('desde'):
            qs = qs.filter(fecha__date__gte=desde)
        if hasta := self.request.query_params.get('hasta'):
            qs = qs.filter(fecha__date__lte=hasta)
        return qs


# ─── Vistas legacy admin ──────────────────────────────────────

@staff_member_required
def reporte_cashflow_view(request):
    hoy = timezone.now().date()
    cheques_entrada = Cheque.objects.filter(
        origen=Cheque.Origen.TERCERO, estado=Cheque.Estado.EN_CARTERA,
        fecha_pago__gte=hoy).order_by('fecha_pago')
    cheques_salida = Cheque.objects.filter(
        origen=Cheque.Origen.PROPIO, estado=Cheque.Estado.ENTREGADO,
        fecha_pago__gte=hoy).order_by('fecha_pago')
    total_entrada = cheques_entrada.aggregate(Sum('monto'))['monto__sum'] or 0
    total_salida  = cheques_salida.aggregate(Sum('monto'))['monto__sum'] or 0
    return render(request, 'admin/finanzas/reporte_cashflow.html', {
        'hoy': hoy, 'cheques_entrada': cheques_entrada,
        'cheques_salida': cheques_salida,
        'total_entrada': total_entrada, 'total_salida': total_salida,
        'balance_proyectado': total_entrada - total_salida,
        'title': 'Proyección Financiera (Cash Flow de Cheques)',
    })


@staff_member_required
def libro_iva_view(request):
    hoy = timezone.now()
    mes  = int(request.GET.get('mes', hoy.month))
    anio = int(request.GET.get('anio', hoy.year))
    tipo = request.GET.get('tipo', 'VENTAS')
    data = ReporteIVAService.generar_libro_iva(mes, anio, tipo)
    return render(request, 'admin/finanzas/libro_iva.html', {
        'data': data, 'mes_actual': mes, 'anio_actual': anio, 'tipo_actual': tipo,
        'meses': range(1, 13), 'anios': range(hoy.year - 2, hoy.year + 2),
        'title': f'Libro IVA {tipo} - {mes}/{anio}',
    })


@staff_member_required
def exportar_libro_iva_view(request):
    hoy  = timezone.now()
    mes  = int(request.GET.get('mes', hoy.month))
    anio = int(request.GET.get('anio', hoy.year))
    tipo = request.GET.get('tipo', 'VENTAS')
    data = ReporteIVAService.generar_libro_iva(mes, anio, tipo)
    lineas, totales, columnas_iva = data['lineas'], data['totales'], data.get('columnas_iva', [])
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Libro_IVA_{tipo}_{mes}_{anio}.csv"'
    writer = csv.writer(response, delimiter=';')
    header = ['Fecha', 'Comprobante', 'Razón Social', 'CUIT', 'Neto Gravado']
    for col in columnas_iva: header.append(f'IVA {col}%')
    header.extend(['Otros Imp.', 'Total'])
    writer.writerow(header)
    for fila in lineas:
        row = [fila['fecha'].strftime("%d/%m/%Y"), fila['comprobante'],
               fila['razon_social'], fila['cuit'],
               f"{fila['neto']:.2f}".replace('.', ',')]
        for col in columnas_iva:
            row.append(f"{fila.get('ivas', {}).get(col, 0):.2f}".replace('.', ','))
        row += [f"{fila['otros']:.2f}".replace('.', ','), f"{fila['total']:.2f}".replace('.', ',')]
        writer.writerow(row)
    return response