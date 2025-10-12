# en inventario/serializers.py (VERSIÓN FINAL CON ID DE MONEDA EN API)

from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField
from .models import Articulo, Marca, Rubro
from parametros.models import Impuesto

class MarcaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marca
        fields = '__all__'

class RubroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rubro
        fields = '__all__'

class ArticuloCreateUpdateSerializer(serializers.ModelSerializer):
    marca = serializers.PrimaryKeyRelatedField(queryset=Marca.objects.all(), required=False, allow_null=True)
    rubro = serializers.PrimaryKeyRelatedField(queryset=Rubro.objects.all())
    impuesto = serializers.PrimaryKeyRelatedField(queryset=Impuesto.objects.all())

    class Meta:
        model = Articulo
        fields = [
            'cod_articulo', 'descripcion', 'ean', 'marca', 'rubro', 'impuesto',
            'precio_costo', 'precio_venta',
            'administra_stock', 'esta_activo',
        ]

class ArticuloSerializer(serializers.ModelSerializer):
    marca = MarcaSerializer(read_only=True)
    rubro = RubroSerializer(read_only=True)

    precio_costo = serializers.SerializerMethodField()
    precio_venta = MoneyField(max_digits=12, decimal_places=2, read_only=True)
    precio_final_calculado = serializers.SerializerMethodField()
    stock_total = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    utilidad = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)

    class Meta:
        model = Articulo
        fields = [
            'cod_articulo', 'descripcion', 'ean', 'marca', 'rubro',
            'stock_total', 'precio_costo', 'precio_venta', 'utilidad',
            'impuesto', 'precio_final_calculado', 'administra_stock', 'esta_activo'
        ]

    # <<< CAMBIO CLAVE: Ahora incluimos el ID de la moneda en la respuesta de la API >>>
    def get_precio_costo(self, obj):
        costo = obj.precio_costo
        if costo:
            # Buscamos el ID de la moneda a partir de su código
            moneda_id = obj.precio_costo_currency.id
            return {'amount': f"{costo.amount:.2f}", 'currency': costo.currency.code, 'currency_id': moneda_id}
        return None

    def get_precio_final_calculado(self, obj):
        precio = obj.precio_final_calculado
        if precio:
            return {'amount': f"{precio.amount:.2f}", 'currency': precio.currency.code}
        return None