# ventas/views.py
# VERSIÓN CORREGIDA:
# - Mantiene create/update con DRF
# - Registra pagos múltiples
# - Calcula recargo por PlanCuota desde backend
# - Agrega / reemplaza artículo RECARGO_FIN
# - Crea CuponTarjeta para pagos con tarjeta
# - Guarda lote / cupón / observaciones / referencia
# - Funciona tanto en CREATE como en UPDATE (finalización de borradores)

import json
from decimal import Decimal, ROUND_HALF_UP

from django.apps import apps
from django.http import JsonResponse, HttpResponse
from django.db import transaction, models
from django.db.models import Q
import datetime
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.template import Template, Context
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from dataclasses import asdict as dc_asdict

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from djmoney.money import Money
import weasyprint

from inventario.models import Articulo
from parametros.models import (
    TipoComprobante,
    SerieDocumento,
    ConfiguracionEmpresa,
    ConfiguracionSMTP,
)
from finanzas.models import (
    TipoValor,
    CuentaFondo,
    Banco,
    PlanCuota,
    CuponTarjeta,
)

from .utils_pdf import generar_qr_afip
from .models import (
    DisenoImpresion,
    ComprobanteVenta,
    ComprobanteVentaItem,
    Cliente,
    Recibo,
    ReciboValor,
    ReciboImputacion,
)
from .services import TaxCalculatorService, PricingService
from .serializers import ComprobanteVentaSerializer, ComprobanteVentaCreateSerializer

# ==============================================================================
# --- HELPERS INTERNOS PARA POS / API ---
# ==============================================================================

DECIMAL_2 = Decimal("0.01")


def _to_decimal(value, default="0"):
    if value is None or value == "":
        return Decimal(default)
    if hasattr(value, "amount"):
        try:
            return Decimal(str(value.amount))
        except Exception:
            return Decimal(default)
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _q2(value: Decimal) -> Decimal:
    return _to_decimal(value).quantize(DECIMAL_2, rounding=ROUND_HALF_UP)


def _get_default_deposito():
    from inventario.models import Deposito
    return Deposito.objects.filter(es_principal=True).first()


def _get_or_create_recargo_article():
    """
    Replica la lógica del admin:
    crea o recupera el artículo RECARGO_FIN.
    """
    ArticuloModel = apps.get_model("inventario", "Articulo")
    RubroModel = apps.get_model("inventario", "Rubro")

    rubro_financiero, _ = RubroModel.objects.get_or_create(nombre="Financiero/Recargos")

    articulo_recargo, _ = ArticuloModel.objects.get_or_create(
        cod_articulo="RECARGO_FIN",
        defaults={
            "descripcion": "Recargo Financiero / Intereses",
            "precio_venta_monto": Decimal("0.00"),
            "administra_stock": False,
            "esta_activo": True,
            "rubro": rubro_financiero,
        },
    )
    return articulo_recargo


def _remove_existing_recargo_item(comprobante):
    try:
        comprobante.items.filter(articulo__cod_articulo="RECARGO_FIN").delete()
    except Exception:
        pass


def _resolve_plan_cuota_from_pago(pago):
    opcion_cuota_id = pago.get("opcion_cuota")
    if not opcion_cuota_id:
        return None
    return (
        PlanCuota.objects
        .select_related("plan", "plan__tarjeta")
        .filter(pk=opcion_cuota_id)
        .first()
    )


