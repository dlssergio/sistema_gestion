# sistema_gestion/compras/services.py (VERSIÓN CORREGIDA - SIN IMPORTACIÓN CIRCULAR)

from decimal import Decimal
from djmoney.money import Money
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Q
from django.db import transaction
from django.utils import timezone

# Modelos Externos (Estos no causan ciclo, se quedan arriba)
from inventario.models import ConversionUnidadMedida, Articulo
from inventario.services import StockManager


# NOTA: Los modelos locales (.models) se importan DENTRO de los métodos
# para evitar Circular Import con compras/models.py


class PriceListService:
    """
    Servicio encargado EXCLUSIVAMENTE de seleccionar la lista de precios correcta.
    Separa la lógica de selección (Cuál lista) de la lógica de cálculo (Cuánto cuesta).
    """

    @staticmethod
    def get_active_price_item(proveedor, articulo, cantidad=Decimal(1), fecha=None):
        """
        Busca el ítem de precio vigente para un artículo y proveedor.
        Prioridad:
        1. Lista Principal Vigente
        2. Otras Listas Activas Vigentes (la más reciente)
        """
        # Importación diferida para romper el ciclo
        from .models import ListaPreciosProveedor, ItemListaPreciosProveedor

        if fecha is None:
            fecha = timezone.now().date()

        # 1. Buscar en la lista principal activa y vigente
        lista_principal = ListaPreciosProveedor.objects.filter(
            proveedor=proveedor, es_principal=True, es_activa=True,
            vigente_desde__lte=fecha
        ).filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=fecha)).first()

        if lista_principal:
            item = ItemListaPreciosProveedor.objects.filter(
                lista_precios=lista_principal, articulo=articulo, cantidad_minima__lte=cantidad
            ).order_by('-cantidad_minima').first()
            if item:
                return item

        # 2. Si no se encontró, buscar en CUALQUIER otra lista activa y vigente
        otras_listas = ListaPreciosProveedor.objects.filter(
            proveedor=proveedor, es_principal=False, es_activa=True,
            vigente_desde__lte=fecha
        ).filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=fecha)).order_by('-vigente_desde')

        for lista in otras_listas:
            item = ItemListaPreciosProveedor.objects.filter(
                lista_precios=lista, articulo=articulo, cantidad_minima__lte=cantidad
            ).order_by('-cantidad_minima').first()
            if item:
                return item

        return None


class CostCalculatorService:
    """
    Servicio de Cálculo Financiero.
    Mantiene la lógica existente para no romper integraciones previas.
    """

    @staticmethod
    def apply_cascading_discounts(base_amount: Decimal, discount_list: list) -> Decimal:
        final_amount = base_amount
        for percentage in discount_list:
            try:
                percentage_decimal = Decimal(str(percentage))
                factor = Decimal(1) + (percentage_decimal / Decimal(100))
                final_amount *= factor
            except (TypeError, ValueError):
                continue
        return final_amount.quantize(Decimal('0.0001'))

    @classmethod
    def calculate_effective_cost(cls, item_precio: 'ItemListaPreciosProveedor') -> Money:
        # Nota: item_precio se pasa como argumento, no necesitamos importar la clase para usar sus atributos
        costo_base = item_precio.precio_lista.amount
        currency = item_precio.precio_lista.currency

        if item_precio.bonificacion_porcentaje > 0:
            bonificacion_factor = (Decimal(100) - item_precio.bonificacion_porcentaje) / Decimal(100)
            costo_base *= bonificacion_factor

        if item_precio.descuentos_adicionales:
            costo_base = cls.apply_cascading_discounts(costo_base, item_precio.descuentos_adicionales)

        if item_precio.descuentos_financieros:
            costo_base = cls.apply_cascading_discounts(costo_base, item_precio.descuentos_financieros)

        try:
            conversion = ConversionUnidadMedida.objects.get(
                articulo=item_precio.articulo,
                unidad_externa=item_precio.unidad_medida_compra
            )
            if conversion.factor_conversion > 0:
                costo_unitario_stock = costo_base / conversion.factor_conversion
            else:
                costo_unitario_stock = costo_base
        except ObjectDoesNotExist:
            costo_unitario_stock = costo_base

        return Money(costo_unitario_stock, currency)

    @classmethod
    def get_latest_price(cls, proveedor_pk: int, articulo_pk: str, cantidad: Decimal = Decimal(1)):
        """
        MÉTODO ACTUALIZADO (Fachada):
        Usa PriceListService para buscar el ítem correcto.
        """
        # Importación diferida
        from .models import Proveedor

        try:
            proveedor = Proveedor.objects.get(pk=proveedor_pk)
            articulo = Articulo.objects.get(pk=articulo_pk)

            # Delegamos la búsqueda al nuevo servicio especializado
            return PriceListService.get_active_price_item(proveedor, articulo, cantidad)

        except (Proveedor.DoesNotExist, Articulo.DoesNotExist):
            return None
        except Exception as e:
            print(f"Error en get_latest_price: {e}")
            return None


