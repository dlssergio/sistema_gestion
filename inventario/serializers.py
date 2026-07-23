# inventario/serializers.py
# VERSIÓN COMPLETA — reemplaza el archivo existente

from decimal import Decimal

from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField

from .models import (
    Articulo, Marca, Rubro, Deposito,
    BalanceStock, MovimientoStockLedger,
    AjusteStock, ItemAjusteStock,
    TransferenciaInterna, ItemTransferencia,
    MotivoAjuste, TipoStock, ProveedorArticulo,
    ConversionUnidadMedida, StockArticulo,
)
from parametros.models import Impuesto, UnidadMedida, Moneda, CategoriaImpositiva
from compras.models import Proveedor as ProveedorModel


# ─────────────────────────────────────────────
#  AUXILIARES / MAESTROS
# ─────────────────────────────────────────────

class MarcaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marca
        fields = '__all__'


class RubroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rubro
        fields = '__all__'


class CategoriaImpositivaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaImpositiva
        fields = '__all__'


class ImpuestoResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Impuesto
        fields = ['id', 'nombre', 'tasa', 'es_porcentaje', 'aplica_a']


class UnidadMedidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnidadMedida
        fields = ['id', 'nombre', 'simbolo']


class MonedaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Moneda
        fields = ['id', 'nombre', 'simbolo', 'cotizacion', 'es_base']


class MotivoAjusteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotivoAjuste
        fields = '__all__'


class TipoStockSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoStock
        fields = ['id', 'codigo', 'nombre', 'es_fisico', 'es_vendible', 'es_reservado']


# ─────────────────────────────────────────────
#  DEPÓSITOS
# ─────────────────────────────────────────────

class DepositoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deposito
        fields = ['id', 'nombre', 'direccion', 'es_principal', 'permite_stock_negativo']


# ─────────────────────────────────────────────
#  CONVERSIONES DE UNIDAD
# ─────────────────────────────────────────────

class ConversionUMSerializer(serializers.ModelSerializer):
    unidad_externa_data = UnidadMedidaSerializer(source='unidad_externa', read_only=True)
    unidad_externa = serializers.PrimaryKeyRelatedField(queryset=UnidadMedida.objects.all())

    class Meta:
        model = ConversionUnidadMedida
        fields = ['id', 'unidad_externa', 'unidad_externa_data', 'factor_conversion']


# ─────────────────────────────────────────────
#  STOCK POR DEPÓSITO (para ficha de artículo)
# ─────────────────────────────────────────────

class BalanceStockSerializer(serializers.ModelSerializer):
    deposito_nombre = serializers.CharField(source='deposito.nombre', read_only=True)
    tipo_codigo = serializers.CharField(source='tipo_stock.codigo', read_only=True)
    tipo_nombre = serializers.CharField(source='tipo_stock.nombre', read_only=True)
    es_fisico = serializers.BooleanField(source='tipo_stock.es_fisico', read_only=True)
    es_vendible = serializers.BooleanField(source='tipo_stock.es_vendible', read_only=True)
    es_reservado = serializers.BooleanField(source='tipo_stock.es_reservado', read_only=True)

    class Meta:
        model = BalanceStock
        fields = [
            'id', 'deposito', 'deposito_nombre',
            'tipo_codigo', 'tipo_nombre',
            'es_fisico', 'es_vendible', 'es_reservado',
            'cantidad', 'ultima_actualizacion',
        ]


class StockArticuloResumenSerializer(serializers.ModelSerializer):
    """
    Resumen de stock legacy por depósito — para la pestaña Stock de la ficha.
    """
    deposito_nombre = serializers.CharField(source='deposito.nombre', read_only=True)
    cantidad_disponible = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )

    class Meta:
        model = StockArticulo
        fields = [
            'deposito', 'deposito_nombre',
            'cantidad_real', 'cantidad_comprometida', 'cantidad_disponible',
        ]




# ─────────────────────────────────────────────
#  PROVEEDOR DE ARTÍCULO
# ─────────────────────────────────────────────

