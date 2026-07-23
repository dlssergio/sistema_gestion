# compras/serializers.py (VERSIÓN CON AUDITORÍA ERPBaseModel)

from rest_framework import serializers
from decimal import Decimal
from django.db import transaction

from .models import (
    ComprobanteCompra, ComprobanteCompraItem,
    Proveedor,
    ListaPreciosProveedor, ItemListaPreciosProveedor,
    OrdenPago, OrdenPagoImputacion, OrdenPagoValor,
)
from inventario.models import Articulo
from entidades.models import Entidad, SituacionIVA
from parametros.models import TipoComprobante, UnidadMedida, Moneda


# ─── Auxiliares ───────────────────────────────────────────────

class SituacionIVASerializer(serializers.ModelSerializer):
    class Meta:
        model = SituacionIVA
        fields = ['id', 'codigo', 'nombre']


class EntidadReadSerializer(serializers.ModelSerializer):
    situacion_iva = SituacionIVASerializer(read_only=True)
    class Meta:
        model = Entidad
        fields = ['id', 'razon_social', 'cuit', 'dni', 'email', 'situacion_iva']


class ArticuloResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Articulo
        fields = ['id', 'cod_articulo', 'descripcion']


class TipoComprobanteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoComprobante
        fields = ['id', 'nombre', 'letra', 'codigo_afip']


class MonedaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Moneda
        fields = ['id', 'nombre', 'simbolo']


# ─── Proveedor — Lista ────────────────────────────────────────

class ProveedorListSerializer(serializers.ModelSerializer):
    id            = serializers.IntegerField(source='entidad.pk', read_only=True)
    razon_social  = serializers.CharField(source='entidad.razon_social', read_only=True)
    cuit          = serializers.CharField(source='entidad.cuit', read_only=True)
    situacion_iva = serializers.CharField(
        source='entidad.situacion_iva.nombre', read_only=True, default=''
    )
    saldo_deuda   = serializers.SerializerMethodField()

    class Meta:
        model = Proveedor
        fields = [
            'id', 'codigo_proveedor', 'razon_social', 'nombre_fantasia',
            'cuit', 'situacion_iva', 'plazo_pago_dias', 'is_active', 'saldo_deuda',
        ]

    def get_saldo_deuda(self, obj):
        from django.db.models import Sum
        r = ComprobanteCompra.objects.filter(
            proveedor=obj,
            estado=ComprobanteCompra.Estado.CONFIRMADO,
            condicion_compra=ComprobanteCompra.CondicionCompra.CTA_CTE,
            tipo_comprobante__mueve_cta_cte=True,
        ).aggregate(t=Sum('saldo_pendiente'))
        return float(r['t'] or 0)


# ─── Proveedor — Detalle ──────────────────────────────────────

class ProveedorDetailSerializer(serializers.ModelSerializer):
    id                 = serializers.IntegerField(source='entidad.pk', read_only=True)
    entidad            = EntidadReadSerializer(read_only=True)
    moneda_compra_data = MonedaSerializer(source='moneda_compra', read_only=True)
    saldo_deuda        = serializers.SerializerMethodField()
    total_comprado     = serializers.SerializerMethodField()
    cant_facturas      = serializers.SerializerMethodField()

    class Meta:
        model = Proveedor
        fields = [
            'id', 'entidad', 'codigo_proveedor', 'nombre_fantasia',
            'limite_credito', 'plazo_pago_dias', 'descuento_compra',
            'moneda_compra', 'moneda_compra_data',
            'situacion_iibb', 'nro_iibb',
            'banco_nombre', 'banco_cbu', 'banco_alias',
            'banco_cuenta_nro', 'banco_tipo_cuenta',
            'contacto_nombre', 'contacto_email', 'contacto_telefono',
            'fecha_alta', 'is_active', 'observaciones',
            'saldo_deuda', 'total_comprado', 'cant_facturas',
        ]

    def get_saldo_deuda(self, obj):
        from django.db.models import Sum
        r = ComprobanteCompra.objects.filter(
            proveedor=obj,
            estado=ComprobanteCompra.Estado.CONFIRMADO,
            condicion_compra=ComprobanteCompra.CondicionCompra.CTA_CTE,
            tipo_comprobante__mueve_cta_cte=True,
        ).aggregate(t=Sum('saldo_pendiente'))
        return float(r['t'] or 0)

    def get_total_comprado(self, obj):
        from django.db.models import Sum
        r = ComprobanteCompra.objects.filter(
            proveedor=obj,
            estado=ComprobanteCompra.Estado.CONFIRMADO,
        ).aggregate(t=Sum('total'))
        return float(r['t'] or 0)

    def get_cant_facturas(self, obj):
        return ComprobanteCompra.objects.filter(
            proveedor=obj,
            estado=ComprobanteCompra.Estado.CONFIRMADO,
        ).count()