def _infer_tipo_valor_from_pago(pago):
    tipo_valor_id = pago.get("tipo_valor")
    if tipo_valor_id:
        return TipoValor.objects.get(pk=tipo_valor_id)

    metodo = (pago.get("metodo") or "").upper()

    if metodo == "EF":
        tipo = TipoValor.objects.filter(nombre__icontains="efect").order_by("id").first()
    elif metodo == "TR":
        tipo = (
            TipoValor.objects.filter(nombre__icontains="transfer").order_by("id").first()
            or TipoValor.objects.filter(nombre__icontains="transf").order_by("id").first()
        )
    elif metodo == "DB":
        tipo = (
            TipoValor.objects.filter(es_tarjeta=True, nombre__icontains="déb").first()
            or TipoValor.objects.filter(es_tarjeta=True, nombre__icontains="deb").first()
            or TipoValor.objects.filter(es_tarjeta=True, nombre__icontains="débito").first()
            or TipoValor.objects.filter(es_tarjeta=True, nombre__icontains="debito").first()
            or TipoValor.objects.filter(es_tarjeta=True).order_by("id").first()
        )
    elif metodo == "CR":
        tipo = (
            TipoValor.objects.filter(es_tarjeta=True, nombre__icontains="créd").first()
            or TipoValor.objects.filter(es_tarjeta=True, nombre__icontains="cred").first()
            or TipoValor.objects.filter(es_tarjeta=True, nombre__icontains="crédito").first()
            or TipoValor.objects.filter(es_tarjeta=True, nombre__icontains="credito").first()
            or TipoValor.objects.filter(es_tarjeta=True).order_by("id").first()
        )
    else:
        tipo = None

    if not tipo:
        raise ValidationError("No se pudo inferir el tipo de valor del pago.")
    return tipo


def _resolve_destino_from_pago(pago):
    destino_id = pago.get("destino")
    if destino_id:
        return CuentaFondo.objects.get(pk=destino_id)

    metodo = (pago.get("metodo") or "").upper()

    # Reglas pedidas por vos:
    # EF -> Caja Principal (id 1)
    # Tarjetas -> A Depositar - Tarjetas (id 3)
    if metodo == "EF":
        destino = CuentaFondo.objects.filter(pk=1, activa=True).first()
        if destino:
            return destino
        destino = (
            CuentaFondo.objects.filter(activa=True, tipo=CuentaFondo.Tipo.EFECTIVO).order_by("id").first()
            or CuentaFondo.objects.filter(activa=True).order_by("id").first()
        )
        if not destino:
            raise ValidationError("No existe una cuenta/caja destino activa para efectivo.")
        return destino

    if metodo in ("DB", "CR"):
        destino = CuentaFondo.objects.filter(pk=3, activa=True).first()
        if destino:
            return destino
        raise ValidationError("No existe la cuenta puente de tarjetas (id 3) o no está activa.")

    raise ValidationError("Falta 'destino' para el pago informado.")


def _create_or_replace_recargo_item(comprobante, recargo_total):
    """
    Borra cualquier RECARGO_FIN previo y crea uno nuevo si corresponde.
    """
    _remove_existing_recargo_item(comprobante)

    recargo_total = _q2(recargo_total)
    if recargo_total <= 0:
        return None

    articulo_recargo = _get_or_create_recargo_article()
    return ComprobanteVentaItem.objects.create(
        comprobante=comprobante,
        articulo=articulo_recargo,
        cantidad=Decimal("1.000"),
        precio_unitario_original=recargo_total,
    )


def _recalcular_totales_comprobante(comprobante):
    subtotal = Decimal("0.00")
    for item in comprobante.items.all():
        subtotal += _q2(getattr(item, "subtotal", 0))

    desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(comprobante, "venta")
    total_impuestos = sum((_to_decimal(v) for v in desglose_impuestos.values()), Decimal("0.00"))

    comprobante.subtotal = _q2(subtotal)
    comprobante.impuestos = {k: str(_q2(v)) for k, v in desglose_impuestos.items()}
    comprobante.total = _q2(subtotal + total_impuestos)
    comprobante.saldo_pendiente = comprobante.total
    comprobante.save(update_fields=["subtotal", "impuestos", "total", "saldo_pendiente"])


def _normalizar_pagos_y_aplicar_recargos(comprobante, pagos_data):
    """
    Replica la lógica del admin.save_formset() para POS/API:
    - si hay opcion_cuota con coeficiente > 1, calcula interés
    - suma el interés al monto del pago
    - agrega ítem RECARGO_FIN al comprobante
    """
    pagos_normalizados = []
    recargo_total = Decimal("0.00")

    for pago in pagos_data or []:
        pago = dict(pago or {})

        monto_base = _q2(pago.get("monto", 0))
        if monto_base <= 0:
            continue

        plan_cuota = _resolve_plan_cuota_from_pago(pago)
        recargo_monto = Decimal("0.00")

        if plan_cuota and _to_decimal(plan_cuota.coeficiente) > Decimal("1"):
            recargo_monto = _q2(monto_base * (_to_decimal(plan_cuota.coeficiente) - Decimal("1")))
            monto_final = _q2(monto_base + recargo_monto)
        else:
            monto_final = monto_base

        pago["_plan_cuota_obj"] = plan_cuota
        pago["_monto_base"] = monto_base
        pago["_recargo_monto_backend"] = recargo_monto
        pago["_monto_final"] = monto_final

        pagos_normalizados.append(pago)
        recargo_total += recargo_monto

    _create_or_replace_recargo_item(comprobante, recargo_total)
    _recalcular_totales_comprobante(comprobante)

    return pagos_normalizados, _q2(recargo_total)