class ProveedorArticuloSerializer(serializers.ModelSerializer):
    """
    Serializer para la relación Artículo ↔ Proveedor.
    Expone todos los campos operativos: código, descripción en el proveedor,
    y el flag es_fuente_de_verdad (fuente de precio de costo).
    """
    proveedor_id         = serializers.IntegerField(source='proveedor.pk', read_only=True)
    razon_social         = serializers.CharField(source='proveedor.entidad.razon_social', read_only=True)
    codigo_proveedor     = serializers.CharField(source='proveedor.codigo_proveedor', read_only=True)
    nombre_fantasia      = serializers.CharField(source='proveedor.nombre_fantasia', read_only=True, default=None)

    # FK de escritura
    proveedor = serializers.PrimaryKeyRelatedField(
        queryset=ProveedorModel.objects.all(),
        write_only=True,
    )

    class Meta:
        model = ProveedorArticulo
        fields = [
            'id',
            'proveedor',           # write-only (FK para crear/editar)
            'proveedor_id',        # read: PK del proveedor
            'razon_social',        # read: nombre del proveedor
            'codigo_proveedor',    # read: código interno del proveedor
            'nombre_fantasia',     # read: nombre de fantasía
            'es_fuente_de_verdad',
            'cod_articulo_proveedor',
            'descripcion_proveedor',
            'fecha_relacion',
        ]
        read_only_fields = ['fecha_relacion']

# ─────────────────────────────────────────────
#  ARTÍCULO — LECTURA (lista + detalle)
# ─────────────────────────────────────────────

class ArticuloListSerializer(serializers.ModelSerializer):
    """
    Serializer liviano para listas paginadas. Solo campos necesarios para la tabla.
    """
    marca_nombre = serializers.CharField(source='marca.nombre', default=None, read_only=True)
    rubro_nombre = serializers.CharField(source='rubro.nombre', read_only=True)
    precio_venta_monto = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    precio_costo_monto = serializers.DecimalField(max_digits=14, decimal_places=4, read_only=True)
    stock_total = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    stock_disponible = serializers.DecimalField(
        source='stock_disponible_calculado', max_digits=12, decimal_places=3, read_only=True
    )
    necesita_reposicion = serializers.BooleanField(read_only=True)
    perfil_display = serializers.CharField(source='get_perfil_display', read_only=True)

    # Campo de compatibilidad con el POS y ventas.
    # El frontend espera { amount, currency } — mantenemos este formato exacto.
    precio_venta = serializers.SerializerMethodField()
    iva_rate     = serializers.SerializerMethodField()

    class Meta:
        model = Articulo
        fields = [
            'id', 'cod_articulo', 'descripcion', 'ean',
            'marca_nombre', 'rubro_nombre',
            'perfil', 'perfil_display',
            'es_servicio', 'es_bien_de_uso',
            'administra_stock', 'is_active',
            'stock_total', 'stock_disponible',
            'stock_minimo', 'necesita_reposicion',
            'precio_costo_monto', 'precio_venta_monto', 'utilidad',
            # Campos de compatibilidad con POS/ventas
            'precio_venta', 'iva_rate',
            'permite_stock_negativo',
            'foto', 'ubicacion',
        ]

    def get_precio_venta(self, obj):
        """
        Devuelve { amount, currency } — formato que consume el POS.
        """
        return {
            'amount': f"{obj.precio_venta_monto:.2f}",
            'currency': obj.precio_venta_moneda.simbolo if obj.precio_venta_moneda else 'ARS',
        }

    def get_iva_rate(self, obj):
        for imp in obj.impuestos.all():
            if 'IVA' in (imp.nombre or '').upper():
                try:
                    return float(Decimal(str(imp.tasa)))
                except Exception:
                    return 21.0
        return 21.0