# ─── Proveedor — Escritura CON edición de Entidad ────────────

class ProveedorWriteSerializer(serializers.ModelSerializer):
    """
    Escritura de Proveedor + Entidad anidada.
    Permite editar razon_social, cuit, email, situacion_iva directamente.
    """
    id            = serializers.IntegerField(source='entidad.pk', read_only=True)
    moneda_compra = serializers.PrimaryKeyRelatedField(
        queryset=Moneda.objects.all(), required=False, allow_null=True
    )

    # ── Campos de Entidad (write-only) ─────
    razon_social  = serializers.CharField(required=False, allow_blank=True, write_only=True)
    cuit          = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    email         = serializers.EmailField(required=False, allow_blank=True, allow_null=True, write_only=True)
    situacion_iva = serializers.PrimaryKeyRelatedField(
        queryset=SituacionIVA.objects.all(), required=False, allow_null=True, write_only=True
    )

    class Meta:
        model = Proveedor
        fields = [
            'id',
            # Entidad (write-only)
            'razon_social', 'cuit', 'email', 'situacion_iva',
            # Proveedor
            'codigo_proveedor', 'nombre_fantasia',
            'limite_credito', 'plazo_pago_dias', 'descuento_compra', 'moneda_compra',
            'situacion_iibb', 'nro_iibb',
            'banco_nombre', 'banco_cbu', 'banco_alias', 'banco_cuenta_nro', 'banco_tipo_cuenta',
            'contacto_nombre', 'contacto_email', 'contacto_telefono',
            'fecha_alta', 'is_active', 'observaciones',
        ]

    def _pop_entidad_fields(self, validated_data):
        """Extrae campos de entidad del dict validado."""
        return {
            k: validated_data.pop(k)
            for k in ['razon_social', 'cuit', 'email', 'situacion_iva']
            if k in validated_data
        }

    def update(self, instance, validated_data):
        entidad_fields = self._pop_entidad_fields(validated_data)

        # Actualizar Entidad si hay campos de entidad
        if entidad_fields:
            entidad = instance.entidad
            for attr, value in entidad_fields.items():
                setattr(entidad, attr, value)
            entidad.save()

        # Actualizar Proveedor
        return super().update(instance, validated_data)

    def create(self, validated_data):
        entidad_fields = self._pop_entidad_fields(validated_data)
        razon_social   = entidad_fields.pop('razon_social', '')
        cuit           = entidad_fields.pop('cuit', None)
        email          = entidad_fields.pop('email', None)
        situacion_iva  = entidad_fields.pop('situacion_iva', None)

        with transaction.atomic():
            entidad = Entidad.objects.create(
                razon_social=razon_social,
                cuit=cuit or '',
                email=email or '',
                situacion_iva=situacion_iva,
            )
            proveedor = Proveedor.objects.create(entidad=entidad, **validated_data)
        return proveedor


# ─── Comprobantes de Compra ───────────────────────────────────

