# ventas/services.py (VERSIÓN FINAL Y ROBUSTA)

from django.db.models import Q
from django.utils import timezone
from decimal import Decimal
from collections import defaultdict


class TaxCalculatorService:
    @staticmethod
    def calcular_impuestos_comprobante(comprobante, tipo_operacion: str):
        """
        Calcula el desglose de impuestos para un comprobante, aplicando reglas de
        vigencia y categoría para una máxima robustez.
        """
        impuestos_agrupados = defaultdict(Decimal)
        today = timezone.now().date()

        for item in comprobante.items.all():
            subtotal_item = item.subtotal.amount if hasattr(item.subtotal, 'amount') else item.subtotal

            # Si no hay subtotal, no hay impuestos que calcular para este ítem.
            if not subtotal_item or subtotal_item <= 0:
                continue

            # <<< INICIO DE LA LÓGICA ROBUSTA >>>
            # Se construye una consulta que filtra los impuestos aplicables.
            impuestos_aplicables = item.articulo.impuestos.filter(
                # 1. Filtro por tipo de operación (venta, compra o ambos)
                Q(aplica_a=tipo_operacion) | Q(aplica_a='ambos'),

                # 2. Filtro por vigencia (debe estar activo hoy)
                vigente_desde__lte=today
            ).filter(
                Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=today)
            )
            # <<< FIN DE LA LÓGICA ROBUSTA >>>

            for impuesto in impuestos_aplicables:
                # Opcional, pero robusto: Si el artículo tiene una categoría, se podría
                # añadir una capa extra de validación aquí si el impuesto también la tiene.
                # Por ahora, la relación ManyToMany es suficiente.

                monto_impuesto = Decimal('0.00')
                if impuesto.es_porcentaje:
                    monto_impuesto = subtotal_item * (impuesto.tasa / Decimal(100))
                else:  # Es un monto fijo por unidad
                    # Multiplicamos el monto fijo por la cantidad de items
                    monto_impuesto = impuesto.tasa * item.cantidad

                impuestos_agrupados[impuesto.nombre] += monto_impuesto

        return {nombre: monto.quantize(Decimal('0.01')) for nombre, monto in impuestos_agrupados.items()}