class ArticuloDetailSerializer(serializers.ModelSerializer):
    """
    Serializer completo para la ficha de artículo (detalle + pestañas).
    """
    marca = MarcaSerializer(read_only=True)
    rubro = RubroSerializer(read_only=True)
    categoria_impositiva = CategoriaImpositivaSerializer(read_only=True)
    impuestos = ImpuestoResumenSerializer(many=True, read_only=True)
    unidad_medida_stock = UnidadMedidaSerializer(read_only=True)
    unidad_medida_venta = UnidadMedidaSerializer(read_only=True)
    precio_costo_moneda = MonedaSerializer(read_only=True)
    precio_venta_moneda = MonedaSerializer(read_only=True)

    # Stock
    stock_total = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    stock_disponible = serializers.DecimalField(
        source='stock_disponible_calculado', max_digits=12, decimal_places=3, read_only=True
    )
    necesita_reposicion = serializers.BooleanField(read_only=True)
    stocks_por_deposito = StockArticuloResumenSerializer(source='stocks', many=True, read_only=True)
    balances_detallados = BalanceStockSerializer(source='balances_stock', many=True, read_only=True)

    # Conversiones
    conversiones_uom = ConversionUMSerializer(many=True, read_only=True)

    # Proveedores
    proveedor_principal  = serializers.SerializerMethodField()
    proveedores_articulo = serializers.SerializerMethodField()

    # Display fields
    perfil_display = serializers.CharField(source='get_perfil_display', read_only=True)
    iva_rate = serializers.SerializerMethodField()
    precio_final_calculado = serializers.SerializerMethodField()

    # Campo de compatibilidad con el POS y ventas.
    # El frontend espera { amount, currency } — mantenemos este formato exacto.
    precio_venta = serializers.SerializerMethodField()

    class Meta:
        model = Articulo
        fields = [
            # Identificación
            'id', 'cod_articulo', 'ean', 'qr', 'cod_fabricante',
            # Descripción
            'descripcion', 'descripcion_larga',
            # Clasificación
            'perfil', 'perfil_display', 'marca', 'rubro',
            'es_servicio', 'es_bien_de_uso',
            # Unidades
            'unidad_medida_stock', 'unidad_medida_venta', 'conversiones_uom',
            # Precios
            'precio_costo_monto', 'precio_costo_moneda',
            'precio_venta_monto', 'precio_venta_moneda',
            'precio_venta',           # ← campo { amount, currency } para POS/ventas
            'utilidad', 'precio_final_calculado',
            # Impositivo
            'categoria_impositiva', 'impuestos', 'iva_rate',
            # Stock
            'administra_stock', 'permite_stock_negativo',
            'stock_total', 'stock_disponible', 'necesita_reposicion',
            'stock_minimo', 'stock_maximo', 'stock_seguridad', 'lead_time_dias',
            'stocks_por_deposito', 'balances_detallados',
            # Logística
            'peso_kg', 'alto_cm', 'ancho_cm', 'profundidad_cm',
            'garantia_meses', 'ubicacion',
            # General
            'is_active', 'foto', 'observaciones', 'nota',
            # Relaciones
            'proveedor_principal',
            'proveedores_articulo',
        ]

    def get_precio_venta(self, obj):
        """
        Devuelve { amount, currency } — formato que consume el POS.
        """
        return {
            'amount': f"{obj.precio_venta_monto:.2f}",
            'currency': obj.precio_venta_moneda.simbolo if obj.precio_venta_moneda else 'ARS',
        }

    def get_iva_rate(self, obj):
        for imp in obj.impuestos.all():
            if 'IVA' in (imp.nombre or '').upper():
                try:
                    return float(Decimal(str(imp.tasa)))
                except Exception:
                    return 21.0
        return 21.0

    def get_precio_final_calculado(self, obj):
        try:
            precio = Decimal(str(obj.precio_venta_monto or 0))
            total_imp = Decimal('0.00')
            for imp in obj.impuestos.all():
                if imp.aplica_a not in ('venta', 'ambos'):
                    continue
                if imp.es_porcentaje:
                    total_imp += precio * (Decimal(str(imp.tasa)) / Decimal('100'))
                else:
                    total_imp += Decimal(str(imp.tasa))
            return str((precio + total_imp).quantize(Decimal('0.01')))
        except Exception:
            return None

    def get_proveedor_principal(self, obj):
        try:
            pa = obj.proveedorarticulo_set.select_related('proveedor__entidad').get(
                es_fuente_de_verdad=True
            )
            return {
                'id': pa.proveedor.pk,
                'razon_social': pa.proveedor.entidad.razon_social,
                'cod_articulo_proveedor': pa.cod_articulo_proveedor,
                'descripcion_proveedor': pa.descripcion_proveedor,
            }
        except Exception:
            return None

    def get_proveedores_articulo(self, obj):
        """Lista completa de proveedores relacionados con este artículo."""
        qs = obj.proveedorarticulo_set.select_related(
            'proveedor__entidad'
        ).order_by('-es_fuente_de_verdad', 'proveedor__entidad__razon_social')
        return [
            {
                'id':                    pa.pk,
                'proveedor_id':          pa.proveedor.pk,
                'razon_social':          pa.proveedor.entidad.razon_social,
                'codigo_proveedor':      pa.proveedor.codigo_proveedor,
                'nombre_fantasia':       pa.proveedor.nombre_fantasia,
                'es_fuente_de_verdad':   pa.es_fuente_de_verdad,
                'cod_articulo_proveedor':pa.cod_articulo_proveedor,
                'descripcion_proveedor': pa.descripcion_proveedor,
                'fecha_relacion':        pa.fecha_relacion.isoformat() if pa.fecha_relacion else None,
            }
            for pa in qs
        ]


