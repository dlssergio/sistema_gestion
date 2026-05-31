# finanzas/serializers.py
from rest_framework import serializers
from .models import TipoValor, CuentaFondo, Banco, PlanCuota, PlanTarjeta, Tarjeta, Cheque, MovimientoFondo


class TipoValorSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoValor
        fields = ['id', 'nombre', 'requiere_banco', 'es_cheque', 'es_tarjeta', 'es_retencion']


class BancoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banco
        fields = ['id', 'nombre', 'codigo_bcra']


class CuentaFondoSerializer(serializers.ModelSerializer):
    banco_nombre  = serializers.CharField(source='banco.nombre', read_only=True, default='')
    tipo_display  = serializers.CharField(source='get_tipo_display', read_only=True)
    moneda_simbolo = serializers.CharField(source='moneda.simbolo', read_only=True, default='ARS')

    class Meta:
        model = CuentaFondo
        fields = [
            'id', 'nombre', 'tipo', 'tipo_display',
            'saldo_monto', 'moneda', 'moneda_simbolo',
            'banco', 'banco_nombre', 'cbu', 'alias', 'activa',
        ]


class PlanCuotaSerializer(serializers.ModelSerializer):
    tarjeta    = serializers.CharField(source='plan.tarjeta.nombre', read_only=True)
    plan_nombre = serializers.CharField(source='plan.nombre', read_only=True)

    class Meta:
        model = PlanCuota
        fields = ['id', 'cuotas', 'coeficiente', 'tna', 'plan', 'plan_nombre', 'tarjeta']


class ChequeSerializer(serializers.ModelSerializer):
    banco_nombre          = serializers.CharField(source='banco.nombre', read_only=True)
    moneda_simbolo        = serializers.CharField(source='moneda.simbolo', read_only=True, default='ARS')
    estado_display        = serializers.CharField(source='get_estado_display', read_only=True)
    origen_display        = serializers.CharField(source='get_origen_display', read_only=True)
    tipo_cheque_display   = serializers.CharField(source='get_tipo_cheque_display', read_only=True)
    dias_para_vencer      = serializers.SerializerMethodField()

    class Meta:
        model = Cheque
        fields = [
            'id', 'numero', 'banco', 'banco_nombre',
            'origen', 'origen_display',
            'tipo_cheque', 'tipo_cheque_display',
            'estado', 'estado_display',
            'fecha_emision', 'fecha_pago', 'dias_para_vencer',
            'monto', 'moneda', 'moneda_simbolo',
            'cuit_librador', 'nombre_librador',
            'referencia_bancaria', 'observaciones',
        ]

    def get_dias_para_vencer(self, obj):
        from django.utils import timezone
        return (obj.fecha_pago - timezone.now().date()).days


class MovimientoFondoSerializer(serializers.ModelSerializer):
    cuenta_nombre        = serializers.CharField(source='cuenta.nombre', read_only=True)
    tipo_valor_nombre    = serializers.CharField(source='tipo_valor.nombre', read_only=True, default='')
    tipo_movimiento_display = serializers.CharField(source='get_tipo_movimiento_display', read_only=True)
    usuario_nombre       = serializers.SerializerMethodField()

    class Meta:
        model = MovimientoFondo
        fields = [
            'id', 'fecha',
            'cuenta', 'cuenta_nombre',
            'tipo_movimiento', 'tipo_movimiento_display',
            'tipo_valor', 'tipo_valor_nombre',
            'monto_ingreso', 'monto_egreso',
            'concepto', 'conciliado', 'usuario_nombre',
        ]

    def get_usuario_nombre(self, obj):
        if obj.usuario:
            return obj.usuario.get_full_name() or obj.usuario.username
        return ''


class MovimientoFondoWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoFondo
        fields = ['cuenta', 'tipo_movimiento', 'tipo_valor',
                  'monto_ingreso', 'monto_egreso', 'concepto']