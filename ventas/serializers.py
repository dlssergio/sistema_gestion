# ventas/serializers.py (VERSIÓN FINAL CORREGIDA)

from decimal import Decimal
from django.db import transaction
from rest_framework import serializers

# --- MODELOS DE OTRAS APPS ---
from inventario.models import Articulo
from parametros.models import TipoComprobante

# --- SERIALIZERS DE OTRAS APPS ---
from inventario.serializers import ArticuloSerializer
from entidades.serializers import ClienteSerializer
from parametros.serializers import TipoComprobanteSerializer

# --- MODELOS DE ESTA APP ---
from .models import ComprobanteVenta, ComprobanteVentaItem, Cliente

# --- SERVICIOS (para recalcular totales en update) ---
from .services import TaxCalculatorService


def _to_decimal(v) -> Decimal:
    """
    Convierte Money/Decimal/number/string a Decimal.
    djmoney Money tiene atributo .amount.
    """
    if v is None:
        return Decimal("0")
    if hasattr(v, "amount"):
        try:
            return Decimal(str(v.amount))
        except Exception:
            return Decimal("0")
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


# --- SERIALIZERS DE ESCRITURA (CREATE/UPDATE) ---

class ComprobanteVentaItemCreateSerializer(serializers.ModelSerializer):
    articulo = serializers.SlugRelatedField(
        queryset=Articulo.objects.all(),
        slug_field='cod_articulo'
    )

    class Meta:
        model = ComprobanteVentaItem
        fields = ['articulo', 'cantidad', 'precio_unitario_original']


class ComprobanteVentaCreateSerializer(serializers.ModelSerializer):
    """
    Serializer de escritura.
    IMPORTANTE: soporta nested writes en UPDATE/PATCH implementando .update().
    """
    cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all())
    tipo_comprobante = serializers.PrimaryKeyRelatedField(queryset=TipoComprobante.objects.all())

    # ✅ En PATCH no siempre mandan items
    items = ComprobanteVentaItemCreateSerializer(many=True, required=False)

    class Meta:
        model = ComprobanteVenta
        fields = [
            'cliente',
            'tipo_comprobante',
            'fecha',
            'estado',
            'punto_venta',
            'numero',
            'items',
            'observaciones',
            'cliente_nombre_override',
            'cliente_cuit_override',
            'cliente_email_override',
        ]

    def update(self, instance, validated_data):
        """
        ✅ Soporta PATCH con nested items.
        Estrategia:
        - Actualiza campos simples.
        - Si vienen items: reemplaza TODOS los items del comprobante por los enviados.
        - Recalcula subtotal/impuestos/total y saldo_pendiente usando la regla del MODELO
          (respeta pagos si está confirmado).
        """
        items_data = validated_data.pop('items', None)

        with transaction.atomic():
            # 1) Update de campos simples
            for attr, value in validated_data.items():
                setattr(instance, attr, value)

            instance.save()

            # 2) Update de items (nested)
            if items_data is not None:
                instance.items.all().delete()

                subtotal_acumulado = Decimal("0")

                # Creamos items nuevos
                for item_data in items_data:
                    item_obj = ComprobanteVentaItem(
                        comprobante=instance,
                        **item_data
                    )
                    # ✅ dispara clean() del item (stock preventivo, etc.) cuando corresponda
                    item_obj.full_clean()
                    item_obj.save()

                    subtotal_acumulado += _to_decimal(getattr(item_obj, "subtotal", 0))

                # 3) Recalcular impuestos / total (con items ya guardados)
                desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(instance, 'venta')
                total_impuestos = sum((_to_decimal(v) for v in desglose_impuestos.values()), Decimal("0"))
                total_nuevo = subtotal_acumulado + total_impuestos

                # ✅ CLAVE: usar la regla del modelo para NO pisar pagos en CN
                instance.recalcular_totales_y_saldo(
                    nuevo_subtotal=subtotal_acumulado,
                    nuevos_impuestos=desglose_impuestos,
                    nuevo_total=total_nuevo,
                )
                instance.save()

        return instance


# --- SERIALIZERS DE LECTURA (READ) ---

class ComprobanteVentaItemSerializer(serializers.ModelSerializer):
    articulo = ArticuloSerializer(read_only=True)

    class Meta:
        model = ComprobanteVentaItem
        fields = ['articulo', 'cantidad', 'precio_unitario_original', 'subtotal']


class ComprobanteVentaSerializer(serializers.ModelSerializer):
    cliente = ClienteSerializer(read_only=True)
    tipo_comprobante = TipoComprobanteSerializer(read_only=True)
    items = ComprobanteVentaItemSerializer(many=True, read_only=True)

    class Meta:
        model = ComprobanteVenta
        fields = [
            'id',
            'numero_completo',
            'numero',
            'letra',
            'punto_venta',
            'cliente',
            'fecha',
            'estado',
            'condicion_venta',
            'subtotal',
            'total',
            'saldo_pendiente',
            'tipo_comprobante',
            'items',
            'observaciones',
            # AFIP
            'cae',
            'vto_cae',
            'afip_resultado',
            'afip_error',
            # Override cliente genérico C00000
            'cliente_nombre_override',
            'cliente_cuit_override',
            'cliente_email_override',
        ]