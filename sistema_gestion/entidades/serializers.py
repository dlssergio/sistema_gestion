# en entidades/serializers.py (CORREGIDO OTRA VEZ)

from rest_framework import serializers
# Corregimos las importaciones para que cada modelo venga de su app correcta.
# 'Entidad' y 'SituacionIVA' vienen del 'models.py' de esta misma app.
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

    class Meta:
        model = Cliente
        fields = ['entidad']

class ProveedorSerializer(serializers.ModelSerializer):
    entidad = EntidadSerializer(read_only=True)

    class Meta:
        model = Proveedor
        fields = [
            'entidad',
            'codigo_proveedor',
            'nombre_fantasia'
        ]