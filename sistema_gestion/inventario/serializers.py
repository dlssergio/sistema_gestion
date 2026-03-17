from decimal import Decimal

from rest_framework import serializers
from djmoney.contrib.django_rest_framework import MoneyField

from .models import Articulo, Marca, Rubro, CategoriaImpositiva
from parametros.models import Impuesto


class MarcaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marca
        fields = '__all__'


class RubroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rubro
        fields = '__all__'


class CategoriaImpositivaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaImpositiva
        fields = '__all__'


class ImpuestoResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Impuesto
        fields = ['id', 'nombre', 'tasa', 'es_porcentaje', 'aplica_a']


class ArticuloCreateUpdateSerializer(serializers.ModelSerializer):
    marca = serializers.PrimaryKeyRelatedField(queryset=Marca.objects.all(), required=False, allow_null=True)
    rubro = serializers.PrimaryKeyRelatedField(queryset=Rubro.objects.all())

    class Meta:
        model = Articulo
        fields = [
            'cod_articulo',
            'descripcion',
            'ean',
            'marca',
            'rubro',
            'precio_costo',
            'precio_venta',
            'administra_stock',
            'esta_activo',
        ]


class ArticuloSerializer(serializers.ModelSerializer):
    marca = MarcaSerializer(read_only=True)
    rubro = RubroSerializer(read_only=True)

    id = serializers.ReadOnlyField(source='pk')

    precio_costo = serializers.SerializerMethodField()
    precio_venta = MoneyField(max_digits=12, decimal_places=2, read_only=True)
    precio_final_calculado = serializers.SerializerMethodField()

    stock_total = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    utilidad = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)

    impuestos = ImpuestoResumenSerializer(many=True, read_only=True)
    iva_rate = serializers.SerializerMethodField()

    class Meta:
        model = Articulo
        fields = [
            'id',
            'cod_articulo',
            'descripcion',
            'ean',
            'marca',
            'rubro',
            'foto',
            'ubicacion',
            'permite_stock_negativo',
            'stock_total',
            'precio_costo',
            'precio_venta',
            'utilidad',
            'impuestos',
            'iva_rate',
            'precio_final_calculado',
            'administra_stock',
            'esta_activo',
        ]

    def get_precio_costo(self, obj):
        costo = obj.precio_costo
        if costo and hasattr(obj, 'precio_costo_currency') and obj.precio_costo_currency:
            moneda_id = obj.precio_costo_currency.id
            return {
                'amount': f"{costo.amount:.2f}",
                'currency': costo.currency.code,
                'currency_id': moneda_id
            }
        return None

    def get_iva_rate(self, obj):
        """
        Devuelve la tasa de IVA principal del artículo para el POS.
        Busca dentro de los impuestos asociados uno cuyo nombre contenga 'IVA'.

        Ejemplos:
        - IVA 21%   -> 21
        - IVA 10.5% -> 10.5
        """
        impuestos = obj.impuestos.all()

        iva = None
        for imp in impuestos:
            if 'IVA' in (imp.nombre or '').upper():
                iva = imp
                break

        if iva:
            try:
                return float(Decimal(str(iva.tasa)))
            except Exception:
                return 21.0

        return 21.0

    def get_precio_final_calculado(self, obj):
        """
        Cálculo simple de precio final con impuestos.
        Se deja informativo para APIs/consultas.
        """
        try:
            precio = Decimal(str(obj.precio_venta_monto or 0))
            total_impuestos = Decimal('0.00')

            for imp in obj.impuestos.all():
                if imp.aplica_a not in ('venta', 'ambos'):
                    continue

                if imp.es_porcentaje:
                    total_impuestos += precio * (Decimal(str(imp.tasa)) / Decimal('100'))
                else:
                    total_impuestos += Decimal(str(imp.tasa))

            return f"{(precio + total_impuestos).quantize(Decimal('0.01'))}"
        except Exception:
            return None