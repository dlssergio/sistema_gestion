# en entidades/serializers.py (CORREGIDO OTRA VEZ)

from rest_framework import serializers
from .models import Entidad, SituacionIVA
from ventas.models import Cliente
from compras.models import Proveedor


class SituacionIVASerializer(serializers.ModelSerializer):
    class Meta:
        model = SituacionIVA
        fields = ['id', 'nombre']

class EntidadSerializer(serializers.ModelSerializer):
    situacion_iva = SituacionIVASerializer(read_only=True)

    class Meta:
        model = Entidad
        fields = [
            'id',
            'razon_social',
            'cuit',
            'situacion_iva'
        ]


class ClienteSerializer(serializers.ModelSerializer):
    entidad = EntidadSerializer(read_only=True)
    id = serializers.ReadOnlyField(source='pk')

    # saldo de cuenta corriente — calculado como suma de saldos pendientes
    saldo = serializers.SerializerMethodField()

    def get_saldo(self, obj):
        """
        Suma de saldo_pendiente de comprobantes CONFIRMADOS del cliente.
        Devuelve float (no Decimal) para que el frontend lo reciba sin problemas.
        """
        try:
            from django.db.models import Sum
            from ventas.models import ComprobanteVenta
            result = ComprobanteVenta.objects.filter(
                cliente=obj,
                estado=ComprobanteVenta.Estado.CONFIRMADO,
                condicion_venta=ComprobanteVenta.CondicionVenta.CTA_CTE,
            ).aggregate(total=Sum('saldo_pendiente'))
            return float(result['total'] or 0)
        except Exception:
            return 0.0

    class Meta:
        model = Cliente
        fields = [
            'id',
            'entidad',
            'permite_cta_cte',
            'codigo_cliente',
            # Enterprise fields:
            'limite_credito',
            'descuento_base',
            'dias_vencimiento',
            'contacto_email',
            'saldo',  # SerializerMethodField — calculado
        ]

class ProveedorSerializer(serializers.ModelSerializer):
    entidad = EntidadSerializer(read_only=True)
    id = serializers.ReadOnlyField(source='pk')

    class Meta:
        model = Proveedor
        fields = [
            'id',
            'entidad',
            'codigo_proveedor',
            'nombre_fantasia'
        ]