# ─────────────────────────────────────────────
#  ARTÍCULO — ESCRITURA (create / update)
# ─────────────────────────────────────────────

class ArticuloWriteSerializer(serializers.ModelSerializer):
    """
    Serializer de escritura completo. Soporta tanto JSON (sin foto) como
    multipart/form-data (con foto). En multipart los booleanos y nulls
    llegan como strings — to_internal_value los normaliza antes de validar.
    """
    marca = serializers.PrimaryKeyRelatedField(
        queryset=Marca.objects.all(), required=False, allow_null=True
    )
    rubro = serializers.PrimaryKeyRelatedField(queryset=Rubro.objects.all())
    categoria_impositiva = serializers.PrimaryKeyRelatedField(
        queryset=CategoriaImpositiva.objects.all(), required=False, allow_null=True
    )
    impuestos = serializers.PrimaryKeyRelatedField(
        queryset=Impuesto.objects.all(), many=True, required=False
    )
    unidad_medida_stock = serializers.PrimaryKeyRelatedField(
        queryset=UnidadMedida.objects.all(), required=False
    )
    unidad_medida_venta = serializers.PrimaryKeyRelatedField(
        queryset=UnidadMedida.objects.all(), required=False
    )
    precio_costo_moneda = serializers.PrimaryKeyRelatedField(
        queryset=Moneda.objects.all(), required=False
    )
    precio_venta_moneda = serializers.PrimaryKeyRelatedField(
        queryset=Moneda.objects.all(), required=False
    )

    # Booleanos explícitos: aceptan "true"/"false" string desde FormData
    is_active              = serializers.BooleanField(required=False)
    administra_stock       = serializers.BooleanField(required=False)
    permite_stock_negativo = serializers.BooleanField(required=False)
    es_servicio            = serializers.BooleanField(required=False)
    es_bien_de_uso         = serializers.BooleanField(required=False)

    class Meta:
        model = Articulo
        fields = [
            # Identificación
            'cod_articulo', 'ean', 'qr', 'cod_fabricante',
            # Descripción
            'descripcion', 'descripcion_larga',
            # Clasificación
            'perfil', 'marca', 'rubro', 'es_servicio', 'es_bien_de_uso',
            # Unidades
            'unidad_medida_stock', 'unidad_medida_venta',
            # Precios
            'precio_costo_monto', 'precio_costo_moneda',
            'precio_venta_monto', 'precio_venta_moneda',
            'utilidad',
            # Impositivo
            'categoria_impositiva', 'impuestos',
            # Stock
            'administra_stock', 'permite_stock_negativo',
            'stock_minimo', 'stock_maximo', 'stock_seguridad', 'lead_time_dias',
            # Logística
            'peso_kg', 'alto_cm', 'ancho_cm', 'profundidad_cm',
            'garantia_meses', 'ubicacion',
            # General
            'is_active', 'foto', 'observaciones', 'nota',
        ]

    def to_internal_value(self, data):
        """
        Normaliza los datos que llegan de multipart/form-data antes de validar.
        - Convierte "true"/"false" strings a booleanos Python.
        - Convierte "null"/"undefined"/"" a None en campos opcionales.
        - Parsea 'impuestos' si llega como JSON string "[1,2,3]".
        - Elimina 'foto' si viene como string "null" para no borrar la foto existente.
        """
        if hasattr(data, '_mutable'):
            data = data.dict()
        else:
            data = dict(data)

        BOOL_FIELDS = [
            'is_active', 'administra_stock', 'permite_stock_negativo',
            'es_servicio', 'es_bien_de_uso',
        ]
        for field in BOOL_FIELDS:
            if field in data and isinstance(data[field], str):
                data[field] = data[field].lower() not in ('false', '0', 'no', '')

        NULLABLE_FIELDS = [
            'marca', 'categoria_impositiva', 'descripcion_larga', 'ean',
            'qr', 'cod_fabricante', 'ubicacion', 'observaciones', 'nota',
            'peso_kg', 'alto_cm', 'ancho_cm', 'profundidad_cm',
            'unidad_medida_stock', 'unidad_medida_venta',
            'precio_costo_moneda', 'precio_venta_moneda',
        ]
        for field in NULLABLE_FIELDS:
            if field in data and data[field] in ('null', 'undefined', ''):
                data[field] = None

        # impuestos puede llegar como JSON string "[1, 2, 3]" desde FormData
        # (el frontend lo serializa así para evitar el problema de campos repetidos)
        if 'impuestos' in data and isinstance(data['impuestos'], str):
            import json
            try:
                data['impuestos'] = json.loads(data['impuestos'])
            except (ValueError, TypeError):
                data['impuestos'] = []

        # Si foto llega como string vacío o "null", la ignoramos para no
        # sobrescribir la foto existente con None
        if 'foto' in data:
            val = data['foto']
            if isinstance(val, str) and val.lower() in ('null', 'undefined', ''):
                del data['foto']

        return super().to_internal_value(data)

    def validate_cod_articulo(self, value):
        if not value:
            return value
        instance = self.instance
        qs = Articulo.objects.filter(cod_articulo=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Ya existe un artículo con el código '{value}'."
            )
        return value

    def create(self, validated_data):
        impuestos = validated_data.pop('impuestos', [])
        articulo = super().create(validated_data)
        if impuestos:
            articulo.impuestos.set(impuestos)
        return articulo

    def update(self, instance, validated_data):
        impuestos = validated_data.pop('impuestos', None)
        articulo = super().update(instance, validated_data)
        if impuestos is not None:
            articulo.impuestos.set(impuestos)
        return articulo