def _create_cupon_tarjeta_from_pago(comprobante, pago, monto_final):
    """
    Replica lo que hace el admin: crea cupón si el pago es tarjeta y tiene plan.
    """
    plan_cuota = pago.get("_plan_cuota_obj")
    if not plan_cuota:
        return None

    plan_maestro = plan_cuota.plan
    if not plan_maestro or not plan_maestro.tarjeta:
        return None

    tarjeta_cupon = (pago.get("tarjeta_cupon") or pago.get("cupon") or pago.get("referencia") or "S/N").strip()
    tarjeta_lote = (pago.get("tarjeta_lote") or pago.get("lote") or "").strip()

    return CuponTarjeta.objects.create(
        tarjeta=plan_maestro.tarjeta,
        plan=plan_maestro,
        cupon=tarjeta_cupon or "S/N",
        lote=tarjeta_lote,
        cuotas=plan_cuota.cuotas,
        monto=_q2(monto_final),
        fecha_operacion=comprobante.fecha,
        estado=CuponTarjeta.Estado.PENDIENTE,
    )


def _registrar_pagos_contado(comprobante, request, pagos_data):
    """
    Registra recibo + valores + imputación + movimientos.
    """
    if not pagos_data:
        return

    if comprobante.condicion_venta != ComprobanteVenta.CondicionVenta.CONTADO:
        return

    recibo = Recibo.objects.create(
        cliente=comprobante.cliente,
        fecha=comprobante.fecha,
        estado=Recibo.Estado.CONFIRMADO,
        origen=Recibo.Origen.CONTADO,
        observaciones=f"Cobro auto. Factura {comprobante.numero_completo}",
        creado_por=request.user,
    )

    total_pagado = Decimal("0.00")

    for pago in pagos_data:
        monto_final = _q2(pago.get("_monto_final", pago.get("monto", 0)))
        if monto_final <= 0:
            continue

        tipo_valor = _infer_tipo_valor_from_pago(pago)
        destino = _resolve_destino_from_pago(pago)

        banco_origen = None
        banco_origen_id = pago.get("banco_origen")
        if banco_origen_id:
            banco_origen = Banco.objects.get(pk=banco_origen_id)

        if tipo_valor.requiere_banco and not banco_origen:
            raise ValidationError(f"El tipo de valor '{tipo_valor.nombre}' requiere banco de origen.")

        cupon_obj = None
        observaciones = (pago.get("observaciones") or pago.get("nota") or "").strip()

        if tipo_valor.es_tarjeta:
            cupon_obj = _create_cupon_tarjeta_from_pago(comprobante, pago, monto_final)

            lote = (pago.get("tarjeta_lote") or pago.get("lote") or "").strip()
            cupon = (pago.get("tarjeta_cupon") or pago.get("cupon") or "").strip()

            detalles = []
            if cupon:
                detalles.append(f"Cupón: {cupon}")
            if lote:
                detalles.append(f"Lote: {lote}")

            plan_cuota = pago.get("_plan_cuota_obj")
            if plan_cuota:
                detalles.append(f"{plan_cuota.plan.nombre} - {plan_cuota.cuotas} cuotas")

            if detalles:
                detalles_txt = " | ".join(detalles)
                observaciones = f"{detalles_txt} - {observaciones}".strip(" -")

        ReciboValor.objects.create(
            recibo=recibo,
            tipo=tipo_valor,
            monto=monto_final,
            destino=destino,
            observaciones=observaciones,
            banco_origen=banco_origen,
            referencia=(pago.get("referencia") or pago.get("nota") or pago.get("tarjeta_cupon") or ""),
            fecha_cobro=pago.get("fecha_cobro") or None,
            cuit_librador=(pago.get("cuit_librador") or ""),
        )

        total_pagado += monto_final

    if total_pagado <= 0:
        raise ValidationError("No se registraron montos de pago válidos.")

    # En contado la imputación debe cancelar el comprobante completo
    ReciboImputacion.objects.create(
        recibo=recibo,
        comprobante=comprobante,
        monto_imputado=comprobante.total,
    )

    recibo.monto_total = _q2(total_pagado)
    recibo.save(update_fields=["monto_total"])

    recibo.aplicar_finanzas()
    comprobante.refresh_from_db()


