# en inventario/serializers.py (VERSIÓN FINAL CON ESCRITURA)

from rest_framework import serializers
from .models import Articulo, Marca, Rubro
from parametros.models import Impuesto, Moneda

class MarcaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marca
        fields = '__all__'

class RubroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rubro
        fields = '__all__'

# --- NUEVO: SERIALIZER DE ESCRITURA PARA ARTICULO ---
class ArticuloCreateUpdateSerializer(serializers.ModelSerializer):
    # Para la escritura, le decimos a DRF que espere los IDs de las relaciones
    marca = serializers.PrimaryKeyRelatedField(queryset=Marca.objects.all(), required=False, allow_null=True)
    rubro = serializers.PrimaryKeyRelatedField(queryset=Rubro.objects.all())
    impuesto = serializers.PrimaryKeyRelatedField(queryset=Impuesto.objects.all())
    moneda_costo = serializers.PrimaryKeyRelatedField(queryset=Moneda.objects.all())
    moneda_venta = serializers.PrimaryKeyRelatedField(queryset=Moneda.objects.all())

    class Meta:
        model = Articulo
        # Incluimos todos los campos que el usuario puede enviar desde el formulario
        fields = [
            'cod_articulo', 'descripcion', 'ean', 'marca', 'rubro', 'impuesto',
            'moneda_costo', 'precio_costo_original', 'utilidad',
            'moneda_venta', 'precio_venta_original',
            'administra_stock', 'esta_activo',
            # No incluimos campos de solo lectura como 'stock_total'
        ]


# --- SERIALIZER DE LECTURA (EL QUE YA TENÍAMOS, AJUSTADO) ---
class ArticuloSerializer(serializers.ModelSerializer):
    # Para Marca y Rubro, seguimos mostrando el objeto completo (útil para la lista)
    marca = MarcaSerializer(read_only=True)
    rubro = RubroSerializer(read_only=True)

    stock_total = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    precio_final_calculado = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Articulo
        # AÑADIMOS los campos que faltaban: impuesto y moneda_venta
        fields = [
            'cod_articulo', 'descripcion', 'ean', 'marca', 'rubro',
            'stock_total', 'precio_venta_base', 'precio_costo_base',
            'precio_costo_original', 'precio_venta_original', 'utilidad',
            'moneda_costo', 'moneda_venta', 'impuesto',
            'precio_final_calculado',
            'administra_stock', 'esta_activo'
        ]