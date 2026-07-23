# ventas/views.py
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
from rest_framework.decorators import action

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
    ArticuloModel = apps.get_model("inventario", "Articulo")
    RubroModel = apps.get_model("inventario", "Rubro")
    rubro_financiero, _ = RubroModel.objects.get_or_create(nombre="Financiero/Recargos")
    articulo_recargo, _ = ArticuloModel.objects.get_or_create(
        cod_articulo="RECARGO_FIN",
        defaults={
            "descripcion": "Recargo Financiero / Intereses",
            "precio_venta_monto": Decimal("0.00"),
            "administra_stock": False,
            "is_active": True,
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
    if metodo == "EF":
        destino = CuentaFondo.objects.filter(pk=1, is_active=True).first()
        if destino:
            return destino
        destino = (
            CuentaFondo.objects.filter(is_active=True, tipo=CuentaFondo.Tipo.EFECTIVO).order_by("id").first()
            or CuentaFondo.objects.filter(is_active=True).order_by("id").first()
        )
        if not destino:
            raise ValidationError("No existe una cuenta/caja destino activa para efectivo.")
        return destino
    if metodo in ("DB", "CR"):
        destino = CuentaFondo.objects.filter(pk=3, is_active=True).first()
        if destino:
            return destino
        raise ValidationError("No existe la cuenta puente de tarjetas (id 3) o no está activa.")
    raise ValidationError("Falta 'destino' para el pago informado.")


def _create_or_replace_recargo_item(comprobante, recargo_total):
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
    desc_pct = _to_decimal(getattr(comprobante, "descuento_global_pct", 0) or 0)
    if desc_pct > 0:
        factor = Decimal("1") - (desc_pct / Decimal("100"))
        subtotal_con_desc = _q2(subtotal * factor)
        total_impuestos = _q2(total_impuestos * factor)
    else:
        subtotal_con_desc = subtotal
    comprobante.subtotal = _q2(subtotal_con_desc)
    comprobante.impuestos = {k: str(_q2(v)) for k, v in desglose_impuestos.items()}
    comprobante.total = _q2(subtotal_con_desc + total_impuestos)
    comprobante.saldo_pendiente = comprobante.total
    comprobante.save(update_fields=["subtotal", "impuestos", "total", "saldo_pendiente"])


def _normalizar_pagos_y_aplicar_recargos(comprobante, pagos_data):
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
    comprobante.refresh_from_db()
    return pagos_normalizados, _q2(recargo_total)


def _create_cupon_tarjeta_from_pago(comprobante, pago, monto_final):
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
        created_by=request.user,
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
# --- VISTAS ---
# ==============================================================================

@staff_member_required
def get_precio_articulo(request, pk):
    try:
        articulo = Articulo.objects.get(pk=pk)
        return JsonResponse({'precio': str(articulo.precio_venta_monto)})
    except Articulo.DoesNotExist:
        return JsonResponse({'error': 'Artículo no encontrado'}, status=404)


@staff_member_required
def get_precio_articulo_cliente(request, cliente_pk, articulo_pk):
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
        return JsonResponse({'saldo': str(comp.saldo_pendiente), 'total': str(comp.total), 'id': comp.pk})
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
        'cliente': cliente, 'movimientos': movimientos,
        'saldo_final': saldo, 'hoy': timezone.now()
    })