# ─────────────────────────────────────────────
#  AJUSTES DE STOCK
# ─────────────────────────────────────────────

class ItemAjusteSerializer(serializers.ModelSerializer):
    articulo_codigo = serializers.CharField(source='articulo.cod_articulo', read_only=True)
    articulo_descripcion = serializers.CharField(source='articulo.descripcion', read_only=True)
    tipo_movimiento_display = serializers.CharField(
        source='get_tipo_movimiento_display', read_only=True
    )

    class Meta:
        model = ItemAjusteStock
        fields = [
            'id', 'articulo', 'articulo_codigo', 'articulo_descripcion',
            'tipo_movimiento', 'tipo_movimiento_display', 'cantidad',
        ]


class AjusteStockSerializer(serializers.ModelSerializer):
    items = ItemAjusteSerializer(many=True)
    motivo_nombre = serializers.CharField(source='motivo.nombre', read_only=True)
    deposito_nombre = serializers.CharField(source='deposito.nombre', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    created_by_nombre = serializers.SerializerMethodField()

    class Meta:
        model = AjusteStock
        fields = [
            'id', 'fecha', 'deposito', 'deposito_nombre',
            'motivo', 'motivo_nombre',
            'estado', 'estado_display',
            'observaciones', 'stock_aplicado',
            'created_by', 'created_by_nombre',
            'items',
        ]
        read_only_fields = ['estado', 'stock_aplicado', 'created_by']

    def get_created_by_nombre(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        ajuste = AjusteStock.objects.create(**validated_data)
        for item_data in items_data:
            ItemAjusteStock.objects.create(ajuste=ajuste, **item_data)
        return ajuste


class AjusteStockListSerializer(serializers.ModelSerializer):
    """Serializer liviano para la lista de ajustes."""
    motivo_nombre = serializers.CharField(source='motivo.nombre', read_only=True)
    deposito_nombre = serializers.CharField(source='deposito.nombre', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    total_items = serializers.SerializerMethodField()

    class Meta:
        model = AjusteStock
        fields = [
            'id', 'fecha', 'deposito_nombre', 'motivo_nombre',
            'estado', 'estado_display', 'total_items', 'observaciones',
        ]

    def get_total_items(self, obj):
        return obj.items.count()


# ─────────────────────────────────────────────
#  TRANSFERENCIAS ENTRE DEPÓSITOS
# ─────────────────────────────────────────────

class ItemTransferenciaSerializer(serializers.ModelSerializer):
    articulo_codigo = serializers.CharField(source='articulo.cod_articulo', read_only=True)
    articulo_descripcion = serializers.CharField(source='articulo.descripcion', read_only=True)

    class Meta:
        model = ItemTransferencia
        fields = [
            'id', 'articulo', 'articulo_codigo', 'articulo_descripcion', 'cantidad',
        ]


class TransferenciaSerializer(serializers.ModelSerializer):
    items = ItemTransferenciaSerializer(many=True)
    origen_nombre = serializers.CharField(source='origen.nombre', read_only=True)
    destino_nombre = serializers.CharField(source='destino.nombre', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    created_by_nombre = serializers.SerializerMethodField()

    class Meta:
        model = TransferenciaInterna
        fields = [
            'id', 'fecha',
            'origen', 'origen_nombre',
            'destino', 'destino_nombre',
            'estado', 'estado_display',
            'observaciones',
            'movimiento_salida_aplicado', 'movimiento_entrada_aplicado',
            'created_by', 'created_by_nombre',
            'items',
        ]
        read_only_fields = [
            'estado', 'movimiento_salida_aplicado',
            'movimiento_entrada_aplicado', 'created_by',
        ]

    def get_created_by_nombre(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None

    def validate(self, data):
        origen = data.get('origen')
        destino = data.get('destino')
        if origen and destino and origen == destino:
            raise serializers.ValidationError(
                "El depósito de origen y destino no pueden ser el mismo."
            )
        return data

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        transferencia = TransferenciaInterna.objects.create(**validated_data)
        for item_data in items_data:
            ItemTransferencia.objects.create(transferencia=transferencia, **item_data)
        return transferencia


class TransferenciaListSerializer(serializers.ModelSerializer):
    """Serializer liviano para la lista de transferencias."""
    origen_nombre = serializers.CharField(source='origen.nombre', read_only=True)
    destino_nombre = serializers.CharField(source='destino.nombre', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    total_items = serializers.SerializerMethodField()

    class Meta:
        model = TransferenciaInterna
        fields = [
            'id', 'fecha', 'origen_nombre', 'destino_nombre',
            'estado', 'estado_display', 'total_items', 'observaciones',
        ]

    def get_total_items(self, obj):
        return obj.items.count()


# ─────────────────────────────────────────────
#  LEDGER (HISTORIAL INMUTABLE — solo lectura)
# ─────────────────────────────────────────────

class LedgerSerializer(serializers.ModelSerializer):
    articulo_codigo = serializers.CharField(source='articulo.cod_articulo', read_only=True)
    articulo_descripcion = serializers.CharField(source='articulo.descripcion', read_only=True)
    deposito_nombre = serializers.CharField(source='deposito.nombre', read_only=True)
    tipo_nombre = serializers.CharField(source='tipo_stock.nombre', read_only=True)
    tipo_codigo = serializers.CharField(source='tipo_stock.codigo', read_only=True)
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = MovimientoStockLedger
        fields = [
            'id', 'fecha_registro', 'fecha_movimiento',
            'articulo', 'articulo_codigo', 'articulo_descripcion',
            'deposito', 'deposito_nombre',
            'tipo_codigo', 'tipo_nombre',
            'cantidad',
            'origen_sistema', 'origen_referencia',
            'observaciones', 'usuario_nombre',
        ]

    def get_usuario_nombre(self, obj):
        if obj.usuario:
            return obj.usuario.get_full_name() or obj.usuario.username
        return None


# ─────────────────────────────────────────────
#  COMPATIBILIDAD HACIA ATRÁS
#  (usado por el POS y ventas actualmente)
# ─────────────────────────────────────────────

class ArticuloSerializer(ArticuloDetailSerializer):
    """
    Alias de compatibilidad. Las vistas existentes (POS, ventas) que importan
    ArticuloSerializer siguen funcionando sin cambios.
    """
    pass


class ArticuloCreateUpdateSerializer(ArticuloWriteSerializer):
    """
    Alias de compatibilidad. Si alguna vista importa este nombre, sigue funcionando.
    """
    pass