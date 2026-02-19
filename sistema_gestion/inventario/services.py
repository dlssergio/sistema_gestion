# inventario/services.py

import logging
from django.db import transaction
from django.db.models import F, Sum
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.utils import timezone

# Modelos
from .models import MovimientoStockLedger, BalanceStock, StockArticulo, TipoStock, Deposito, HistoricoMovimientos

logger = logging.getLogger(__name__)


class StockManager:
    """
    GATEKEEPER DEL STOCK (CORE).
    ----------------------------------------------------------------------
    Esta clase es la ÚNICA autorizada para escribir en:
    1. MovimientoStockLedger (Append-only)
    2. BalanceStock (Vista materializada)
    3. StockArticulo (Modelo Legacy)

    Cualquier escritura directa a estos modelos fuera de esta clase
    provocará desincronización de datos.
    ----------------------------------------------------------------------
    """

    @staticmethod
    @transaction.atomic
    def registrar_movimiento(articulo, deposito, codigo_tipo, cantidad,
                             origen_sistema, origen_referencia, usuario=None,
                             observaciones="", permitir_stock_negativo=None):
        """
        Registra un cambio de stock atómico con validación jerárquica de negativos.

        Args:
            permitir_stock_negativo (bool|None):
                - True: Fuerza la operación (Override).
                - False: Fuerza la validación.
                - None (Default): Aplica reglas de negocio (Depósito > Artículo).
        """
        cantidad = Decimal(str(cantidad))
        if cantidad == Decimal(0): return Decimal(0)

        # 1. Resolver Tipo (Validación de Existencia)
        try:
            tipo = TipoStock.objects.get(codigo=codigo_tipo)
        except TipoStock.DoesNotExist:
            raise ValidationError(f"Error Crítico: El Tipo de Stock '{codigo_tipo}' no existe en la configuración.")

        # ==============================================================================
        # PARTE A: VALIDACIÓN AVANZADA DE STOCK NEGATIVO (JERARQUÍA)
        # ==============================================================================
        if cantidad < Decimal(0):
            validar_saldo = False

            # Nivel 1: Override Explícito
            if permitir_stock_negativo is not None:
                validar_saldo = not permitir_stock_negativo

            else:
                # Nivel 2: Regla por Depósito
                if not deposito.permite_stock_negativo:
                    validar_saldo = True

                # Nivel 3: Regla por Artículo
                elif not articulo.permite_stock_negativo:
                    validar_saldo = True

                # Default del sistema: Si nadie lo permite explícitamente, bloqueamos.
                else:
                    validar_saldo = False  # Ambos flags estaban en True

            if validar_saldo:
                balance_actual = BalanceStock.objects.filter(
                    articulo=articulo, deposito=deposito, tipo_stock=tipo
                ).first()

                saldo = balance_actual.cantidad if balance_actual else Decimal(0)

                if saldo + cantidad < Decimal(0):
                    raise ValidationError(
                        f"Stock insuficiente en {deposito.nombre}. "
                        f"Artículo: {articulo.cod_articulo} ({tipo.nombre}). "
                        f"Saldo Actual: {saldo}. Solicitado: {abs(cantidad)}. "
                        f"(Bloqueado por regla de stock negativo)."
                    )

        # ==============================================================================
        # ESCRITURA
        # ==============================================================================

        # 3. Insertar en Ledger (Inmutable)
        MovimientoStockLedger.objects.create(
            articulo=articulo,
            deposito=deposito,
            tipo_stock=tipo,
            cantidad=cantidad,
            origen_sistema=origen_sistema,
            origen_referencia=origen_referencia,
            usuario=usuario,
            observaciones=observaciones,
            fecha_movimiento=timezone.now()
        )

        # 4. Actualizar Balance Materializado (Fuente para consultas)
        # Usamos update_or_create y luego update() con F() para garantizar atomicidad DB.
        balance, _ = BalanceStock.objects.get_or_create(
            articulo=articulo, deposito=deposito, tipo_stock=tipo,
            defaults={'cantidad': Decimal(0)}
        )
        BalanceStock.objects.filter(pk=balance.pk).update(cantidad=F('cantidad') + cantidad)

        # 5. Sincronización Legacy (StockArticulo)
        # El modelo legacy solo entiende de 'REAL' y 'RSRV' (Comprometido).
        stock_legacy, _ = StockArticulo.objects.select_for_update().get_or_create(
            articulo=articulo, deposito=deposito,
            defaults={'cantidad_real': Decimal(0), 'cantidad_comprometida': Decimal(0)}
        )

        if codigo_tipo == 'REAL':
            StockArticulo.objects.filter(pk=stock_legacy.pk).update(cantidad_real=F('cantidad_real') + cantidad)
        elif codigo_tipo == 'RSRV':
            StockArticulo.objects.filter(pk=stock_legacy.pk).update(
                cantidad_comprometida=F('cantidad_comprometida') + cantidad)

        # 6. Compatibilidad Auditoría Vieja (Robustez Operativa)
        try:
            operacion_legacy = 'SUMAR' if cantidad > Decimal(0) else 'RESTAR'
            if codigo_tipo in ['REAL', 'RSRV']:
                tipo_legacy = 'REAL' if codigo_tipo == 'REAL' else 'COMPROMETIDO'
                # Recargamos para obtener valor actualizado exacto para el log
                stock_legacy.refresh_from_db()
                saldo_legacy = stock_legacy.cantidad_real if codigo_tipo == 'REAL' else stock_legacy.cantidad_comprometida

                HistoricoMovimientos.objects.create(
                    articulo=articulo, deposito=deposito, cantidad=abs(cantidad),
                    tipo_stock=tipo_legacy, operacion=operacion_legacy,
                    saldo_post_movimiento=saldo_legacy, referencia=origen_referencia, usuario=usuario
                )
        except Exception as e:
            # No rompemos la transacción si falla el log legacy, pero lo registramos
            logger.warning(f"Error escribiendo HistoricoMovimientos (Legacy): {e}")

        return True

    @staticmethod
    def validar_disponibilidad(articulo, deposito, cantidad_requerida):
        """
        Verifica disponibilidad usando la nueva lógica de balances.
        """
        vendible = BalanceStock.objects.filter(
            articulo=articulo, deposito=deposito, tipo_stock__es_vendible=True
        ).aggregate(total=Sum('cantidad'))['total'] or Decimal(0)

        reservado = BalanceStock.objects.filter(
            articulo=articulo, deposito=deposito, tipo_stock__es_reservado=True
        ).aggregate(total=Sum('cantidad'))['total'] or Decimal(0)

        disponible = vendible - reservado
        return disponible >= Decimal(str(cantidad_requerida))

    # --- NUEVO MÉTODO PARA VALIDACIÓN EN FORMULARIOS ---
    @staticmethod
    def obtener_saldo_actual(articulo, deposito, codigo_tipo_stock):
        """
        Consulta rápida de saldo para validaciones en formularios (read-only).
        Devuelve Decimal.
        """
        try:
            balance = BalanceStock.objects.filter(
                articulo=articulo,
                deposito=deposito,
                tipo_stock__codigo=codigo_tipo_stock
            ).first()
            return balance.cantidad if balance else Decimal(0)
        except Exception:
            return Decimal(0)