class ComprobanteCompraItemReadSerializer(serializers.ModelSerializer):
    articulo       = ArticuloResumenSerializer(read_only=True)
    costo_unitario = serializers.DecimalField(
        source='precio_costo_unitario_monto', max_digits=14, decimal_places=4, read_only=True
    )
    subtotal       = serializers.SerializerMethodField()

    class Meta:
        model = ComprobanteCompraItem
        fields = ['id', 'articulo', 'cantidad', 'costo_unitario', 'subtotal']

    def get_subtotal(self, obj):
        return float((obj.cantidad or Decimal(0)) * (obj.precio_costo_unitario_monto or Decimal(0)))


class ComprobanteCompraItemWriteSerializer(serializers.ModelSerializer):
    articulo       = serializers.PrimaryKeyRelatedField(queryset=Articulo.objects.all())
    costo_unitario = serializers.DecimalField(
        source='precio_costo_unitario_monto', max_digits=14, decimal_places=4
    )

    class Meta:
        model = ComprobanteCompraItem
        fields = ['articulo', 'cantidad', 'costo_unitario']


class ComprobanteCompraListSerializer(serializers.ModelSerializer):
    proveedor_nombre  = serializers.CharField(source='proveedor.entidad.razon_social', read_only=True)
    tipo_nombre       = serializers.CharField(source='tipo_comprobante.nombre', read_only=True)
    estado_display    = serializers.CharField(source='get_estado_display', read_only=True)
    condicion_display = serializers.CharField(source='get_condicion_compra_display', read_only=True)
    numero_completo   = serializers.SerializerMethodField()

    class Meta:
        model = ComprobanteCompra
        fields = [
            'id', 'numero_completo', 'letra',
            'proveedor', 'proveedor_nombre',
            'tipo_comprobante', 'tipo_nombre',
            'fecha', 'estado', 'estado_display',
            'condicion_compra', 'condicion_display',
            'total', 'saldo_pendiente',
        ]

    def get_numero_completo(self, obj):
        return f"{str(obj.punto_venta or 0).zfill(4)}-{str(obj.numero or 0).zfill(8)}"


class ComprobanteCompraOrigenSerializer(serializers.ModelSerializer):
    """Serializer reducido para mostrar el origen de un comprobante."""
    tipo_nombre    = serializers.CharField(source='tipo_comprobante.nombre', read_only=True)
    numero_completo = serializers.SerializerMethodField()

    class Meta:
        model = ComprobanteCompra
        fields = ['id', 'tipo_nombre', 'numero_completo', 'fecha', 'estado']

    def get_numero_completo(self, obj):
        return f"{str(obj.punto_venta or 0).zfill(4)}-{str(obj.numero or 0).zfill(8)}"


class ComprobanteCompraDetailSerializer(serializers.ModelSerializer):
    proveedor         = ProveedorListSerializer(read_only=True)
    tipo_comprobante  = TipoComprobanteSerializer(read_only=True)
    items             = ComprobanteCompraItemReadSerializer(many=True, read_only=True)
    estado_display    = serializers.CharField(source='get_estado_display', read_only=True)
    condicion_display = serializers.CharField(source='get_condicion_compra_display', read_only=True)
    numero_completo   = serializers.SerializerMethodField()
    deposito_nombre   = serializers.CharField(source='deposito.nombre', read_only=True, default='')
    # Trazabilidad: comprobante del que deriva y los que se generaron a partir de este
    comprobante_origen    = ComprobanteCompraOrigenSerializer(read_only=True)
    comprobantes_derivados = ComprobanteCompraOrigenSerializer(many=True, read_only=True)

    class Meta:
        model = ComprobanteCompra
        fields = [
            'id', 'numero_completo', 'letra', 'punto_venta', 'numero',
            'proveedor', 'tipo_comprobante',
            'deposito', 'deposito_nombre',
            'fecha', 'estado', 'estado_display',
            'condicion_compra', 'condicion_display',
            'subtotal', 'impuestos', 'total', 'saldo_pendiente',
            'stock_aplicado',
            'comprobante_origen', 'comprobantes_derivados',
            'items',
        ]

    def get_numero_completo(self, obj):
        return f"{str(obj.punto_venta or 0).zfill(4)}-{str(obj.numero or 0).zfill(8)}"


