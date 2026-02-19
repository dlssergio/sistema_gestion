# finanzas/services.py (VERSIÓN FINAL DEFINITIVA: IVA DINÁMICO + FILTRO FISCAL)

from django.db.models import Sum, Q
from django.db.models.functions import TruncDay
from django.utils import timezone
from decimal import Decimal
from django.core.exceptions import ValidationError
import json
from datetime import date
import calendar

# Modelos propios (Importaciones directas donde no hay riesgo circular)
from finanzas.models import CuentaFondo, Cheque, RegimenRetencion


# Importaciones diferidas dentro de métodos para modelos de Ventas/Compras
# para evitar CircularDependencyError si estos módulos importan finanzas.


class DashboardService:
    @staticmethod
    def get_metricas_financieras():
        # Importaciones locales para romper el ciclo
        from ventas.models import ComprobanteVenta
        from compras.models import ComprobanteCompra

        hoy = timezone.now()
        # Primer día del mes actual
        inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # --- 1. KPIs ESCALARES ---
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

        # Aquí usamos el modelo importado localmente
        a_pagar = ComprobanteCompra.objects.filter(
            estado=ComprobanteCompra.Estado.CONFIRMADO,
            saldo_pendiente__gt=0
        ).aggregate(total=Sum('saldo_pendiente'))['total'] or Decimal(0)

        ventas_mes = ComprobanteVenta.objects.filter(
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            fecha__gte=inicio_mes
        ).aggregate(total=Sum('total'))['total'] or Decimal(0)

        # --- 2. DATOS PARA GRÁFICOS (Evolución de Ventas) ---
        ventas_diarias = ComprobanteVenta.objects.filter(
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            fecha__gte=inicio_mes
        ).annotate(dia=TruncDay('fecha')).values('dia').annotate(total=Sum('total')).order_by('dia')

        labels = []
        data = []

        if ventas_diarias:
            for v in ventas_diarias:
                labels.append(v['dia'].strftime("%d/%m"))
                data.append(float(v['total']))
        else:
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


class CalculadoraFiscalService:

    @staticmethod
    def calcular_retencion_ganancias(proveedor, base_imponible):
        """
        Calcula el monto a retener de Ganancias según el régimen del proveedor.
        Retorna una tupla: (monto_retencion, regimen_aplicado)
        """
        regimen = proveedor.regimen_ganancias

        # 1. Si no tiene régimen configurado, no retenemos.
        if not regimen:
            return Decimal(0), None

        # 2. Definir alícuota
        alicuota = regimen.alicuota_inscripto

        # 3. Cálculo: (Base - Mínimo No Imponible) * Alícuota
        monto_sujeto = base_imponible - regimen.monto_no_imponible

        if monto_sujeto <= 0:
            return Decimal(0), regimen

        retencion_calculada = monto_sujeto * (alicuota / Decimal(100))

        # 4. Validar Mínimo de Retención
        if retencion_calculada < regimen.monto_minimo_retencion:
            return Decimal(0), regimen

        return retencion_calculada, regimen


