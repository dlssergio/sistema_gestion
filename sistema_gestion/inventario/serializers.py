from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField
from .models import Articulo, Marca, Rubro
# <<< CAMBIO CLAVE: Eliminamos la importación de 'Impuesto' >>>

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
    # <<< CAMBIO CLAVE: Eliminamos el campo 'impuesto' de este serializer >>>
    # impuesto = serializers.PrimaryKeyRelatedField(queryset=Impuesto.objects.all())

    class Meta:
        model = Articulo
        # <<< CAMBIO CLAVE: Eliminamos 'impuesto' de la lista de campos >>>
        fields = [
            'cod_articulo', 'descripcion', 'ean', 'marca', 'rubro',
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
        # <<< CAMBIO CLAVE: Eliminamos 'impuesto' de la lista de campos >>>
        fields = [
            'cod_articulo', 'descripcion', 'ean', 'marca', 'rubro',
            'stock_total', 'precio_costo', 'precio_venta', 'utilidad',
            'precio_final_calculado', 'administra_stock', 'esta_activo'
        ]

    def get_precio_costo(self, obj):
        costo = obj.precio_costo
        if costo and hasattr(obj, 'precio_costo_currency') and obj.precio_costo_currency:
            moneda_id = obj.precio_costo_currency.id
            return {'amount': f"{costo.amount:.2f}", 'currency': costo.currency.code, 'currency_id': moneda_id}
        return None

    def get_precio_final_calculado(self, obj):
        # <<< CAMBIO CLAVE: Deshabilitamos temporalmente este cálculo >>>
        # La nueva lógica de impuestos se implementará aquí en el futuro.
        return None