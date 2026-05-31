from rest_framework import serializers
from .models import Entidad, SituacionIVA
from ventas.models import Cliente
from compras.models import Proveedor


class SituacionIVASerializer(serializers.ModelSerializer):
    class Meta:
        model = SituacionIVA
        fields = ['id', 'codigo', 'nombre', 'codigo_afip', 'mostrar_precio_con_iva']


class EntidadSerializer(serializers.ModelSerializer):
    situacion_iva = SituacionIVASerializer(read_only=True)

    class Meta:
        model = Entidad
        fields = [
            'id',
            'razon_social',
            'cuit',
            'dni',
            'sexo',
            'email',
            'situacion_iva',
        ]


class ClienteSerializer(serializers.ModelSerializer):
    entidad = EntidadSerializer(read_only=True)
    id = serializers.ReadOnlyField(source='pk')
    saldo = serializers.SerializerMethodField()

    def get_saldo(self, obj):
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
            'nombre_fantasia',
            'categoria',
            'zona',
            'limite_credito',
            'descuento_base',
            'dias_vencimiento',
            'contacto_nombre',
            'contacto_email',
            'contacto_telefono',
            'esta_activo',
            'observaciones',
            'saldo',
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
            'nombre_fantasia',
        ]