# --- WRAPPER DE COMPATIBILIDAD ---
class StockService:
    """
    CLASE DEPRECADA / WRAPPER.
    Mantiene la firma del servicio anterior para no romper imports antiguos.
    Delega todo al nuevo StockManager.
    """

    @classmethod
    def ajustar_stock(cls, articulo, deposito, cantidad, operacion, modo='REAL', referencia='', usuario=None):
        codigo_tipo = 'REAL'
        if modo == 'COMPROMETIDO':
            codigo_tipo = 'RSRV'

        # Convertir operacion/cantidad a signo matemático
        cantidad_dec = Decimal(str(cantidad))
        cantidad_final = cantidad_dec if operacion == 'SUMAR' else -cantidad_dec

        StockManager.registrar_movimiento(
            articulo=articulo,
            deposito=deposito,
            codigo_tipo=codigo_tipo,
            cantidad=cantidad_final,
            origen_sistema='LEGACY_WRAPPER',
            origen_referencia=referencia,
            usuario=usuario,
            permitir_stock_negativo=True
        )


# Importamos el modelo dentro de los métodos o usamos string para evitar ciclo si fuera necesario,
# pero como esto está en services.py y el modelo en models.py, necesitamos importar models aquí.
# Asegúrate de importar TransferenciaInterna al principio del archivo o dentro de la clase.