# ==============================================================================
# --- VISTAS API Y REPORTES ---
# ==============================================================================

@staff_member_required
def get_precio_articulo(request, pk):
    try:
        articulo = Articulo.objects.get(pk=pk)
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
                monto_str = item_data.get('precio_monto', item_data.get('precio', '0'))
                monto = Decimal(str(monto_str))
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
            def items(self):
                return self

            def all(self):
                return self.items_list

        fake_items = []
        for item in items_data:
            if item.get('articulo'):
                try:
                    fake_items.append(FakeItem(item))
                except Exception:
                    continue

        fake_comprobante = FakeComprobante(fake_items)
        subtotal = sum((item.subtotal for item in fake_items), Money(0, 'ARS'))
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(fake_comprobante, 'venta')
        total = subtotal + Money(sum(desglose_impuestos.values()), subtotal.currency)

        return JsonResponse({
            'subtotal': f"{subtotal.amount:,.2f}",
            'currency_symbol': subtotal.currency.code,
            'impuestos': {k: f"{v:,.2f}" for k, v in desglose_impuestos.items()},
            'total': f"{total.amount:,.2f}"
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@staff_member_required
def get_comprobante_venta_info(request, pk):
    try:
        comp = ComprobanteVenta.objects.get(pk=pk)
        return JsonResponse({
            'saldo': str(comp.saldo_pendiente),
            'total': str(comp.total),
            'id': comp.pk
        })
    except ComprobanteVenta.DoesNotExist:
        return JsonResponse({'error': 'Comprobante no encontrado'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
def reporte_cuenta_corriente(request, cliente_pk):
    cliente = get_object_or_404(Cliente, pk=cliente_pk)

    facturas = ComprobanteVenta.objects.filter(
        cliente=cliente,
        estado=ComprobanteVenta.Estado.CONFIRMADO,
        condicion_venta=ComprobanteVenta.CondicionVenta.CTA_CTE
    ).annotate(
        monto_debe=models.F('total'),
        monto_haber=models.Value(0, output_field=models.DecimalField()),
        tipo_doc=models.Value('Factura', output_field=models.CharField())
    ).values('fecha', 'numero', 'letra', 'punto_venta', 'monto_debe', 'monto_haber', 'tipo_doc', 'id')

    recibos = Recibo.objects.filter(
        cliente=cliente,
        estado=Recibo.Estado.CONFIRMADO,
        origen=Recibo.Origen.COBRANZA
    ).annotate(
        monto_debe=models.Value(0, output_field=models.DecimalField()),
        monto_haber=models.F('monto_total'),
        tipo_doc=models.Value('Recibo', output_field=models.CharField()),
        letra=models.Value('X', output_field=models.CharField()),
        punto_venta=models.Value(0, output_field=models.IntegerField())
    ).values('fecha', 'numero', 'letra', 'punto_venta', 'monto_debe', 'monto_haber', 'tipo_doc', 'id')

    movimientos = sorted(list(facturas) + list(recibos), key=lambda x: x['fecha'])

    saldo = 0
    for mov in movimientos:
        saldo += (mov['monto_debe'] - mov['monto_haber'])
        mov['saldo_acumulado'] = saldo

    return render(request, 'ventas/reporte_cta_cte.html', {
        'cliente': cliente,
        'movimientos': movimientos,
        'saldo_final': saldo,
        'hoy': timezone.now()
    })


class ComprobanteVentaViewSet(viewsets.ModelViewSet):
    from .serializers import ComprobanteVentaSerializer, ComprobanteVentaCreateSerializer

    queryset = ComprobanteVenta.objects.all().order_by('-fecha', '-numero')
    search_fields = ['numero', 'cliente__entidad__razon_social']

    def get_queryset(self):
        qs = ComprobanteVenta.objects.select_related(
            'cliente__entidad',
            'tipo_comprobante',
        ).prefetch_related('items__articulo').order_by('-fecha', '-numero')

        p = self.request.query_params

        # Estado: BR / CN / AN
        estado = p.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        # Tipo de comprobante (id)
        tipo = p.get('tipo_comprobante')
        if tipo:
            try:
                qs = qs.filter(tipo_comprobante_id=int(tipo))
            except (ValueError, TypeError):
                pass

        # Condición de venta: CO / CC
        condicion = p.get('condicion_venta')
        if condicion:
            qs = qs.filter(condicion_venta=condicion)

        # Búsqueda libre: número, razón social, CUIT, CAE
        search = (p.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(numero__icontains=search) |
                Q(cliente__entidad__razon_social__icontains=search) |
                Q(cliente__entidad__cuit__icontains=search) |
                Q(cae__icontains=search)
            ).distinct()

        # Rango de fechas (YYYY-MM-DD)
        fecha_desde = p.get('fecha_desde')
        if fecha_desde:
            try:
                qs = qs.filter(fecha__date__gte=datetime.date.fromisoformat(fecha_desde))
            except ValueError:
                pass

        fecha_hasta = p.get('fecha_hasta')
        if fecha_hasta:
            try:
                qs = qs.filter(fecha__date__lte=datetime.date.fromisoformat(fecha_hasta))
            except ValueError:
                pass

        return qs

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ComprobanteVentaCreateSerializer
        return ComprobanteVentaSerializer

    def _resolver_serie_y_deposito(self, datos_comprobante):
        if not datos_comprobante.get('serie'):
            tipo = datos_comprobante.get('tipo_comprobante')
            punto_venta = datos_comprobante.get('punto_venta', 1)
            serie = SerieDocumento.objects.filter(
                tipo_comprobante=tipo,
                punto_venta=punto_venta,
                activo=True
            ).first()
            if serie:
                datos_comprobante['serie'] = serie

        if not datos_comprobante.get('deposito'):
            if datos_comprobante.get('serie') and datos_comprobante['serie'].deposito_defecto:
                datos_comprobante['deposito'] = datos_comprobante['serie'].deposito_defecto
            else:
                principal = _get_default_deposito()
                if principal:
                    datos_comprobante['deposito'] = principal

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                items_data = serializer.validated_data.pop('items')
                datos_comprobante = serializer.validated_data
                self._resolver_serie_y_deposito(datos_comprobante)

                comprobante = ComprobanteVenta.objects.create(**datos_comprobante)

                for item_data in items_data:
                    ComprobanteVentaItem.objects.create(comprobante=comprobante, **item_data)

                _recalcular_totales_comprobante(comprobante)

                pagos_data = request.data.get('pagos', [])
                pagos_normalizados, _recargo_total = _normalizar_pagos_y_aplicar_recargos(comprobante, pagos_data)

                if pagos_normalizados and comprobante.condicion_venta == ComprobanteVenta.CondicionVenta.CONTADO:
                    _registrar_pagos_contado(comprobante, request, pagos_normalizados)

                comprobante.refresh_from_db()

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteVentaSerializer(comprobante)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """
        Soporta PATCH/PUT con nested items.
        Además:
        - recalcula recargos backend por pagos
        - agrega RECARGO_FIN
        - registra recibo si pasa a contado con pagos
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                comprobante = serializer.save()

                # Si el serializer actualizó items, recalculamos primero base
                _recalcular_totales_comprobante(comprobante)

                pagos_data = request.data.get('pagos', [])
                pagos_normalizados, _recargo_total = _normalizar_pagos_y_aplicar_recargos(comprobante, pagos_data)

                if pagos_normalizados and comprobante.condicion_venta == ComprobanteVenta.CondicionVenta.CONTADO:
                    ya_existe = Recibo.objects.filter(
                        cliente=comprobante.cliente,
                        origen=Recibo.Origen.CONTADO,
                        observaciones__icontains=comprobante.numero_completo
                    ).exists()

                    if not ya_existe:
                        _registrar_pagos_contado(comprobante, request, pagos_normalizados)

                comprobante.refresh_from_db()

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteVentaSerializer(comprobante)
        return Response(read_serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)


# ==============================================================================
# --- SECCIÓN PDF Y EMAILS ---
# ==============================================================================

def obtener_contexto_pdf(comprobante, request=None):
    """
    Prepara todo el diccionario de datos necesario para el PDF.
    """
    config = ConfiguracionEmpresa.objects.first()

    discrimina_iva = comprobante.letra in ['A', 'B', 'M']
    es_monotributo = comprobante.letra == 'C'

    items_impresion = []
    subtotal_visual_acumulado = Decimal(0)

    for item in comprobante.items.all():
        precio_neto_guardado = item.precio_unitario_original
        cantidad = item.cantidad

        try:
            tasa = item.articulo.iva if item.articulo and item.articulo.iva else Decimal("21.00")
        except Exception:
            tasa = Decimal("21.00")

        factor_iva = 1 + (tasa / 100)

        if es_monotributo:
            precio_unitario_mostrar = precio_neto_guardado * factor_iva
            subtotal_linea = precio_unitario_mostrar * cantidad
        else:
            precio_unitario_mostrar = precio_neto_guardado
            subtotal_linea = precio_unitario_mostrar * cantidad

        subtotal_visual_acumulado += subtotal_linea

        items_impresion.append({
            'codigo': item.articulo.cod_articulo if item.articulo else '-',
            'descripcion': item.articulo.descripcion if item.articulo else '-',
            'cantidad': cantidad,
            'unidad': 'Unid.',
            'precio_unitario': precio_unitario_mostrar,
            'subtotal': subtotal_linea
        })

    subtotal_comprobante = subtotal_visual_acumulado

    if discrimina_iva:
        mostrar_tabla_impuestos = True
        total_iva_calculado = comprobante.total - subtotal_comprobante
    else:
        mostrar_tabla_impuestos = False
        total_iva_calculado = Decimal(0)

    qr_afip = generar_qr_afip(comprobante)

    logo_url = None
    if config and config.logo and request:
        logo_url = request.build_absolute_uri(config.logo.url)

    template_name = 'ventas/pdf/factura_premium.html'
    if comprobante.serie and comprobante.serie.diseno_impresion:
        template_name = comprobante.serie.diseno_impresion.archivo_template

    return {
        'comprobante': comprobante,
        'items_impresion': items_impresion,
        'empresa': config.entidad if config else None,
        'config': config,
        'logo_url': logo_url,
        'discrimina_iva': discrimina_iva,
        'es_monotributo': es_monotributo,
        'subtotal_comprobante': subtotal_comprobante,
        'total_iva_calculado': total_iva_calculado,
        'mostrar_tabla_impuestos': mostrar_tabla_impuestos,
        'qr_afip': qr_afip,
        'template_name': template_name
    }


def generar_pdf_bytes(comprobante, request):
    """
    Genera el archivo PDF en memoria y devuelve los bytes.
    SOPORTE AVANZADO: Renderiza desde archivo físico O desde código HTML en BD.
    """
    context_dict = obtener_contexto_pdf(comprobante, request)
    default_template_name = context_dict.pop('template_name')

    html_string = ""
    diseno = None

    if comprobante.serie and comprobante.serie.diseno_impresion:
        diseno = comprobante.serie.diseno_impresion

    if diseno and hasattr(diseno, 'contenido_html') and diseno.contenido_html:
        try:
            template = Template(diseno.contenido_html)
            context = Context(context_dict)
            html_string = template.render(context)
        except Exception as e:
            print(f"Error renderizando plantilla de BD: {e}. Usando archivo por defecto.")
            html_string = render_to_string(default_template_name, context_dict, request=request)
    else:
        html_string = render_to_string(default_template_name, context_dict, request=request)

    pdf_file = weasyprint.HTML(
        string=html_string,
        base_url=request.build_absolute_uri()
    ).write_pdf()

    return pdf_file


def enviar_comprobante_por_email(comprobante, request):
    """
    Envía el comprobante por email usando configuración SMTP de Base de Datos.
    Soporta HTML completo en el cuerpo del mensaje.
    """
    entidad = comprobante.cliente.entidad
    email_destino = getattr(entidad, 'email', None)
    if not email_destino:
        return False, f"El cliente '{entidad.razon_social}' no tiene un email cargado."

    config_smtp = ConfiguracionSMTP.objects.filter(activo=True).first()
    if not config_smtp:
        return False, "Error: No hay un servidor de correo configurado (Parámetros > Config SMTP)."

    host_real = config_smtp.host_custom if config_smtp.host == 'custom' else config_smtp.host

    try:
        connection = get_connection(
            host=host_real,
            port=config_smtp.puerto,
            username=config_smtp.usuario,
            password=config_smtp.password,
            use_tls=config_smtp.usar_tls,
            use_ssl=config_smtp.usar_ssl
        )

        pdf_content = generar_pdf_bytes(comprobante, request)
        filename = f"{comprobante.tipo_comprobante.nombre}_{comprobante.numero_completo}.pdf"

        nombre_empresa = getattr(comprobante, 'empresa_nombre_fantasia', 'Nuestra Empresa')

        context_data = {
            'cliente': entidad.razon_social,
            'numero': comprobante.numero_completo,
            'fecha': comprobante.fecha.strftime('%d/%m/%Y'),
            'empresa': nombre_empresa,
            'vencimiento': comprobante.vto_cae.strftime('%d/%m/%Y') if comprobante.vto_cae else '-',
            'total': f"${comprobante.total:,.2f}",
            'link_pago': "https://tupagina.com/pagar"
        }

        subject = f"Su Comprobante {comprobante.numero_completo} - {nombre_empresa}"
        body_html = f"""
        <p>Estimado/a <strong>{entidad.razon_social}</strong>:</p>
        <p>Adjuntamos su comprobante electrónico <strong>{comprobante.numero_completo}</strong>.</p>
        <p>Atte,<br>{nombre_empresa}</p>
        """

        if comprobante.serie and comprobante.serie.diseno_impresion:
            diseno = comprobante.serie.diseno_impresion

            if diseno.asunto_email:
                try:
                    subject = diseno.asunto_email.format(**context_data)
                except Exception:
                    pass

            if diseno.cuerpo_email:
                try:
                    template_email = Template(diseno.cuerpo_email)
                    context_email = Context(context_data)
                    body_html = template_email.render(context_email)
                except Exception as e:
                    print(f"Error renderizando email: {e}")

        email = EmailMessage(
            subject=subject,
            body=body_html,
            from_email=config_smtp.email_from,
            to=[email_destino],
            connection=connection
        )

        email.content_subtype = "html"
        email.attach(filename, pdf_content, 'application/pdf')
        email.send()

        return True, f"Enviado correctamente a {email_destino}"

    except Exception as e:
        return False, f"Error técnico SMTP: {str(e)}"


@staff_member_required
def imprimir_comprobante_pdf(request, pk):
    comprobante = get_object_or_404(ComprobanteVenta, pk=pk)
    pdf_bytes = generar_pdf_bytes(comprobante, request)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"Comprobante_{comprobante.numero_completo}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generar_pdf_venta_api(request, pk):
    """
    Genera el PDF del comprobante respetando el diseño de impresión
    configurado en la Serie de Documento (Talonario).

    Si la serie tiene diseno_impresion con contenido_html, usa ese HTML.
    Si tiene archivo_template, usa ese archivo.
    Si no tiene diseño configurado, usa el template por defecto.
    """
    comprobante = get_object_or_404(ComprobanteVenta, pk=pk)

    try:
        pdf_file = generar_pdf_bytes(comprobante, request)
    except Exception as e:
        return Response(
            {'error': f'Error generando PDF: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f"Comprobante_{comprobante.numero_completo}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enviar_email_comprobante_api(request, pk):
    """
    Envía el comprobante por email al cliente.
    Usa la función enviar_comprobante_por_email() ya existente.
    POST /api/comprobantes-venta/{pk}/enviar-email/
    """
    comprobante = get_object_or_404(ComprobanteVenta, pk=pk)
    ok, mensaje = enviar_comprobante_por_email(comprobante, request)

    if ok:
        return Response({'ok': True, 'mensaje': mensaje}, status=status.HTTP_200_OK)
    else:
        return Response({'ok': False, 'error': mensaje}, status=status.HTTP_400_BAD_REQUEST)