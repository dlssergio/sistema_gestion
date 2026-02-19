# finanzas/views.py (VERSIÓN FINAL: EXPORTACIÓN CSV DINÁMICA)

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .services import DashboardService, ReporteIVAService
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from .models import Cheque
import csv
from django.http import HttpResponse


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_metrics_api(request):
    """
    API que devuelve los KPIs y datos para gráficos del Dashboard Ejecutivo.
    """
    try:
        metrics = DashboardService.get_metricas_financieras()
        return Response(metrics)
    except Exception as e:
        print(f"Error calculando métricas: {e}")
        return Response({'error': 'No se pudieron obtener las métricas'}, status=500)


@staff_member_required
def reporte_cashflow_view(request):
    hoy = timezone.now().date()
    # treinta_dias = hoy + timedelta(days=30) # Variable no usada, se puede quitar o dejar

    # 1. Ingresos Futuros (Cheques de Terceros en Cartera)
    cheques_entrada = Cheque.objects.filter(
        origen=Cheque.Origen.TERCERO,
        estado=Cheque.Estado.EN_CARTERA,
        fecha_pago__gte=hoy
    ).order_by('fecha_pago')

    # 2. Egresos Futuros (Cheques Propios Entregados pero no debitados aún)
    cheques_salida = Cheque.objects.filter(
        origen=Cheque.Origen.PROPIO,
        estado=Cheque.Estado.ENTREGADO,
        fecha_pago__gte=hoy
    ).order_by('fecha_pago')

    # Totales
    total_entrada = cheques_entrada.aggregate(Sum('monto'))['monto__sum'] or 0
    total_salida = cheques_salida.aggregate(Sum('monto'))['monto__sum'] or 0
    balance_proyectado = total_entrada - total_salida

    context = {
        'hoy': hoy,
        'cheques_entrada': cheques_entrada,
        'cheques_salida': cheques_salida,
        'total_entrada': total_entrada,
        'total_salida': total_salida,
        'balance_proyectado': balance_proyectado,
        'title': 'Proyección Financiera (Cash Flow de Cheques)'
    }
    return render(request, 'admin/finanzas/reporte_cashflow.html', context)


@staff_member_required
def libro_iva_view(request):
    # 1. Obtener filtros (Default: Mes actual)
    hoy = timezone.now()
    try:
        mes = int(request.GET.get('mes', hoy.month))
        anio = int(request.GET.get('anio', hoy.year))
    except ValueError:
        mes = hoy.month
        anio = hoy.year

    tipo = request.GET.get('tipo', 'VENTAS')  # 'VENTAS' o 'COMPRAS'

    # 2. Llamar al servicio
    data = ReporteIVAService.generar_libro_iva(mes, anio, tipo)

    # 3. Contexto para el template
    context = {
        'data': data,
        'mes_actual': mes,
        'anio_actual': anio,
        'tipo_actual': tipo,
        'meses': range(1, 13),
        'anios': range(hoy.year - 2, hoy.year + 2),
        'title': f"Libro IVA {tipo} - {mes}/{anio}"
    }

    return render(request, 'admin/finanzas/libro_iva.html', context)


@staff_member_required
def exportar_libro_iva_view(request):
    """
    Genera un archivo CSV descargable con los datos del Libro IVA (DINÁMICO).
    """
    hoy = timezone.now()
    try:
        mes = int(request.GET.get('mes', hoy.month))
        anio = int(request.GET.get('anio', hoy.year))
    except ValueError:
        mes = hoy.month
        anio = hoy.year

    tipo = request.GET.get('tipo', 'VENTAS')

    # 1. Obtener datos procesados del servicio
    data = ReporteIVAService.generar_libro_iva(mes, anio, tipo)
    lineas = data['lineas']
    totales = data['totales']
    columnas_iva = data.get('columnas_iva', [])  # Lista de tasas detectadas (ej: ['10.5', '21.0'])

    # 2. Configurar respuesta HTTP
    response = HttpResponse(content_type='text/csv')
    filename = f"Libro_IVA_{tipo}_{mes}_{anio}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # 3. Escribir CSV (; para Excel Latam)
    writer = csv.writer(response, delimiter=';')

    # --- CONSTRUCCIÓN DINÁMICA DEL ENCABEZADO ---
    header_row = ['Fecha', 'Comprobante', 'Razón Social', 'CUIT', 'Neto Gravado']

    # Agregamos una columna por cada tasa de IVA detectada
    for col in columnas_iva:
        header_row.append(f'IVA {col}%')

    header_row.extend(['Otros Imp.', 'Total'])
    writer.writerow(header_row)

    # --- FILAS DE DATOS ---
    for fila in lineas:
        row = [
            fila['fecha'].strftime("%d/%m/%Y"),
            fila['comprobante'],
            fila['razon_social'],
            fila['cuit'],
            f"{fila['neto']:.2f}".replace('.', ',')
        ]

        # Agregamos los montos de IVA dinámicos
        # Buscamos en el diccionario 'ivas' de la fila. Si no existe esa tasa, va 0,00
        ivas_fila = fila.get('ivas', {})
        for col in columnas_iva:
            monto = ivas_fila.get(col, 0)
            row.append(f"{monto:.2f}".replace('.', ','))

        row.append(f"{fila['otros']:.2f}".replace('.', ','))
        row.append(f"{fila['total']:.2f}".replace('.', ','))

        writer.writerow(row)

    # --- FILA DE TOTALES ---
    writer.writerow([])  # Espacio vacío

    row_total = ['TOTALES', '', '', '', f"{totales['neto_gravado']:.2f}".replace('.', ',')]

    # Totales dinámicos de IVA
    ivas_totales = totales.get('ivas', {})
    for col in columnas_iva:
        monto = ivas_totales.get(col, 0)
        row_total.append(f"{monto:.2f}".replace('.', ','))

    row_total.append(f"{totales['otros_impuestos']:.2f}".replace('.', ','))
    row_total.append(f"{totales['total']:.2f}".replace('.', ','))

    writer.writerow(row_total)

    return response