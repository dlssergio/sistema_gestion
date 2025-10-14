from rest_framework import serializers
# <<< CAMBIO CLAVE: Eliminamos la importación de 'Impuesto' >>>
from .models import Moneda, TipoComprobante, ReglaImpuesto

class MonedaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Moneda
        # Exponemos los campos más útiles para la UI
        fields = ['id', 'nombre', 'simbolo', 'es_base', 'cotizacion']

class TipoComprobanteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoComprobante
        # Exponemos todos los campos del modelo
        fields = '__all__'

# <<< CAMBIO CLAVE: Eliminamos el ImpuestoSerializer por completo >>>
# En su lugar, creamos un serializer para el nuevo modelo ReglaImpuesto
# que usaremos en el futuro.

class ReglaImpuestoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReglaImpuesto
        fields = '__all__'