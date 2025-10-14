from django.db.models import Q
from django.utils import timezone
from decimal import Decimal
from collections import defaultdict

from parametros.models import ReglaImpuesto


class TaxCalculatorService:
    @staticmethod
    def calcular_impuestos_comprobante(comprobante, tipo_operacion: str):
        """
        Recibe una instancia de un comprobante (venta o compra) y el tipo de operación,
        y devuelve un diccionario con el desglose de impuestos aplicados.
        tipo_operacion debe ser 'venta' o 'compra'.
        """
        if tipo_operacion not in ['venta', 'compra']:
            return {}  # Devolvemos un diccionario vacío si el tipo no es válido

        impuestos_agrupados = defaultdict(Decimal)
        today = timezone.now().date()

        for item in comprobante.items.all():
            reglas_aplicables = ReglaImpuesto.objects.filter(
                activo=True,
                aplica_a=tipo_operacion,  # <<< CAMBIO CLAVE: Ahora es dinámico
                valido_desde__lte=today
            ).filter(
                Q(valido_hasta__isnull=True) | Q(valido_hasta__gte=today)
            ).filter(
                Q(categorias_producto__isnull=True) | Q(categorias_producto=item.articulo.rubro)
            ).filter(
                Q(tipos_comprobante__isnull=True) | Q(tipos_comprobante=comprobante.tipo_comprobante)
            )

            for regla in reglas_aplicables:
                monto_impuesto = Decimal('0.00')
                if regla.tipo_impuesto == 'porcentaje':
                    # La base del cálculo es el subtotal del ítem
                    # Para compras, el subtotal es un objeto Money, accedemos a su monto
                    subtotal_item = item.subtotal.amount if hasattr(item.subtotal, 'amount') else item.subtotal
                    monto_impuesto = subtotal_item * (regla.tasa / Decimal(100))

                impuestos_agrupados[regla.nombre] += monto_impuesto

        return {nombre: monto.quantize(Decimal('0.01')) for nombre, monto in impuestos_agrupados.items()}