# inventario/tests.py

# CAMBIO CLAVE: Usamos TenantTestCase en lugar de TestCase normal
from django_tenants.test.cases import TenantTestCase
from django.contrib.auth import get_user_model
from decimal import Decimal

# Importamos los modelos necesarios para el entorno de pruebas
from parametros.models import Moneda, UnidadMedida, SerieDocumento
from inventario.models import (
    Articulo, Deposito, TipoStock, Rubro,
    MovimientoStock, ItemMovimientoStock,
    BalanceStock, MovimientoStockLedger
)
from inventario.services import StockManager

User = get_user_model()


class InventarioStockTestCase(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        """
        Esta función es específica de django-tenants.
        Configura el tenant de pruebas antes de correr los tests.
        """
        tenant.schema_name = 'test_tenant'
        return tenant

    def setUp(self):
        """
        Prepara el entorno base antes de cada test.
        Usa get_or_create para evitar colisiones con datos pre-poblados por migraciones.
        """
        super().setUp()

        # 1. Usuario Admin
        self.usuario, _ = User.objects.get_or_create(username='test_admin', defaults={'is_staff': True})
        if not self.usuario.check_password('123'):
            self.usuario.set_password('123')
            self.usuario.save()

        # 2. Parámetros Base
        self.moneda, _ = Moneda.objects.get_or_create(
            nombre="Pesos", defaults={"simbolo": "$", "cotizacion": 1, "es_base": True}
        )
        self.uom, _ = UnidadMedida.objects.get_or_create(
            nombre="Unidad", defaults={"simbolo": "u"}
        )
        self.rubro, _ = Rubro.objects.get_or_create(nombre="General")

        # 3. Tipos de Stock
        self.tipo_real, _ = TipoStock.objects.get_or_create(
            codigo='REAL', defaults={'nombre': 'Físico', 'es_fisico': True, 'es_vendible': True}
        )

        # 4. Depósitos
        self.deposito_central, _ = Deposito.objects.get_or_create(
            nombre="Depósito Central", defaults={"es_principal": True}
        )
        self.deposito_sucursal, _ = Deposito.objects.get_or_create(
            nombre="Sucursal 1"
        )

        # 5. Artículo de Prueba
        self.articulo, _ = Articulo.objects.get_or_create(
            cod_articulo="TEST-001",
            defaults={
                "descripcion": "Producto de Prueba Enterprise",
                "rubro": self.rubro,
                "unidad_medida_stock": self.uom,
                "unidad_medida_venta": self.uom,
                "precio_costo_moneda": self.moneda,
                "precio_venta_moneda": self.moneda,
                "administra_stock": True
            }
        )

        # 6. Tipo de Comprobante (Faltaba esto para que no dé error NotNull)
        # Importamos TipoComprobante aquí dentro para evitar referencias circulares arriba si las hay.
        from parametros.models import TipoComprobante
        self.tipo_comp_stock, _ = TipoComprobante.objects.get_or_create(
            nombre="Ajuste de Inventario",
            defaults={
                "clase": 'S',  # 'S' de Stock
                "mueve_stock": True,
                "signo_stock": 0,
                "mueve_cta_cte": False,
                "mueve_caja": False,
                "es_fiscal": False,
                "numeracion_automatica": True
            }
        )

        # 7. Serie para Movimientos Internos (Ahora sí, vinculada al tipo de comprobante)
        self.serie_mov, _ = SerieDocumento.objects.get_or_create(
            nombre="Movimientos Internos",
            defaults={
                "tipo_comprobante": self.tipo_comp_stock,  # ¡Agregamos el tipo de comprobante!
                "ultimo_numero": 0,
                "activo": True,
                "es_manual": False
            }
        )

    def test_01_entrada_stock_actualiza_ledger_y_balance(self):
        """
        Prueba 1: Una Entrada de Stock debe sumar al BalanceStock y crear un registro en el Ledger.
        """
        mov = MovimientoStock.objects.create(
            serie=self.serie_mov,
            tipo_movimiento=MovimientoStock.Tipo.ENTRADA,
            deposito_destino=self.deposito_central,
            estado=MovimientoStock.Estado.CONFIRMADO,
            created_by=self.usuario
        )

        ItemMovimientoStock.objects.create(
            movimiento=mov,
            articulo=self.articulo,
            cantidad=Decimal('50.000')
        )

        mov.confirmar_movimiento()

        balance = BalanceStock.objects.get(
            articulo=self.articulo,
            deposito=self.deposito_central,
            tipo_stock=self.tipo_real
        )
        self.assertEqual(balance.cantidad, Decimal('50.000'), "El balance de stock no se sumó correctamente.")

        ledger_count = MovimientoStockLedger.objects.filter(
            articulo=self.articulo,
            cantidad=Decimal('50.000')
        ).count()
        self.assertEqual(ledger_count, 1, "No se guardó el registro inmutable en el Ledger.")

    def test_02_transferencia_entre_depositos(self):
        """
        Prueba 2: Una Transferencia debe restar del Origen y sumar al Destino garantizando partida doble.
        """
        StockManager.registrar_movimiento(
            articulo=self.articulo, deposito=self.deposito_central,
            codigo_tipo='REAL', cantidad=Decimal('100.000'),
            origen_sistema='TEST', origen_referencia='INIT', usuario=self.usuario,
            permitir_stock_negativo=True
        )

        mov = MovimientoStock.objects.create(
            serie=self.serie_mov,
            tipo_movimiento=MovimientoStock.Tipo.TRANSFERENCIA,
            deposito_origen=self.deposito_central,
            deposito_destino=self.deposito_sucursal,
            estado=MovimientoStock.Estado.CONFIRMADO,
            created_by=self.usuario
        )
        ItemMovimientoStock.objects.create(
            movimiento=mov,
            articulo=self.articulo,
            cantidad=Decimal('30.000')
        )

        mov.confirmar_movimiento()

        balance_central = BalanceStock.objects.get(
            articulo=self.articulo, deposito=self.deposito_central, tipo_stock=self.tipo_real
        )
        balance_sucursal = BalanceStock.objects.get(
            articulo=self.articulo, deposito=self.deposito_sucursal, tipo_stock=self.tipo_real
        )

        self.assertEqual(balance_central.cantidad, Decimal('70.000'), "El depósito origen no descontó el stock.")
        self.assertEqual(balance_sucursal.cantidad, Decimal('30.000'), "El depósito destino no sumó el stock.")

    def test_03_revertir_movimiento_restaura_saldos(self):
        """
        Prueba 3: Anular un movimiento debe hacer un contrasiento exacto en el Ledger.
        """
        mov = MovimientoStock.objects.create(
            serie=self.serie_mov,
            tipo_movimiento=MovimientoStock.Tipo.ENTRADA,
            deposito_destino=self.deposito_central,
            estado=MovimientoStock.Estado.CONFIRMADO,
            created_by=self.usuario
        )
        ItemMovimientoStock.objects.create(movimiento=mov, articulo=self.articulo, cantidad=Decimal('20.000'))
        mov.confirmar_movimiento()

        balance = BalanceStock.objects.get(articulo=self.articulo, deposito=self.deposito_central,
                                           tipo_stock=self.tipo_real)
        self.assertEqual(balance.cantidad, Decimal('20.000'))

        mov.revertir_movimiento()

        balance.refresh_from_db()
        self.assertEqual(balance.cantidad, Decimal('0.000'), "La reversión no dejó el balance en 0.")

        movimientos_ledger = MovimientoStockLedger.objects.filter(articulo=self.articulo).order_by('fecha_registro')
        self.assertEqual(movimientos_ledger.count(), 2, "Debe haber 2 registros en el Ledger (Ida y Vuelta).")
        self.assertEqual(movimientos_ledger[0].cantidad, Decimal('20.000'))
        self.assertEqual(movimientos_ledger[1].cantidad, Decimal('-20.000'))