# =========================================================
# NUEVA LÓGICA DE STOCK PARA COMPRAS (ENTERPRISE)
# =========================================================

class ComprasStockService:
    """
    Gestor de Movimientos de Stock para el ciclo de Compras.
    Implementa el flujo: Orden de Compra (RCPT) -> Recepción (REAL).
    """

    @staticmethod
    @transaction.atomic
    def confirmar_orden_compra(comprobante: 'ComprobanteCompra'):
        """
        Al confirmar una OC, aumentamos el stock 'A Recibir' (RCPT).
        Esto permite a Planeamiento ver qué está por llegar.
        """
        if comprobante.stock_aplicado: return

        # Validamos que sea una OC o similar (Si NO mueve stock físico directo, es una OC/Preventa)
        if not comprobante.tipo_comprobante.afecta_stock_fisico:
            ref = f"OC #{comprobante.numero}"
            for item in comprobante.items.all():
                StockManager.registrar_movimiento(
                    articulo=item.articulo,
                    deposito=comprobante.deposito,
                    codigo_tipo='RCPT',  # Aumenta "A Recibir"
                    cantidad=item.cantidad,  # Positivo
                    origen_sistema='COMPRAS',
                    origen_referencia=ref,
                    usuario=None
                )
            # NOTA: Podrías necesitar un flag específico 'stock_previsto_aplicado' en el modelo
            # si quieres controlar idempotencia solo para la OC, separado del stock real.
            pass

    @staticmethod
    @transaction.atomic
    def procesar_recepcion_mercaderia(comprobante: 'ComprobanteCompra'):
        """
        Al recibir la mercadería (Remito/Factura de Compra):
        1. Aumenta Stock REAL (Físico).
        2. Disminuye Stock RCPT (Si venía de una OC previa).
        """
        # Importación diferida para actualizar el estado al final
        from .models import ComprobanteCompra

        if comprobante.stock_aplicado: return

        # Solo procesamos si el tipo de comprobante indica movimiento físico (Remito, Factura)
        if not comprobante.tipo_comprobante.afecta_stock_fisico: return

        ref = f"Recepción {comprobante.tipo_comprobante.nombre} #{comprobante.numero}"

        for item in comprobante.items.all():
            # 1. Ingreso Físico (REAL)
            StockManager.registrar_movimiento(
                articulo=item.articulo,
                deposito=comprobante.deposito,
                codigo_tipo='REAL',
                cantidad=item.cantidad,  # Positivo (Entrada)
                origen_sistema='COMPRAS',
                origen_referencia=ref,
                usuario=None
            )

            # 2. Cancelación de Expectativa (RCPT) - Si existe enlace con OC
            if comprobante.comprobante_origen:
                # Si viene de una OC, asumimos que esa OC generó RCPT. Lo restamos.
                StockManager.registrar_movimiento(
                    articulo=item.articulo,
                    deposito=comprobante.deposito,
                    codigo_tipo='RCPT',
                    cantidad=-item.cantidad,  # Negativo (Descargamos la expectativa)
                    origen_sistema='COMPRAS',
                    origen_referencia=f"Cierre OC por Recep. #{comprobante.numero}",
                    usuario=None,
                    permitir_stock_negativo=True  # Permitimos negativo por diferencias menores
                )

        # Bloqueamos para no duplicar
        comprobante.stock_aplicado = True
        ComprobanteCompra.objects.filter(pk=comprobante.pk).update(stock_aplicado=True)