class ReporteIVAService:

    @staticmethod
    def generar_libro_iva(mes, anio, tipo_libro='VENTAS'):
        """
        Genera la estructura de datos para el Libro IVA de forma DINÁMICA.
        Detecta automáticamente las alícuotas de IVA presentes.
        """
        # Importamos aquí para asegurar que el filtro funcione con los modelos correctos
        from ventas.models import ComprobanteVenta
        from compras.models import ComprobanteCompra

        # 1. Definir rango de fechas
        _, last_day = calendar.monthrange(anio, mes)
        fecha_inicio = date(anio, mes, 1)
        fecha_fin = date(anio, mes, last_day)

        # 2. Seleccionar Fuente de Datos CON FILTRO FISCAL
        if tipo_libro == 'VENTAS':
            queryset = ComprobanteVenta.objects.filter(
                fecha__range=(fecha_inicio, fecha_fin),
                estado=ComprobanteVenta.Estado.CONFIRMADO,
                tipo_comprobante__es_fiscal=True,  # Solo Facturas oficiales
                numero__isnull=False
            ).select_related('cliente__entidad', 'tipo_comprobante')
        else:  # COMPRAS
            queryset = ComprobanteCompra.objects.filter(
                fecha__range=(fecha_inicio, fecha_fin),
                estado=ComprobanteCompra.Estado.CONFIRMADO,
                tipo_comprobante__es_fiscal=True,
                numero__isnull=False
            ).select_related('proveedor__entidad', 'tipo_comprobante')

        lineas = []

        # Diccionario para acumular totales generales
        totales = {
            'neto_gravado': 0.0,
            'no_gravado': 0.0,
            'otros_impuestos': 0.0,
            'total': 0.0,
            'ivas': {}  # Diccionario dinámico: {'21.0': 1500, '10.5': 300}
        }

        # Conjunto para saber qué columnas de IVA existen en este período
        columnas_iva_existentes = set()

        # 3. Procesar comprobantes
        for comp in queryset:
            # Recuperar desglose de impuestos del JSON
            impuestos = comp.impuestos or {}

            # Variables de la fila
            ivas_fila = {}  # {'21.0': 100, '10.5': 50}
            total_impuestos_fila = 0.0

            # Procesar el diccionario de impuestos
            for nombre_impuesto, valor_str in impuestos.items():
                try:
                    monto = float(valor_str)
                except:
                    monto = 0.0

                total_impuestos_fila += monto

                # Detectar si es IVA y qué alícuota es
                nombre_upper = nombre_impuesto.upper()
                if 'IVA' in nombre_upper or 'I.V.A.' in nombre_upper:
                    # Intentamos extraer el número de la alícuota
                    # Ej: "IVA 21%" -> "21"
                    # Ej: "IVA 10.5%" -> "10.5"
                    import re
                    match = re.search(r'(\d+[\.,]?\d*)', nombre_impuesto)
                    if match:
                        alicuota_str = match.group(1).replace(',', '.')
                        # Normalizamos la clave (ej: '21.0', '10.5')
                        key_iva = alicuota_str

                        ivas_fila[key_iva] = ivas_fila.get(key_iva, 0) + monto
                        columnas_iva_existentes.add(key_iva)
                    else:
                        # Si dice "IVA" pero no tiene número, lo mandamos a 'Otros' o una categoría default
                        # Opcional: Asumir 21 si no dice nada
                        pass

                        # Calcular 'Otros Impuestos' (Percepciones, Imp internos)
            total_iva_fila = sum(ivas_fila.values())
            otros_fila = total_impuestos_fila - total_iva_fila

            # Detectar signo (Nota de Crédito resta)
            signo = -1 if comp.tipo_comprobante and comp.tipo_comprobante.es_nota_credito else 1

            # Obtener datos de entidad
            if tipo_libro == 'VENTAS':
                razon_social = comp.cliente.entidad.razon_social
                cuit = comp.cliente.entidad.cuit
            else:
                razon_social = comp.proveedor.entidad.razon_social
                cuit = comp.proveedor.entidad.cuit

            # Construcción del nombre del comprobante
            nombre_tipo = comp.tipo_comprobante.nombre if comp.tipo_comprobante else "Comp"
            letra = comp.letra or ""
            pv = comp.punto_venta or 0
            nro = comp.numero or 0
            comprobante_str = f"{nombre_tipo} {letra} {pv:05d}-{nro:08d}"

            # Armado de la fila de datos
            fila = {
                'fecha': comp.fecha,
                'comprobante': comprobante_str,
                'razon_social': razon_social,
                'cuit': cuit,
                'neto': float(comp.subtotal) * signo,
                'otros': otros_fila * signo,
                'total': float(comp.total) * signo,
                'ivas': {k: v * signo for k, v in ivas_fila.items()}  # IVA con signo
            }
            lineas.append(fila)

            # Acumular en totales generales
            totales['neto_gravado'] += fila['neto']
            totales['otros_impuestos'] += fila['otros']
            totales['total'] += fila['total']

            for k, v in fila['ivas'].items():
                totales['ivas'][k] = totales['ivas'].get(k, 0) + v

        # Ordenar las columnas de IVA para que salgan prolijas (ej: 10.5, 21, 27)
        columnas_iva_ordenadas = sorted(list(columnas_iva_existentes), key=lambda x: float(x))

        return {
            'lineas': lineas,
            'totales': totales,
            'columnas_iva': columnas_iva_ordenadas,  # Enviamos las columnas detectadas al template
            'periodo': f"{mes}/{anio}",
            'tipo': tipo_libro
        }