class TransferenciaService:
    """
    Maneja el ciclo de vida de una transferencia:
    1. Despacho (Origen -> Tránsito)
    2. Recepción (Tránsito -> Destino Real)
    """

    @staticmethod
    @transaction.atomic
    def despachar_transferencia(transferencia):
        """
        Paso 1: Sacar mercadería del Origen y ponerla en 'TRNS' del Destino.
        """
        # Validaciones
        if transferencia.estado != 'BR':
            raise ValidationError("Solo se pueden despachar transferencias en estado Borrador.")
        if transferencia.movimiento_salida_aplicado:
            return

        ref = f"Envío TRF #{transferencia.pk} a {transferencia.destino}"

        for item in transferencia.items.all():
            # 1. Restar Físico en Origen (Puede fallar si no hay stock)
            # Nota: Usamos permitir_stock_negativo=None para que aplique las reglas del depósito.
            StockManager.registrar_movimiento(
                articulo=item.articulo,
                deposito=transferencia.origen,
                codigo_tipo='REAL',
                cantidad=-item.cantidad, # Resta
                origen_sistema='TRANSFERENCIA',
                origen_referencia=ref,
                usuario=transferencia.creado_por,
                permitir_stock_negativo=None
            )

            # 2. Sumar 'En Tránsito' en Destino
            # (El stock viaja "hacia" el destino, así que se imputa allí como pendiente)
            StockManager.registrar_movimiento(
                articulo=item.articulo,
                deposito=transferencia.destino,
                codigo_tipo='TRNS', # Stock virtual de tránsito
                cantidad=item.cantidad, # Suma
                origen_sistema='TRANSFERENCIA',
                origen_referencia=ref,
                usuario=transferencia.creado_por
            )

        # Actualizar estado
        transferencia.estado = 'TR' # En Tránsito
        transferencia.movimiento_salida_aplicado = True
        transferencia.save()

    @staticmethod
    @transaction.atomic
    def recibir_transferencia(transferencia):
        """
        Paso 2: Confirmar llegada. Sacar de 'TRNS' y poner en 'REAL' del Destino.
        """
        if transferencia.estado != 'TR':
            raise ValidationError("Solo se pueden recibir transferencias que están 'En Tránsito'.")
        if transferencia.movimiento_entrada_aplicado:
            return

        ref = f"Recepción TRF #{transferencia.pk} desde {transferencia.origen}"

        for item in transferencia.items.all():
            # 1. Restar del Tránsito (Ya llegó)
            StockManager.registrar_movimiento(
                articulo=item.articulo,
                deposito=transferencia.destino,
                codigo_tipo='TRNS',
                cantidad=-item.cantidad, # Resta lo que estaba viajando
                origen_sistema='TRANSFERENCIA',
                origen_referencia=ref,
                usuario=transferencia.creado_por,
                permitir_stock_negativo=True # Permitimos porque es un clearing técnico
            )

            # 2. Sumar al Físico Real
            StockManager.registrar_movimiento(
                articulo=item.articulo,
                deposito=transferencia.destino,
                codigo_tipo='REAL',
                cantidad=item.cantidad, # Suma al stock disponible
                origen_sistema='TRANSFERENCIA',
                origen_referencia=ref,
                usuario=transferencia.creado_por
            )

        # Actualizar estado
        transferencia.estado = 'CP' # Completada
        transferencia.movimiento_entrada_aplicado = True
        transferencia.save()


class AjusteService:
    """
    Gestiona la confirmación de Ajustes Manuales.
    """

    @staticmethod
    @transaction.atomic
    def confirmar_ajuste(ajuste):
        if ajuste.estado != 'BR':
            raise ValidationError("Solo se pueden confirmar ajustes en estado Borrador.")
        if ajuste.stock_aplicado:
            return

        ref = f"Ajuste #{ajuste.pk}: {ajuste.motivo.nombre}"

        for item in ajuste.items.all():
            cantidad_final = item.cantidad

            # Si es SALIDA, invertimos el signo a negativo
            if item.tipo_movimiento == 'S':
                cantidad_final = -abs(item.cantidad)
            else:
                cantidad_final = abs(item.cantidad)

            # Impactamos en Stock REAL
            StockManager.registrar_movimiento(
                articulo=item.articulo,
                deposito=ajuste.deposito,
                codigo_tipo='REAL',
                cantidad=cantidad_final,
                origen_sistema='AJUSTE_MANUAL',
                origen_referencia=ref,
                usuario=ajuste.creado_por,
                observaciones=ajuste.observaciones,
                # IMPORTANTE: Permitimos negativo si es una corrección de stock,
                # pero el StockManager igual validará si el depósito/artículo lo prohíben
                # a menos que pasemos True.
                # Estrategia: Pasamos None para respetar la config del artículo.
                permitir_stock_negativo=None
            )

        ajuste.estado = 'CN'
        ajuste.stock_aplicado = True
        ajuste.save()