class ComprobanteVentaViewSet(viewsets.ModelViewSet):
    from .serializers import ComprobanteVentaSerializer, ComprobanteVentaCreateSerializer
    queryset = ComprobanteVenta.objects.all().order_by('-fecha', '-numero')
    search_fields = ['numero', 'cliente__entidad__razon_social']

    def get_queryset(self):
        qs = ComprobanteVenta.objects.select_related(
            'cliente__entidad', 'tipo_comprobante',
        ).prefetch_related('items__articulo').order_by('-fecha', '-numero')
        p = self.request.query_params
        estado = p.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        tipo = p.get('tipo_comprobante')
        if tipo:
            try:
                qs = qs.filter(tipo_comprobante_id=int(tipo))
            except (ValueError, TypeError):
                pass
        condicion = p.get('condicion_venta')
        if condicion:
            qs = qs.filter(condicion_venta=condicion)
        search = (p.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(numero__icontains=search) |
                Q(cliente__entidad__razon_social__icontains=search) |
                Q(cliente__entidad__cuit__icontains=search) |
                Q(cae__icontains=search)
            ).distinct()
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
                tipo_comprobante=tipo, punto_venta=punto_venta, activo=True
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

            # 🚀 AQUÍ VA LA LÓGICA ROBUSTA DE AFIP (Fuera de la transacción para evitar bloqueos)
            if comprobante.estado == ComprobanteVenta.Estado.CONFIRMADO and not comprobante.cae and comprobante.serie:
                config = ConfiguracionEmpresa.objects.first()
                if config and getattr(config, 'usar_factura_electronica', True):
                    modo_fact = str(getattr(config, 'modo_facturacion', '')).strip().upper()
                    es_auto_empresa = modo_fact in ['AUTO', 'TRUE', '1', 'T']

                    if hasattr(config, 'solicitar_cae_automaticamente'):
                        es_auto_empresa = getattr(config, 'solicitar_cae_automaticamente')

                    if es_auto_empresa and getattr(comprobante.serie, 'solicitar_cae_automaticamente', False):
                        schema_name = getattr(request.tenant, 'schema_name', 'public')
                        from ventas.tasks import tarea_solicitar_cae
                        tarea_solicitar_cae.delay(comprobante.pk, schema_name)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteVentaSerializer(comprobante)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                comprobante = serializer.save()
                if not getattr(comprobante, 'descuento_global_pct', 0):
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

            # 🚀 AQUÍ SE REPITE LA LÓGICA DE AFIP
            if comprobante.estado == ComprobanteVenta.Estado.CONFIRMADO and not comprobante.cae and comprobante.serie:
                config = ConfiguracionEmpresa.objects.first()
                if config and getattr(config, 'usar_factura_electronica', True):
                    modo_fact = str(getattr(config, 'modo_facturacion', '')).strip().upper()
                    es_auto_empresa = modo_fact in ['AUTO', 'TRUE', '1', 'T']

                    if hasattr(config, 'solicitar_cae_automaticamente'):
                        es_auto_empresa = getattr(config, 'solicitar_cae_automaticamente')

                    if es_auto_empresa and getattr(comprobante.serie, 'solicitar_cae_automaticamente', False):
                        schema_name = getattr(request.tenant, 'schema_name', 'public')
                        from ventas.tasks import tarea_solicitar_cae
                        tarea_solicitar_cae.delay(comprobante.pk, schema_name)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        read_serializer = ComprobanteVentaSerializer(comprobante)
        return Response(read_serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='reintentar-cae')
    def reintentar_cae(self, request, pk=None):
        """
        Endpoint para reintentar o solicitar el CAE manualmente desde el Frontend.
        URL generada: POST /api/comprobantes-venta/{pk}/reintentar-cae/
        """
        comprobante = self.get_object()

        if comprobante.cae:
            return Response({'error': 'El comprobante ya posee CAE.'}, status=status.HTTP_400_BAD_REQUEST)

        if comprobante.estado != ComprobanteVenta.Estado.CONFIRMADO:
            return Response({'error': 'El comprobante debe estar Confirmado para solicitar CAE.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Enviar a Celery (o procesar sincrónicamente, según prefieras)
        schema_name = getattr(request.tenant, 'schema_name', 'public')
        from ventas.tasks import tarea_solicitar_cae
        tarea_solicitar_cae.delay(comprobante.pk, schema_name)

        return Response({
            'ok': True,
            'mensaje': 'Solicitud enviada a AFIP. Por favor, actualice en unos segundos.'
        }, status=status.HTTP_200_OK)


# ==============================================================================
# --- PDF Y EMAILS ---
# ==============================================================================

def obtener_contexto_pdf(comprobante, request=None):
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
            host=host_real, port=config_smtp.puerto,
            username=config_smtp.usuario, password=config_smtp.password,
            use_tls=config_smtp.usar_tls, use_ssl=config_smtp.usar_ssl
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
            subject=subject, body=body_html,
            from_email=config_smtp.email_from, to=[email_destino], connection=connection
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
    comprobante = get_object_or_404(ComprobanteVenta, pk=pk)
    try:
        pdf_file = generar_pdf_bytes(comprobante, request)
    except Exception as e:
        return Response({'error': f'Error generando PDF: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f"Comprobante_{comprobante.numero_completo}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enviar_email_comprobante_api(request, pk):
    comprobante = get_object_or_404(ComprobanteVenta, pk=pk)
    ok, mensaje = enviar_comprobante_por_email(comprobante, request)
    if ok:
        return Response({'ok': True, 'mensaje': mensaje}, status=status.HTTP_200_OK)
    else:
        return Response({'ok': False, 'error': mensaje}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def informe_saldos_clientes_api(request):
    from django.db.models import Sum, Count, Avg, Max

    hoy = timezone.localdate()
    fecha_90d = hoy - timezone.timedelta(days=90)

    saldos = (
        ComprobanteVenta.objects
        .filter(estado=ComprobanteVenta.Estado.CONFIRMADO, saldo_pendiente__gt=0)
        .values('cliente_id')
        .annotate(saldo_total=Sum('saldo_pendiente'), comprobantes_impagos=Count('id'))
    )
    saldos_map = {s['cliente_id']: s for s in saldos}

    ranking = (
        ComprobanteVenta.objects
        .filter(estado=ComprobanteVenta.Estado.CONFIRMADO, fecha__date__gte=fecha_90d)
        .values('cliente_id')
        .annotate(
            total_vendido=Sum('total'), cantidad_comprobantes=Count('id'),
            ticket_promedio=Avg('total'), ultima_compra=Max('fecha'),
        )
        .order_by('-total_vendido')
    )
    ranking_map = {r['cliente_id']: r for r in ranking}

    all_ids = set(list(saldos_map.keys()) + [r['cliente_id'] for r in ranking])
    clientes_qs = (
        Cliente.objects.filter(pk__in=all_ids)
        .select_related('entidad', 'entidad__situacion_iva')
        .order_by('entidad__razon_social')
    )

    resultado = []
    for c in clientes_qs:
        s = saldos_map.get(c.pk, {})
        r = ranking_map.get(c.pk, {})
        saldo_total = float(s.get('saldo_total') or 0)
        limite = float(c.limite_credito or 0)
        dias_venc = int(c.dias_vencimiento or 0)
        deuda_vencida = 0.0
        if saldo_total > 0:
            for comp in ComprobanteVenta.objects.filter(
                cliente=c, estado=ComprobanteVenta.Estado.CONFIRMADO, saldo_pendiente__gt=0
            ):
                fecha_base = comp.fecha.date() if comp.fecha else hoy
                fecha_venc = fecha_base + timezone.timedelta(days=dias_venc)
                if fecha_venc < hoy:
                    deuda_vencida += float(comp.saldo_pendiente)
        ultima_compra = r.get('ultima_compra')
        resultado.append({
            'id': c.pk,
            'codigo': c.codigo_cliente or '',
            'razon_social': c.entidad.razon_social if c.entidad else f'Cliente #{c.pk}',
            'cuit': c.entidad.cuit if c.entidad else '',
            'situacion_iva': c.entidad.situacion_iva.nombre if c.entidad and c.entidad.situacion_iva else '',
            'limite_credito': limite,
            'permite_cta_cte': c.permite_cta_cte,
            'saldo_total': saldo_total,
            'deuda_vencida': deuda_vencida,
            'deuda_no_vencida': saldo_total - deuda_vencida,
            'comprobantes_impagos': s.get('comprobantes_impagos') or 0,
            'riesgo': 'EXCEDIDO' if (limite > 0 and saldo_total > limite) or deuda_vencida > 0 else 'NORMAL',
            'total_vendido_90d': float(r.get('total_vendido') or 0),
            'cantidad_comprobantes_90d': r.get('cantidad_comprobantes') or 0,
            'ticket_promedio_90d': float(r.get('ticket_promedio') or 0),
            'ultima_compra': ultima_compra.isoformat() if ultima_compra else None,
        })
    return Response(resultado)


def _fmt_money(n):
    """Formatea número como $ X.XXX,XX (formato AR)."""
    return "$ {:,.2f}".format(float(n or 0)).replace(',', 'X').replace('.', ',').replace('X', '.')


def _build_estado_cuenta_pdf_html(cliente, entidad, dashboard, nombre_empresa, hoy_str):
    """Genera el HTML del PDF del estado de cuenta — sin f-strings con expresiones complejas."""
    saldo      = dashboard.get('saldo_total', 0)
    vencida    = dashboard.get('deuda_vencida', 0)
    no_vencida = dashboard.get('deuda_no_vencida', 0)
    riesgo     = dashboard.get('riesgo', 'NORMAL')
    impagos    = dashboard.get('comprobantes_impagos', 0)
    limite_credito = dashboard.get('limite_credito', 0)

    kpis         = dashboard.get('kpis') or {}
    kpi_ventas   = _fmt_money(kpis.get('total_vendido_30d', 0))
    kpi_ticket   = _fmt_money(kpis.get('ticket_promedio_90d', 0))
    kpi_comp_90d = kpis.get('cantidad_comprobantes_90d', 0)
    kpi_dias     = kpis.get('dias_desde_ultima_compra', '—')
    if kpi_dias is None:
        kpi_dias = '—'

    riesgo_color = '#dc2626' if riesgo == 'EXCEDIDO' else '#d97706' if riesgo == 'SEGUIMIENTO' else '#16a34a'
    riesgo_label = 'EXCEDIDO' if riesgo == 'EXCEDIDO' else 'EN SEGUIMIENTO' if riesgo == 'SEGUIMIENTO' else 'NORMAL'
    vencida_color = '#dc2626' if float(vencida) > 0 else '#16a34a'
    sit_iva = entidad.situacion_iva.nombre if entidad.situacion_iva else '—'
    dias_vto = cliente.dias_vencimiento or 0

    # Límite de crédito row
    limite_row = ''
    if float(limite_credito) > 0:
        limite_row = (
            '<div class="ficha-row">'
            '<span class="ficha-key">Límite de crédito</span>'
            '<span class="ficha-val">' + _fmt_money(limite_credito) + '</span>'
            '</div>'
        )

    # Aging
    aging = dashboard.get('aging') or {}
    aging_rows = [
        ('0 – 30 días',  'bucket_0_30',    '#16a34a'),
        ('31 – 60 días', 'bucket_31_60',   '#d97706'),
        ('61 – 90 días', 'bucket_61_90',   '#ea580c'),
        ('+ 90 días',    'bucket_90_plus', '#dc2626'),
    ]
    aging_html = ''
    for label, key, color in aging_rows:
        val = aging.get(key, 0)
        if float(val) > 0:
            aging_html += (
                '<tr><td>' + label + '</td>'
                '<td style="text-align:right;color:' + color + ';font-weight:700">'
                + _fmt_money(val) + '</td></tr>'
            )

    aging_section = ''
    if aging_html:
        aging_section = (
            '<div class="section-title">Antigüedad de deuda</div>'
            '<table><thead><tr><th>Período</th><th style="text-align:right">Monto</th></tr></thead>'
            '<tbody>' + aging_html + '</tbody></table>'
        )

    # Movimientos
    movs = dashboard.get('movimientos_cta_cte') or []
    filas_mov = ''
    for i, mv in enumerate(movs):
        bg = '#f8fafc' if i % 2 == 0 else '#fff'
        fecha_mov = (mv.get('fecha') or '')[:10].replace('-', '/')
        debe_str  = _fmt_money(mv['debe'])  if float(mv.get('debe', 0)) > 0 else '—'
        haber_str = _fmt_money(mv['haber']) if float(mv.get('haber', 0)) > 0 else '—'
        saldo_val = float(mv.get('saldo', 0))
        saldo_color = '#dc2626' if saldo_val > 0 else '#16a34a'
        filas_mov += (
            '<tr style="background:' + bg + '">'
            '<td>' + fecha_mov + '</td>'
            '<td>' + str(mv.get('tipo', '')) + '</td>'
            '<td style="font-family:monospace">' + str(mv.get('numero', '')) + '</td>'
            '<td style="text-align:right">' + debe_str + '</td>'
            '<td style="text-align:right;color:#16a34a">' + haber_str + '</td>'
            '<td style="text-align:right;font-weight:700;color:' + saldo_color + '">'
            + _fmt_money(saldo_val) + '</td>'
            '</tr>'
        )

    movs_section = ''
    if filas_mov:
        movs_section = (
            '<div class="section-title">Movimientos de cuenta corriente</div>'
            '<table><thead><tr>'
            '<th>Fecha</th><th>Tipo</th><th>Número</th>'
            '<th style="text-align:right">Debe</th>'
            '<th style="text-align:right">Haber</th>'
            '<th style="text-align:right">Saldo</th>'
            '</tr></thead><tbody>' + filas_mov +
            '<tr class="tr-total"><td colspan="5">Saldo Final</td>'
            '<td style="text-align:right;color:#dc2626">' + _fmt_money(saldo) + '</td>'
            '</tr></tbody></table>'
        )

    html = """<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:Arial,sans-serif;font-size:9pt;color:#1e293b;padding:14mm 16mm}
  .header{display:flex;justify-content:space-between;align-items:flex-start;
          padding-bottom:10px;border-bottom:3px solid #1e3a5f;margin-bottom:14px}
  .empresa-nombre{font-size:15pt;font-weight:800;color:#1e3a5f}
  .doc-titulo{font-size:13pt;font-weight:800;color:#1e3a5f;text-align:right}
  .doc-sub{font-size:7.5pt;color:#64748b;text-align:right;margin-top:4px}
  .ficha-grid{display:flex;gap:10px;margin-bottom:14px}
  .ficha-box{flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 12px}
  .ficha-box-accent{background:#e8f0f9;border-color:#b8cfe8}
  .ficha-titulo{font-size:7pt;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
                color:#64748b;margin-bottom:7px;padding-bottom:5px;border-bottom:1px solid #e2e8f0}
  .ficha-row{display:flex;justify-content:space-between;margin-bottom:4px;font-size:8.5pt}
  .ficha-key{color:#64748b}
  .ficha-val{font-weight:600;font-family:monospace}
  .kpi-strip{display:flex;gap:8px;margin-bottom:14px}
  .kpi{flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;
       padding:8px 10px;text-align:center}
  .kpi-label{font-size:7pt;font-weight:700;text-transform:uppercase;
             letter-spacing:.06em;color:#64748b;margin-bottom:3px}
  .kpi-val{font-size:11pt;font-weight:800;font-family:monospace}
  .section-title{font-size:7.5pt;font-weight:800;text-transform:uppercase;
                 letter-spacing:.09em;color:#1e3a5f;border-bottom:2px solid #1e3a5f;
                 padding-bottom:4px;margin-bottom:8px}
  table{width:100%;border-collapse:collapse;font-size:8pt;margin-bottom:14px}
  thead tr{background:#1e3a5f;color:#fff}
  th{padding:5px 7px;font-size:7pt;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
  td{padding:5px 7px;border-bottom:1px solid #e2e8f0}
  .tr-total td{background:#e8f0f9;border-top:2px solid #1e3a5f;font-weight:800}
  .footer{margin-top:16px;padding-top:8px;border-top:1px solid #e2e8f0;
          font-size:7pt;color:#94a3b8;text-align:center}
  .badge{display:inline-block;padding:2px 10px;border-radius:20px;
         font-size:7.5pt;font-weight:800;text-transform:uppercase;color:#fff}
</style></head><body>

<div class="header">
  <div><div class="empresa-nombre">""" + nombre_empresa + """</div></div>
  <div>
    <div class="doc-titulo">Estado de Cuenta</div>
    <div class="doc-sub">Emitido el """ + hoy_str + """</div>
  </div>
</div>

<div class="ficha-grid">
  <div class="ficha-box">
    <div class="ficha-titulo">Cliente</div>
    <div class="ficha-row"><span class="ficha-key">Razón Social</span>
      <span class="ficha-val" style="font-weight:800">""" + entidad.razon_social + """</span></div>
    <div class="ficha-row"><span class="ficha-key">CUIT</span>
      <span class="ficha-val">""" + (entidad.cuit or '—') + """</span></div>
    <div class="ficha-row"><span class="ficha-key">Situación IVA</span>
      <span class="ficha-val">""" + sit_iva + """</span></div>
    <div class="ficha-row"><span class="ficha-key">Vto. crédito</span>
      <span class="ficha-val">""" + str(dias_vto) + """ días</span></div>
  </div>
  <div class="ficha-box ficha-box-accent">
    <div class="ficha-titulo">Resumen financiero</div>
    <div class="ficha-row"><span class="ficha-key">Saldo Total</span>
      <span class="ficha-val" style="color:#dc2626;font-size:11pt;font-weight:800">""" + _fmt_money(saldo) + """</span></div>
    <div class="ficha-row"><span class="ficha-key">Deuda Vencida</span>
      <span class="ficha-val" style="color:""" + vencida_color + """">""" + _fmt_money(vencida) + """</span></div>
    <div class="ficha-row"><span class="ficha-key">No Vencida</span>
      <span class="ficha-val" style="color:#16a34a">""" + _fmt_money(no_vencida) + """</span></div>
    <div class="ficha-row"><span class="ficha-key">Comprobantes impagos</span>
      <span class="ficha-val">""" + str(impagos) + """</span></div>
    """ + limite_row + """
    <div class="ficha-row" style="margin-top:6px"><span class="ficha-key">Estado</span>
      <span class="badge" style="background:""" + riesgo_color + """">""" + riesgo_label + """</span>
    </div>
  </div>
</div>

<div class="kpi-strip">
  <div class="kpi"><div class="kpi-label">Ventas 30 días</div>
    <div class="kpi-val" style="color:#16a34a">""" + kpi_ventas + """</div></div>
  <div class="kpi"><div class="kpi-label">Ticket promedio</div>
    <div class="kpi-val">""" + kpi_ticket + """</div></div>
  <div class="kpi"><div class="kpi-label">Comprobantes 90d</div>
    <div class="kpi-val">""" + str(kpi_comp_90d) + """</div></div>
  <div class="kpi"><div class="kpi-label">Días sin comprar</div>
    <div class="kpi-val">""" + str(kpi_dias) + """</div></div>
</div>

""" + aging_section + movs_section + """

<div class="footer">""" + nombre_empresa + """ · Estado de cuenta emitido el """ + hoy_str + """ · Sistema de Gestión PyME</div>
</body></html>"""

    return html


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enviar_estado_cuenta_email_api(request, pk):
    """
    Genera el PDF del estado de cuenta y lo envía como adjunto por email.
    Cuerpo: mensaje simple con resumen. Adjunto: PDF completo.
    """
    from .clientes_dashboard_service import ClienteDashboardService

    cliente = get_object_or_404(
        Cliente.objects.select_related('entidad', 'entidad__situacion_iva'),
        pk=pk
    )
    entidad = cliente.entidad
    email_destino = request.data.get('email') or getattr(entidad, 'email', None)

    if not email_destino:
        return Response(
            {'error': (
                f"El cliente '{entidad.razon_social}' no tiene un email registrado. "
                'Indicá uno en el body como {"email": "..."}'
            )},
            status=400
        )

    config_smtp = ConfiguracionSMTP.objects.filter(activo=True).first()
    if not config_smtp:
        return Response(
            {'error': 'No hay un servidor de correo configurado (Parámetros > Config SMTP).'},
            status=400
        )

    try:
        dashboard = ClienteDashboardService.build_dashboard(cliente)
        hoy       = timezone.localdate()
        hoy_str   = hoy.strftime('%d/%m/%Y')

        config_empresa = None
        try:
            config_empresa = ConfiguracionEmpresa.objects.select_related('entidad').first()
        except Exception:
            pass

        nombre_empresa = (
            getattr(config_empresa, 'nombre_fantasia', None)
            or (getattr(config_empresa.entidad, 'razon_social', None) if config_empresa else None)
            or 'Nuestra Empresa'
        )

        saldo      = dashboard.get('saldo_total', 0)
        vencida    = dashboard.get('deuda_vencida', 0)
        no_vencida = dashboard.get('deuda_no_vencida', 0)
        impagos    = dashboard.get('comprobantes_impagos', 0)
        vencida_color = '#dc2626' if float(vencida) > 0 else '#16a34a'

        # ── Generar PDF ───────────────────────────────────────────────────
        pdf_html  = _build_estado_cuenta_pdf_html(
            cliente, entidad, dashboard, nombre_empresa, hoy_str
        )
        pdf_bytes = weasyprint.HTML(string=pdf_html).write_pdf()

        # ── Cuerpo email — simple con resumen ─────────────────────────────
        body_html = (
            '<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#1e293b">'
            '<div style="background:#1e3a5f;padding:24px 28px;border-radius:8px 8px 0 0">'
            '<h2 style="color:#fff;margin:0;font-size:18px">Estado de Cuenta — ' + hoy_str + '</h2>'
            '<p style="color:#93c5fd;margin:4px 0 0;font-size:13px">' + nombre_empresa + '</p>'
            '</div>'
            '<div style="border:1px solid #e2e8f0;border-top:none;padding:24px 28px;border-radius:0 0 8px 8px">'
            '<p style="margin:0 0 16px">Estimado/a <strong>' + entidad.razon_social + '</strong>,</p>'
            '<p style="margin:0 0 16px">Le enviamos adjunto su estado de cuenta al día <strong>' + hoy_str + '</strong>.</p>'
            '<table style="width:100%;border-collapse:collapse;margin-bottom:16px;font-size:13px">'
            '<tr style="background:#f8fafc">'
            '<td style="padding:10px 12px;border:1px solid #e2e8f0;color:#64748b;font-size:11px;text-transform:uppercase">Saldo total</td>'
            '<td style="padding:10px 12px;border:1px solid #e2e8f0;font-weight:800;font-size:16px;color:#dc2626;text-align:right">' + _fmt_money(saldo) + '</td>'
            '</tr>'
            '<tr>'
            '<td style="padding:8px 12px;border:1px solid #e2e8f0;color:#64748b;font-size:11px;text-transform:uppercase">Deuda vencida</td>'
            '<td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:700;color:' + vencida_color + ';text-align:right">' + _fmt_money(vencida) + '</td>'
            '</tr>'
            '<tr style="background:#f8fafc">'
            '<td style="padding:8px 12px;border:1px solid #e2e8f0;color:#64748b;font-size:11px;text-transform:uppercase">Deuda no vencida</td>'
            '<td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:700;color:#16a34a;text-align:right">' + _fmt_money(no_vencida) + '</td>'
            '</tr>'
            '<tr>'
            '<td style="padding:8px 12px;border:1px solid #e2e8f0;color:#64748b;font-size:11px;text-transform:uppercase">Comprobantes impagos</td>'
            '<td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:700;text-align:right">' + str(impagos) + '</td>'
            '</tr>'
            '</table>'
            '<p style="margin:0 0 8px;font-size:13px">El detalle completo de movimientos se encuentra en el archivo PDF adjunto.</p>'
            '<p style="margin:0;font-size:12px;color:#64748b">Ante cualquier consulta no dude en comunicarse con nosotros.</p>'
            '<div style="margin-top:20px;padding-top:16px;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;text-align:center">'
            + nombre_empresa + ' · Generado automáticamente el ' + hoy_str +
            '</div>'
            '</div>'
            '</div>'
        )

        # ── Enviar ────────────────────────────────────────────────────────
        host_real = config_smtp.host_custom if config_smtp.host == 'custom' else config_smtp.host
        connection = get_connection(
            host=host_real, port=config_smtp.puerto,
            username=config_smtp.usuario, password=config_smtp.password,
            use_tls=config_smtp.usar_tls, use_ssl=config_smtp.usar_ssl,
        )
        nombre_archivo = (
            'Estado_Cuenta_'
            + entidad.razon_social.replace(' ', '_')
            + '_' + hoy.strftime('%Y%m%d') + '.pdf'
        )
        email_msg = EmailMessage(
            subject='Estado de Cuenta — ' + entidad.razon_social + ' — ' + hoy_str,
            body=body_html,
            from_email=config_smtp.email_from,
            to=[email_destino],
            connection=connection,
        )
        email_msg.content_subtype = 'html'
        email_msg.attach(nombre_archivo, pdf_bytes, 'application/pdf')
        email_msg.send()

        return Response({'ok': True, 'mensaje': f'Estado de cuenta enviado a {email_destino}'})

    except Exception as e:
        return Response({'error': f'Error al enviar: {str(e)}'}, status=400)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_ventas_api(request):
    """
    Dashboard completo de ventas.
    Parámetros opcionales: fecha_desde, fecha_hasta (YYYY-MM-DD)
    Por defecto: últimos 30 días.
    """
    from django.db.models import Sum, Count, Avg, F, FloatField
    from django.db.models.functions import TruncDate

    hoy = timezone.localdate()

    fecha_hasta_str = request.query_params.get('fecha_hasta')
    fecha_desde_str = request.query_params.get('fecha_desde')

    try:
        fecha_hasta = datetime.date.fromisoformat(fecha_hasta_str) if fecha_hasta_str else hoy
    except ValueError:
        fecha_hasta = hoy
    try:
        fecha_desde = datetime.date.fromisoformat(fecha_desde_str) if fecha_desde_str else hoy - timezone.timedelta(days=29)
    except ValueError:
        fecha_desde = hoy - timezone.timedelta(days=29)

    dias = (fecha_hasta - fecha_desde).days + 1
    fecha_desde_ant = fecha_desde - timezone.timedelta(days=dias)
    fecha_hasta_ant = fecha_desde - timezone.timedelta(days=1)

    def base_qs(f_desde, f_hasta):
        return ComprobanteVenta.objects.filter(
            estado=ComprobanteVenta.Estado.CONFIRMADO,
            fecha__date__gte=f_desde,
            fecha__date__lte=f_hasta,
        )

    qs_actual   = base_qs(fecha_desde, fecha_hasta)
    qs_anterior = base_qs(fecha_desde_ant, fecha_hasta_ant)

    agg = qs_actual.aggregate(
        total_ventas=Sum('total'),
        cantidad_comprobantes=Count('id'),
        ticket_promedio=Avg('total'),
    )
    agg_ant = qs_anterior.aggregate(
        total_ventas=Sum('total'),
        cantidad_comprobantes=Count('id'),
    )

    def pct_cambio(actual, anterior):
        a = float(actual or 0)
        b = float(anterior or 0)
        if b == 0:
            return None
        return round(((a - b) / b) * 100, 1)

    inicio_semana = hoy - timezone.timedelta(days=hoy.weekday())
    inicio_mes    = hoy.replace(day=1)

    kpi_hoy    = base_qs(hoy, hoy).aggregate(t=Sum('total'), c=Count('id'))
    kpi_semana = base_qs(inicio_semana, hoy).aggregate(t=Sum('total'), c=Count('id'))
    kpi_mes    = base_qs(inicio_mes, hoy).aggregate(t=Sum('total'), c=Count('id'))

    ventas_por_dia = list(
        qs_actual
        .annotate(dia=TruncDate('fecha'))
        .values('dia')
        .annotate(total=Sum('total'), cantidad=Count('id'))
        .order_by('dia')
    )
    ventas_por_dia_serial = [
        {'fecha': str(v['dia']), 'total': float(v['total'] or 0), 'cantidad': v['cantidad']}
        for v in ventas_por_dia
    ]

    ranking_articulos = list(
        ComprobanteVentaItem.objects
        .filter(
            comprobante__estado=ComprobanteVenta.Estado.CONFIRMADO,
            comprobante__fecha__date__gte=fecha_desde,
            comprobante__fecha__date__lte=fecha_hasta,
        )
        .exclude(articulo__cod_articulo='RECARGO_FIN')
        .values('articulo__cod_articulo', 'articulo__descripcion')
        .annotate(
            cantidad_total=Sum('cantidad'),
            monto_total=Sum(
                F('cantidad') * F('precio_unitario_original'),
                output_field=FloatField()
            ),
            veces_vendido=Count('id'),
        )
        .order_by('-monto_total')[:15]
    )
    ranking_articulos_serial = [
        {
            'codigo':        r['articulo__cod_articulo'],
            'descripcion':   r['articulo__descripcion'],
            'cantidad':      float(r['cantidad_total'] or 0),
            'monto':         float(r['monto_total'] or 0),
            'veces_vendido': r['veces_vendido'],
        }
        for r in ranking_articulos
    ]

    ventas_por_vendedor = list(
        qs_actual
        .values(
            'cliente__vendedor__first_name',
            'cliente__vendedor__last_name',
            'cliente__vendedor__username',
        )
        .annotate(total=Sum('total'), cantidad=Count('id'))
        .order_by('-total')
    )
    ventas_por_vendedor_serial = []
    for v in ventas_por_vendedor:
        nombre = (
            (
                (v['cliente__vendedor__first_name'] or '') + ' ' +
                (v['cliente__vendedor__last_name'] or '')
            ).strip()
            or v['cliente__vendedor__username']
            or 'Sin vendedor'
        )
        ventas_por_vendedor_serial.append({
            'vendedor': nombre,
            'total':    float(v['total'] or 0),
            'cantidad': v['cantidad'],
        })

    por_condicion = list(
        qs_actual
        .values('condicion_venta')
        .annotate(total=Sum('total'), cantidad=Count('id'))
    )

    return Response({
        'periodo': {
            'desde':     str(fecha_desde),
            'hasta':     str(fecha_hasta),
            'dias':      dias,
            'desde_ant': str(fecha_desde_ant),
            'hasta_ant': str(fecha_hasta_ant),
        },
        'kpis': {
            'total_ventas':          float(agg['total_ventas'] or 0),
            'cantidad_comprobantes': agg['cantidad_comprobantes'] or 0,
            'ticket_promedio':       float(agg['ticket_promedio'] or 0),
            'vs_anterior': {
                'total_ventas':          pct_cambio(agg['total_ventas'], agg_ant['total_ventas']),
                'cantidad_comprobantes': pct_cambio(agg['cantidad_comprobantes'], agg_ant['cantidad_comprobantes']),
            },
        },
        'hoy':    {'total': float(kpi_hoy['t'] or 0),    'cantidad': kpi_hoy['c'] or 0},
        'semana': {'total': float(kpi_semana['t'] or 0), 'cantidad': kpi_semana['c'] or 0},
        'mes':    {'total': float(kpi_mes['t'] or 0),    'cantidad': kpi_mes['c'] or 0},
        'ventas_por_dia':      ventas_por_dia_serial,
        'ranking_articulos':   ranking_articulos_serial,
        'ventas_por_vendedor': ventas_por_vendedor_serial,
        'por_condicion': [
            {
                'condicion': v['condicion_venta'],
                'total':     float(v['total'] or 0),
                'cantidad':  v['cantidad'],
            }
            for v in por_condicion
        ],
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def convertir_comprobante_api(request, pk):
    """
    Crea un nuevo comprobante a partir de uno existente, según una ReglaConversionComprobante.

    Body JSON:
    {
        "regla_id": <int>,          # ID de ReglaConversionComprobante
        "serie_id": <int|null>,     # Serie destino (opcional, se busca automáticamente)
        "condicion_venta": "CO"|"CC",  # opcional, sobreescribe si regla.copia_condicion_venta=False
        "observaciones": "...",     # opcional
    }
    """
    from parametros.models import ReglaConversionComprobante, SerieDocumento

    origen = get_object_or_404(
        ComprobanteVenta.objects.select_related(
            'cliente', 'tipo_comprobante', 'serie'
        ).prefetch_related('items__articulo'),
        pk=pk
    )

    if origen.estado == ComprobanteVenta.Estado.ANULADO:
        return Response({'error': 'No se puede convertir un comprobante anulado.'}, status=400)

    regla_id = request.data.get('regla_id')
    if not regla_id:
        return Response({'error': 'Se requiere regla_id.'}, status=400)

    regla = get_object_or_404(
        ReglaConversionComprobante.objects.select_related('tipo_origen', 'tipo_destino'),
        pk=regla_id,
        activo=True,
    )

    # Validar que la regla aplica al tipo del origen
    if regla.tipo_origen != origen.tipo_comprobante:
        return Response(
            {'error': f'La regla no aplica a comprobantes de tipo "{origen.tipo_comprobante}".'},
            status=400
        )

    try:
        with transaction.atomic():
            # ── Resolver serie destino ────────────────────────────────────
            serie_id = request.data.get('serie_id')
            serie_destino = None

            if serie_id:
                serie_destino = SerieDocumento.objects.filter(
                    pk=serie_id, activo=True
                ).first()

            if not serie_destino:
                # Buscar serie activa para el tipo destino con mismo punto de venta
                serie_destino = SerieDocumento.objects.filter(
                    tipo_comprobante=regla.tipo_destino,
                    punto_venta=origen.punto_venta,
                    activo=True,
                ).first()

            if not serie_destino:
                # Cualquier serie activa del tipo destino
                serie_destino = SerieDocumento.objects.filter(
                    tipo_comprobante=regla.tipo_destino,
                    activo=True,
                ).first()

            if not serie_destino:
                return Response(
                    {'error': f'No hay ninguna serie activa configurada para '
                              f'"{regla.tipo_destino.nombre}". '
                              f'Creá una en Parámetros > Series de Documentos.'},
                    status=400
                )

            # ── Crear comprobante destino ─────────────────────────────────
            cliente      = origen.cliente if regla.copia_cliente else origen.cliente
            condicion    = origen.condicion_venta if regla.copia_condicion_venta else request.data.get('condicion_venta', 'CO')
            observaciones = request.data.get('observaciones') or origen.observaciones or ''

            nuevo = ComprobanteVenta(
                serie=serie_destino,
                tipo_comprobante=regla.tipo_destino,
                cliente=cliente,
                fecha=timezone.now(),
                estado=ComprobanteVenta.Estado.BORRADOR,
                condicion_venta=condicion,
                punto_venta=serie_destino.punto_venta,
                deposito=origen.deposito,
                observaciones=observaciones,
                descuento_global_pct=origen.descuento_global_pct,
                cliente_nombre_override=origen.cliente_nombre_override,
                cliente_cuit_override=origen.cliente_cuit_override,
                cliente_email_override=origen.cliente_email_override,
            )
            nuevo.save()

            # ── Vincular comprobantes ─────────────────────────────────────
            nuevo.comprobantes_asociados.add(origen)

            # ── Copiar ítems ──────────────────────────────────────────────
            if regla.copia_items:
                for item in origen.items.all():
                    # Excluir recargos financieros
                    if item.articulo and item.articulo.cod_articulo == 'RECARGO_FIN':
                        continue
                    ComprobanteVentaItem.objects.create(
                        comprobante=nuevo,
                        articulo=item.articulo,
                        cantidad=item.cantidad,
                        precio_unitario_original=item.precio_unitario_original,
                        descuento_pct=item.descuento_pct,
                    )

            # ── Recalcular totales ────────────────────────────────────────
            _recalcular_totales_comprobante(nuevo)
            # ── Confirmar si la regla lo indica ──────────────────────────
            if regla.confirmar_automaticamente:
                nuevo.estado = ComprobanteVenta.Estado.CONFIRMADO
                nuevo.save(update_fields=['estado'])

            nuevo.refresh_from_db()

    except Exception as e:
        return Response({'error': str(e)}, status=400)

    serializer = ComprobanteVentaSerializer(nuevo)
    return Response({
        'ok': True,
        'comprobante': serializer.data,
        'mensaje': f'{regla.etiqueta} creado correctamente como borrador.',
    }, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reglas_conversion_para_comprobante_api(request, pk):
    """
    Devuelve las reglas de conversión aplicables a un comprobante específico.
    Útil para que el frontend sepa qué botones mostrar.
    GET /api/comprobantes-venta/{pk}/reglas-conversion/
    """
    from parametros.models import ReglaConversionComprobante, SerieDocumento

    comprobante = get_object_or_404(
        ComprobanteVenta.objects.select_related('tipo_comprobante'),
        pk=pk
    )

    if not comprobante.tipo_comprobante:
        return Response([])

    reglas = ReglaConversionComprobante.objects.filter(
        tipo_origen=comprobante.tipo_comprobante,
        activo=True,
    ).select_related('tipo_origen', 'tipo_destino').order_by('orden')

    resultado = []
    for r in reglas:
        # Verificar que existe al menos una serie activa para el tipo destino
        tiene_serie = SerieDocumento.objects.filter(
            tipo_comprobante=r.tipo_destino, activo=True
        ).exists()
        resultado.append({
            'id':                   r.pk,
            'etiqueta':             r.etiqueta,
            'tipo_origen_id':       r.tipo_origen.pk,
            'tipo_origen_nombre':   r.tipo_origen.nombre,
            'tipo_destino_id':      r.tipo_destino.pk,
            'tipo_destino_nombre':  r.tipo_destino.nombre,
            'copia_items':          r.copia_items,
            'copia_cliente':        r.copia_cliente,
            'copia_condicion_venta': r.copia_condicion_venta,
            'tiene_serie_activa':   tiene_serie,
        })

    return Response(resultado)