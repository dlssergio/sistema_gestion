from rest_framework import serializers


class ClienteDashboardUltimaVentaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    fecha = serializers.CharField(allow_null=True)
    numero = serializers.CharField()
    tipo = serializers.CharField()
    total = serializers.FloatField()
    saldo = serializers.FloatField()
    estado = serializers.CharField()


class ClienteDashboardKpisSerializer(serializers.Serializer):
    cantidad_comprobantes_90d = serializers.IntegerField()
    total_vendido_30d = serializers.FloatField()
    ticket_promedio_90d = serializers.FloatField()
    dias_desde_ultima_compra = serializers.IntegerField(allow_null=True)


class ClienteDashboardAgingSerializer(serializers.Serializer):
    bucket_0_30 = serializers.FloatField()
    bucket_31_60 = serializers.FloatField()
    bucket_61_90 = serializers.FloatField()
    bucket_90_plus = serializers.FloatField()


class ClienteDashboardComprobanteSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    fecha = serializers.CharField(allow_null=True)
    numero = serializers.CharField()
    tipo = serializers.CharField()
    condicion_venta = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    total = serializers.FloatField()
    saldo = serializers.FloatField()
    estado = serializers.CharField()
    estado_pago = serializers.CharField()


class ClienteDashboardMovimientoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    fecha = serializers.CharField(allow_null=True)
    tipo = serializers.CharField()
    numero = serializers.CharField()
    debe = serializers.FloatField()
    haber = serializers.FloatField()
    saldo = serializers.FloatField()


class ClienteDashboardDebugClasificacionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    numero = serializers.CharField()
    condicion_original = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    clasificacion_dashboard = serializers.CharField()
    saldo = serializers.FloatField()


class ClienteDashboardSerializer(serializers.Serializer):
    cliente_id = serializers.IntegerField()
    saldo_total = serializers.FloatField()
    deuda_vencida = serializers.FloatField()
    deuda_no_vencida = serializers.FloatField()
    deuda_cta_cte = serializers.FloatField()
    deuda_contado = serializers.FloatField()
    limite_credito = serializers.FloatField()
    credito_disponible = serializers.FloatField()
    comprobantes_impagos = serializers.IntegerField()
    riesgo = serializers.CharField()
    aging = ClienteDashboardAgingSerializer()
    ultima_venta = ClienteDashboardUltimaVentaSerializer(allow_null=True)
    kpis = ClienteDashboardKpisSerializer()
    ultimos_comprobantes = ClienteDashboardComprobanteSerializer(many=True)
    movimientos_cta_cte = ClienteDashboardMovimientoSerializer(many=True)
    debug_clasificacion = ClienteDashboardDebugClasificacionSerializer(many=True, required=False)