class ComprobanteCompraWriteSerializer(serializers.ModelSerializer):
    proveedor          = serializers.PrimaryKeyRelatedField(queryset=Proveedor.objects.all())
    tipo_comprobante   = serializers.PrimaryKeyRelatedField(queryset=TipoComprobante.objects.all())
    comprobante_origen = serializers.PrimaryKeyRelatedField(
        queryset=ComprobanteCompra.objects.all(), required=False, allow_null=True
    )
    items              = ComprobanteCompraItemWriteSerializer(many=True)

    class Meta:
        model = ComprobanteCompra
        fields = [
            'proveedor', 'tipo_comprobante', 'deposito',
            'punto_venta', 'numero', 'fecha',
            'estado', 'condicion_compra',
            'comprobante_origen',
            'items',
        ]


# Alias de compatibilidad
ComprobanteCompraSerializer       = ComprobanteCompraDetailSerializer
ComprobanteCompraCreateSerializer = ComprobanteCompraWriteSerializer


# ─── Órdenes de Pago ─────────────────────────────────────────

class OrdenPagoImputacionSerializer(serializers.ModelSerializer):
    numero_comprobante = serializers.SerializerMethodField()
    tipo_comprobante   = serializers.CharField(source='comprobante.tipo_comprobante.nombre', read_only=True)
    fecha_comprobante  = serializers.DateTimeField(source='comprobante.fecha', read_only=True)
    total_comprobante  = serializers.DecimalField(
        source='comprobante.total', max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = OrdenPagoImputacion
        fields = [
            'id', 'comprobante', 'numero_comprobante',
            'tipo_comprobante', 'fecha_comprobante',
            'total_comprobante', 'monto_imputado',
        ]

    def get_numero_comprobante(self, obj):
        c = obj.comprobante
        return f"{str(c.punto_venta or 0).zfill(4)}-{str(c.numero or 0).zfill(8)}"


class OrdenPagoValorSerializer(serializers.ModelSerializer):
    tipo_nombre   = serializers.CharField(source='tipo.nombre', read_only=True)
    cuenta_nombre = serializers.CharField(source='origen.nombre', read_only=True)

    class Meta:
        model = OrdenPagoValor
        fields = [
            'id', 'tipo', 'tipo_nombre', 'monto',
            'origen', 'cuenta_nombre',
            'cheque_propio_nro', 'es_echeq', 'fecha_pago_cheque',
            'cheque_tercero', 'referencia',
        ]


class OrdenPagoListSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source='proveedor.entidad.razon_social', read_only=True)
    estado_display   = serializers.CharField(source='get_estado_display', read_only=True)

    class Meta:
        model = OrdenPago
        fields = ['id', 'numero', 'proveedor', 'proveedor_nombre',
                  'fecha', 'estado', 'estado_display', 'monto_total']


