# finanzas/serializers.py
from rest_framework import serializers
from .models import TipoValor, CuentaFondo, Banco, PlanCuota, PlanTarjeta, Tarjeta

class TipoValorSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoValor
        fields = ['id', 'nombre', 'requiere_banco', 'es_cheque', 'es_tarjeta', 'es_retencion']

class BancoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banco
        fields = ['id', 'nombre', 'codigo_bcra']

class CuentaFondoSerializer(serializers.ModelSerializer):
    banco_nombre = serializers.CharField(source='banco.nombre', read_only=True)

    class Meta:
        model = CuentaFondo
        fields = ['id', 'nombre', 'tipo', 'saldo_monto', 'moneda', 'banco', 'banco_nombre', 'activa']

class PlanCuotaSerializer(serializers.ModelSerializer):
    tarjeta = serializers.CharField(source='plan.tarjeta.nombre', read_only=True)
    plan_nombre = serializers.CharField(source='plan.nombre', read_only=True)

    class Meta:
        model = PlanCuota
        fields = ['id', 'cuotas', 'coeficiente', 'tna', 'plan', 'plan_nombre', 'tarjeta']