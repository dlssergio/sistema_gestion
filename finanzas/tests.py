# finanzas/tests.py

from django_tenants.test.cases import TenantTestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError

from parametros.models import Moneda
from finanzas.models import (
    Banco, CuentaFondo, TipoValor,
    MovimientoFondo, TransferenciaInterna, Cheque
)

User = get_user_model()


class FinanzasCoreTestCase(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        """
        Configura el schema falso para que corra aislado.
        """
        tenant.schema_name = 'test_tenant_finanzas'
        return tenant

    def setUp(self):
        """
        Prepara el entorno financiero base.
        """
        super().setUp()

        # 1. Usuario Admin
        self.usuario, _ = User.objects.get_or_create(username='finanzas_admin', defaults={'is_staff': True})

        # 2. Monedas
        self.moneda_pesos, _ = Moneda.objects.get_or_create(
            nombre="Pesos", defaults={"simbolo": "$", "cotizacion": 1, "es_base": True}
        )
        self.moneda_dolares, _ = Moneda.objects.get_or_create(
            nombre="Dólares", defaults={"simbolo": "U$S", "cotizacion": 1000, "es_base": False}
        )

        # 3. Tipos de Valor
        self.valor_efectivo, _ = TipoValor.objects.get_or_create(nombre="Efectivo")
        self.valor_transf, _ = TipoValor.objects.get_or_create(
            nombre="Transferencia", defaults={"requiere_banco": True}
        )
        self.valor_cheque, _ = TipoValor.objects.get_or_create(
            nombre="Cheque Propio", defaults={"es_cheque": True}
        )

        # 4. Cuentas de Fondo (Caja y Banco)
        self.caja_principal, _ = CuentaFondo.objects.get_or_create(
            nombre="Caja Fuerte",
            defaults={"tipo": CuentaFondo.Tipo.EFECTIVO, "moneda": self.moneda_pesos, "saldo_monto": Decimal('0.00')}
        )

        self.banco_macro, _ = Banco.objects.get_or_create(nombre="Banco Macro", codigo_bcra="0285")

        self.cuenta_macro, _ = CuentaFondo.objects.get_or_create(
            nombre="CC Macro Pesos",
            defaults={"tipo": CuentaFondo.Tipo.BANCO, "moneda": self.moneda_pesos, "banco": self.banco_macro,
                      "saldo_monto": Decimal('0.00')}
        )

        self.caja_dolares, _ = CuentaFondo.objects.get_or_create(
            nombre="Caja Fuerte U$S",
            defaults={"tipo": CuentaFondo.Tipo.EFECTIVO, "moneda": self.moneda_dolares, "saldo_monto": Decimal('0.00')}
        )

    def test_01_transferencia_interna_confirma_y_actualiza_saldos(self):
        """
        Si inyectamos dinero en Caja Fuerte, y lo transferimos a Banco Macro,
        los saldos deben reflejar la partida doble matemáticamente.
        """
        # INYECTAMOS 50.000 a la Caja (Simulando un saldo inicial a mano)
        self.caja_principal.saldo_monto = Decimal('50000.00')
        self.caja_principal.save()

        # Creamos una transferencia de 15.000 de Caja a Banco
        trf = TransferenciaInterna.objects.create(
            origen=self.caja_principal,
            destino=self.cuenta_macro,
            monto=Decimal('15000.00'),
            estado=TransferenciaInterna.Estado.BORRADOR,
            created_by=self.usuario
        )

        # CONFIRMAMOS LA TRANSFERENCIA (Se dispara el signal o llamamos directo)
        trf.estado = TransferenciaInterna.Estado.CONFIRMADO
        trf.save()

        # Refrescamos de base de datos
        self.caja_principal.refresh_from_db()
        self.cuenta_macro.refresh_from_db()

        # VERIFICACIÓN 1: Saldos Cuentas
        self.assertEqual(self.caja_principal.saldo_monto, Decimal('35000.00'), "La caja no descontó la transferencia.")
        self.assertEqual(self.cuenta_macro.saldo_monto, Decimal('15000.00'), "El banco no sumó la transferencia.")

        # VERIFICACIÓN 2: Movimientos en el Libro Mayor (MovimientoFondo)
        movs = MovimientoFondo.objects.filter(concepto__contains="TRF").order_by('fecha')
        self.assertEqual(movs.count(), 2, "Deben existir 2 movimientos de fondo (Ingreso y Egreso).")

        egreso = movs.get(tipo_movimiento=MovimientoFondo.TipoMov.EGRESO)
        ingreso = movs.get(tipo_movimiento=MovimientoFondo.TipoMov.INGRESO)

        self.assertEqual(egreso.cuenta, self.caja_principal)
        self.assertEqual(ingreso.cuenta, self.cuenta_macro)
        self.assertEqual(egreso.monto_egreso, Decimal('15000.00'))

    def test_02_anular_transferencia_revierte_saldos(self):
        """
        Anular una transferencia previamente confirmada debe devolver el dinero al origen.
        """
        # INYECTAMOS 20.000 a Banco
        self.cuenta_macro.saldo_monto = Decimal('20000.00')
        self.cuenta_macro.save()

        # Banco -> Caja (10.000)
        trf = TransferenciaInterna.objects.create(
            origen=self.cuenta_macro,
            destino=self.caja_principal,
            monto=Decimal('10000.00'),
            estado=TransferenciaInterna.Estado.CONFIRMADO,  # Lo creamos ya confirmado
            created_by=self.usuario
        )

        # Verificamos impacto parcial
        self.cuenta_macro.refresh_from_db()
        self.assertEqual(self.cuenta_macro.saldo_monto, Decimal('10000.00'))

        # ANULAMOS
        trf.estado = TransferenciaInterna.Estado.ANULADO
        trf.save()

        # Verificamos reversión total
        self.cuenta_macro.refresh_from_db()
        self.caja_principal.refresh_from_db()

        self.assertEqual(self.cuenta_macro.saldo_monto, Decimal('20000.00'), "No devolvió el saldo al anular.")
        self.assertEqual(self.caja_principal.saldo_monto, Decimal('0.00'), "No restó el saldo del destino al anular.")
        self.assertFalse(trf.finanzas_aplicadas, "El flag de control debe volver a False.")

    def test_03_validacion_monedas_distintas(self):
        """
        El modelo debe impedir transferencias directas entre cuentas de distinta moneda (Pesos vs Dólares).
        """
        trf = TransferenciaInterna(
            origen=self.caja_principal,  # Pesos
            destino=self.caja_dolares,  # Dólares
            monto=Decimal('100.00'),
            estado=TransferenciaInterna.Estado.BORRADOR,
            created_by=self.usuario
        )

        # Debemos atrapar el ValidationError cuando corremos el clean()
        with self.assertRaisesMessage(ValidationError, "Las cuentas deben ser de la misma moneda."):
            trf.clean()

    def test_04_validacion_misma_cuenta(self):
        """
        No se puede transferir plata de la Caja Fuerte a la misma Caja Fuerte.
        """
        trf = TransferenciaInterna(
            origen=self.caja_principal,
            destino=self.caja_principal,
            monto=Decimal('1000.00')
        )
        with self.assertRaisesMessage(ValidationError, "La cuenta de origen y destino no pueden ser la misma."):
            trf.clean()