class OrdenPagoDetailSerializer(serializers.ModelSerializer):
    proveedor      = ProveedorListSerializer(read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    imputaciones   = OrdenPagoImputacionSerializer(many=True, read_only=True)
    valores        = OrdenPagoValorSerializer(many=True, read_only=True)

    class Meta:
        model = OrdenPago
        fields = [
            'id', 'numero', 'proveedor',
            'fecha', 'estado', 'estado_display',
            'monto_total', 'observaciones',
            'finanzas_aplicadas', 'imputaciones', 'valores',
        ]


class OrdenPagoWriteSerializer(serializers.ModelSerializer):
    proveedor    = serializers.PrimaryKeyRelatedField(queryset=Proveedor.objects.all())
    imputaciones = OrdenPagoImputacionSerializer(many=True, required=False)
    valores      = OrdenPagoValorSerializer(many=True, required=False)

    class Meta:
        model = OrdenPago
        fields = ['proveedor', 'serie', 'numero', 'fecha', 'estado', 'observaciones', 'imputaciones', 'valores']


# ─── Listas de Precios ────────────────────────────────────────

class ItemListaPreciosSerializer(serializers.ModelSerializer):
    articulo_data       = ArticuloResumenSerializer(source='articulo', read_only=True)
    articulo            = serializers.PrimaryKeyRelatedField(queryset=Articulo.objects.all())
    moneda_nombre       = serializers.CharField(source='precio_lista_moneda.simbolo', read_only=True, default='')
    unidad_nombre       = serializers.CharField(source='unidad_medida_compra.simbolo', read_only=True, default='')
    costo_efectivo      = serializers.SerializerMethodField()

    # Campos opcionales con defaults seguros
    precio_lista_moneda = serializers.PrimaryKeyRelatedField(
        queryset=Moneda.objects.all(), required=False, allow_null=True
    )
    unidad_medida_compra = serializers.PrimaryKeyRelatedField(
        queryset=UnidadMedida.objects.all(), required=False, allow_null=True
    )
    descuentos_adicionales = serializers.ListField(
        child=serializers.DecimalField(max_digits=5, decimal_places=2),
        required=False, default=list
    )
    descuentos_financieros = serializers.ListField(
        child=serializers.DecimalField(max_digits=5, decimal_places=2),
        required=False, default=list
    )

    class Meta:
        model = ItemListaPreciosProveedor
        fields = [
            'id', 'articulo', 'articulo_data',
            'unidad_medida_compra', 'unidad_nombre',
            'precio_lista_monto', 'precio_lista_moneda', 'moneda_nombre',
            'bonificacion_porcentaje',
            'descuentos_adicionales', 'descuentos_financieros',
            'cantidad_minima', 'codigo_articulo_proveedor',
            'costo_efectivo',
        ]

    def get_costo_efectivo(self, obj):
        try:
            ce = obj.costo_efectivo
            return float(ce.amount) if ce else None
        except Exception:
            return None

    def _get_default_unidad(self):
        from parametros.models import UnidadMedida as UM
        unidad, _ = UM.objects.get_or_create(simbolo='UN', defaults={'nombre': 'Unidad'})
        return unidad

    def _normalizar_descuentos(self, validated_data):
        for campo in ('descuentos_adicionales', 'descuentos_financieros'):
            if campo in validated_data:
                validated_data[campo] = [float(v) for v in (validated_data[campo] or [])]
        return validated_data

    def create(self, validated_data):
        if not validated_data.get('unidad_medida_compra'):
            validated_data['unidad_medida_compra'] = self._get_default_unidad()
        validated_data = self._normalizar_descuentos(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if not validated_data.get('unidad_medida_compra'):
            validated_data['unidad_medida_compra'] = instance.unidad_medida_compra
        validated_data = self._normalizar_descuentos(validated_data)
        return super().update(instance, validated_data)


class ListaPreciosProveedorListSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source='proveedor.entidad.razon_social', read_only=True)
    cant_items       = serializers.SerializerMethodField()

    class Meta:
        model = ListaPreciosProveedor
        fields = ['id', 'proveedor', 'proveedor_nombre', 'nombre', 'codigo',
                  'vigente_desde', 'vigente_hasta', 'is_active', 'es_principal', 'cant_items']

    def get_cant_items(self, obj):
        return obj.items.count()


class ListaPreciosProveedorDetailSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source='proveedor.entidad.razon_social', read_only=True)
    items            = ItemListaPreciosSerializer(many=True, read_only=True)

    class Meta:
        model = ListaPreciosProveedor
        fields = [
            'id', 'proveedor', 'proveedor_nombre', 'nombre', 'codigo',
            'vigente_desde', 'vigente_hasta', 'is_active', 'es_principal',
            'observaciones', 'created_at', 'updated_at', 'items',
        ]