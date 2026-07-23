# ventas/tests.py
"""
Tests automatizados — Módulo de Ventas
=======================================
Compatibilidad con django-tenants: los tests utilizan la clase oficial
TenantTestCase que crea la DB temporal, migra el schema public, crea
un tenant de prueba, migra el schema del tenant y enruta las queries.

Ejecutar con:
    python manage.py test ventas --verbosity=2
"""
import logging
from decimal import Decimal

from django.utils import timezone
from django.contrib.auth import get_user_model

# ── Importación Crítica para Multi-Tenant ──
from django_tenants.test.cases import TenantTestCase

from ventas.models import (
    Cliente, ComprobanteVenta, ComprobanteVentaItem,
    Recibo, ReciboImputacion, ReciboValor,
)
from ventas.cuenta_corriente_api import CuentaCorrienteService
from inventario.models import (
    Articulo, Deposito, TipoStock, BalanceStock,
)
from parametros.models import TipoComprobante
from entidades.models import Entidad, SituacionIVA
from finanzas.models import CuentaFondo, TipoValor

User = get_user_model()
logging.disable(logging.CRITICAL)


# ═══════════════════════════════════════════════════════════════════════════
# BASE — Configuración oficial para django-tenants
# ═══════════════════════════════════════════════════════════════════════════

class TenantAwareTestCase(TenantTestCase):
    """
    Clase base que hereda de TenantTestCase.
    Se encarga de construir el tenant de prueba aislado.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        """Configura los campos obligatorios de tu modelo Company"""
        tenant.schema_name = 'test_schema'
        tenant.name = 'Empresa Test'
        # Añade aquí otros campos obligatorios que tenga tu modelo Company si fallara
        return tenant

    @classmethod
    def setup_domain(cls, domain):
        """Configura los campos obligatorios de tu modelo Domain"""
        domain.domain = 'test.localhost'
        domain.is_primary = True
        return domain


# ═══════════════════════════════════════════════════════════════════════════
# FACTORIES
# ═══════════════════════════════════════════════════════════════════════════

_entidad_counter = 0


def make_entidad(**kwargs):
    global _entidad_counter
    _entidad_counter += 1

    # Nos aseguramos de tener al menos una Situación de IVA creada
    situacion_iva, _ = SituacionIVA.objects.get_or_create(
        nombre='Responsable Inscripto',
        defaults={'is_active': True}
    )

    defaults = dict(
        razon_social=f'Empresa Test {_entidad_counter}',
        cuit=f'30-{_entidad_counter:08d}-9',
        email=f'test{_entidad_counter}@empresa.com',
        situacion_iva=situacion_iva,  # <--- ¡Agregamos esto!
    )
    defaults.update(kwargs)
    return Entidad.objects.create(**defaults)


def make_cliente(entidad=None, permite_cta_cte=True, limite_credito=100000, **kwargs):
    if entidad is None:
        entidad = make_entidad()
    return Cliente.objects.create(
        entidad=entidad,
        permite_cta_cte=permite_cta_cte,
        limite_credito=Decimal(str(limite_credito)),
        dias_vencimiento=30,
        **kwargs
    )


def make_tipo_comprobante(nombre='Factura A', letra='A', mueve_stock=True,
                          afecta_stock_fisico=True, afecta_stock_comprometido=False,
                          signo_stock=-1, codigo_afip='001', **kwargs):
    return TipoComprobante.objects.create(
        nombre=nombre, letra=letra, codigo_afip=codigo_afip,
        mueve_stock=mueve_stock, afecta_stock_fisico=afecta_stock_fisico,
        afecta_stock_comprometido=afecta_stock_comprometido,
        signo_stock=signo_stock, **kwargs
    )


def make_deposito(nombre='Principal', permite_stock_negativo=False):
    return Deposito.objects.get_or_create(
        nombre=nombre,
        defaults={'es_principal': True, 'permite_stock_negativo': permite_stock_negativo}
    )[0]


def make_tipo_stock(codigo='REAL'):
    return TipoStock.objects.get_or_create(
        codigo=codigo, defaults={'nombre': codigo}
    )[0]


def make_articulo(codigo=None, precio='1000.00', **kwargs):
    global _entidad_counter
    _entidad_counter += 1
    if codigo is None:
        codigo = f'ART{_entidad_counter:04d}'
    from inventario.models import Rubro
    rubro, _ = Rubro.objects.get_or_create(
        nombre='Rubro Test',
        defaults={}
    )
    # Remover campos inválidos del modelo
    kwargs.pop('activo', None)
    kwargs.pop('codigo', None)
    return Articulo.objects.create(
        cod_articulo=codigo,
        descripcion=f'Artículo {codigo}',
        precio_venta_monto=Decimal(precio),
        permite_stock_negativo=kwargs.pop('permite_stock_negativo', False),
        is_active=True,
        rubro=rubro,
        **kwargs
    )


def set_stock(articulo, deposito, tipo_stock, cantidad):
    BalanceStock.objects.update_or_create(
        articulo=articulo, deposito=deposito, tipo_stock=tipo_stock,
        defaults={'cantidad': Decimal(str(cantidad))}
    )


def make_comprobante(cliente, tipo, deposito, items_data,
                     condicion=ComprobanteVenta.CondicionVenta.CTA_CTE,
                     estado=ComprobanteVenta.Estado.BORRADOR):
    global _entidad_counter
    _entidad_counter += 1
    comp = ComprobanteVenta.objects.create(
        cliente=cliente, tipo_comprobante=tipo,
        condicion_venta=condicion, deposito=deposito,
        estado=estado, punto_venta=1,
        numero=_entidad_counter, letra=tipo.letra or 'A',
    )
    subtotal = Decimal('0')
    for d in items_data:
        precio = Decimal(str(d['precio_unitario']))
        cant = Decimal(str(d['cantidad']))

        # --- AQUÍ ESTÁ EL CAMBIO FINAL ---
        ComprobanteVentaItem.objects.create(
            comprobante=comp,
            articulo=d['articulo'],
            cantidad=cant,
            precio_unitario_original=precio  # <--- Nombre exacto de tu modelo
        )

        subtotal += precio * cant

    comp.recalcular_totales_y_saldo(
        nuevo_subtotal=subtotal, nuevos_impuestos={}, nuevo_total=subtotal
    )
    comp.save()
    return comp


def confirmar_comprobante(comp):
    comp.estado = ComprobanteVenta.Estado.CONFIRMADO
    comp.save()
    comp.refresh_from_db()
    return comp


def make_cuenta_fondo(nombre='Caja Principal', saldo=Decimal('0')):
    return CuentaFondo.objects.get_or_create(
        nombre=nombre, defaults={'saldo_monto': saldo}
    )[0]


def make_tipo_valor(nombre='Efectivo'):
    return TipoValor.objects.get_or_create(
        nombre=nombre, defaults={'es_cheque': False}
    )[0]


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1 — Comprobante básico
# ═══════════════════════════════════════════════════════════════════════════

class ComprobanteBasicoTests(TenantAwareTestCase):

    def setUp(self):
        super().setUp()
        self.cliente = make_cliente()
        self.tipo_fac = make_tipo_comprobante(mueve_stock=False)
        self.deposito = make_deposito()
        self.art = make_articulo()

    def test_total_calculado_correctamente(self):
        comp = make_comprobante(
            self.cliente, self.tipo_fac, self.deposito,
            [{'articulo': self.art, 'cantidad': 2, 'precio_unitario': '500.00'}]
        )
        self.assertEqual(comp.total, Decimal('1000.00'))

    def test_saldo_pendiente_igual_total_en_borrador(self):
        comp = make_comprobante(
            self.cliente, self.tipo_fac, self.deposito,
            [{'articulo': self.art, 'cantidad': 1, 'precio_unitario': '1500.00'}]
        )
        self.assertEqual(comp.saldo_pendiente, comp.total)

    def test_estado_pago_impago(self):
        comp = make_comprobante(
            self.cliente, self.tipo_fac, self.deposito,
            [{'articulo': self.art, 'cantidad': 1, 'precio_unitario': '800.00'}]
        )
        self.assertEqual(comp.estado_pago, 'IMPAGO')

    def test_estado_pago_pagado(self):
        comp = make_comprobante(
            self.cliente, self.tipo_fac, self.deposito,
            [{'articulo': self.art, 'cantidad': 1, 'precio_unitario': '800.00'}]
        )
        comp.saldo_pendiente = Decimal('0')
        comp.save()
        self.assertEqual(comp.estado_pago, 'PAGADO')

    def test_estado_pago_parcial(self):
        comp = make_comprobante(
            self.cliente, self.tipo_fac, self.deposito,
            [{'articulo': self.art, 'cantidad': 1, 'precio_unitario': '1000.00'}]
        )
        comp.saldo_pendiente = Decimal('400.00')
        comp.save()
        self.assertEqual(comp.estado_pago, 'PARCIAL')

    def test_saldo_pendiente_no_negativo_tras_recalculo(self):
        comp = make_comprobante(
            self.cliente, self.tipo_fac, self.deposito,
            [{'articulo': self.art, 'cantidad': 1, 'precio_unitario': '1000.00'}]
        )
        comp.saldo_pendiente = Decimal('0')
        comp.estado = ComprobanteVenta.Estado.CONFIRMADO
        comp.save()
        comp.recalcular_totales_y_saldo(
            nuevo_subtotal=Decimal('800'), nuevos_impuestos={}, nuevo_total=Decimal('800')
        )
        self.assertGreaterEqual(comp.saldo_pendiente, Decimal('0'))

    def test_cliente_sin_cta_cte_no_puede_usar_condicion_cc(self):
        from django.core.exceptions import ValidationError
        cliente_contado = make_cliente(permite_cta_cte=False)
        comp = ComprobanteVenta(
            cliente=cliente_contado, tipo_comprobante=self.tipo_fac,
            condicion_venta=ComprobanteVenta.CondicionVenta.CTA_CTE,
            deposito=self.deposito, estado=ComprobanteVenta.Estado.BORRADOR,
        )
        with self.assertRaises(ValidationError):
            comp.clean()


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2 — Movimiento de stock
# ═══════════════════════════════════════════════════════════════════════════

class StockMovimientoTests(TenantAwareTestCase):

    def setUp(self):
        super().setUp()
        make_tipo_stock('REAL')
        make_tipo_stock('RSRV')
        self.deposito = make_deposito()
        self.cliente = make_cliente()
        self.art = make_articulo()
        set_stock(self.art, self.deposito, TipoStock.objects.get(codigo='REAL'), 50)

    def _stock_real(self):
        tipo = TipoStock.objects.get(codigo='REAL')
        b = BalanceStock.objects.filter(
            articulo=self.art, deposito=self.deposito, tipo_stock=tipo
        ).first()
        return b.cantidad if b else Decimal('0')

    def test_confirmacion_descuenta_stock_real(self):
        tipo = make_tipo_comprobante(
            nombre='Fac Stock', mueve_stock=True,
            afecta_stock_fisico=True, signo_stock=-1,
        )
        comp = make_comprobante(
            self.cliente, tipo, self.deposito,
            [{'articulo': self.art, 'cantidad': 5, 'precio_unitario': '100'}],
            condicion=ComprobanteVenta.CondicionVenta.CONTADO,
        )
        stock_antes = self._stock_real()
        confirmar_comprobante(comp)
        self.assertEqual(stock_antes - self._stock_real(), Decimal('5'))

    def test_stock_aplicado_impide_doble_movimiento(self):
        tipo = make_tipo_comprobante(
            nombre='Fac Doble', mueve_stock=True,
            afecta_stock_fisico=True, signo_stock=-1,
        )
        comp = make_comprobante(
            self.cliente, tipo, self.deposito,
            [{'articulo': self.art, 'cantidad': 3, 'precio_unitario': '100'}],
            condicion=ComprobanteVenta.CondicionVenta.CONTADO,
        )
        confirmar_comprobante(comp)
        stock_tras_primera = self._stock_real()
        comp.observaciones = 'segundo save'
        comp.save()
        self.assertEqual(stock_tras_primera, self._stock_real())

    def test_nc_financiero_no_mueve_stock(self):
        tipo_nc = make_tipo_comprobante(
            nombre='NC Fin', letra='A', codigo_afip='003',
            mueve_stock=True, afecta_stock_fisico=True, signo_stock=1,
        )
        stock_antes = self._stock_real()
        comp = make_comprobante(
            self.cliente, tipo_nc, self.deposito,
            [{'articulo': self.art, 'cantidad': 2, 'precio_unitario': '100'}],
            condicion=ComprobanteVenta.CondicionVenta.CONTADO,
        )
        comp.concepto_nota_credito = ComprobanteVenta.ConceptoNC.FINANCIERO
        comp.save()
        confirmar_comprobante(comp)
        self.assertEqual(self._stock_real(), stock_antes)

    def test_nc_devolucion_devuelve_stock(self):
        tipo_nc = make_tipo_comprobante(
            nombre='NC Dev', letra='A', codigo_afip='003',
            mueve_stock=True, afecta_stock_fisico=True, signo_stock=1,
        )
        stock_antes = self._stock_real()
        comp = make_comprobante(
            self.cliente, tipo_nc, self.deposito,
            [{'articulo': self.art, 'cantidad': 4, 'precio_unitario': '100'}],
            condicion=ComprobanteVenta.CondicionVenta.CONTADO,
        )
        comp.concepto_nota_credito = ComprobanteVenta.ConceptoNC.DEVOLUCION
        comp.save()
        confirmar_comprobante(comp)
        self.assertEqual(self._stock_real(), stock_antes + Decimal('4'))

    def test_stock_no_mueve_si_tipo_no_mueve_stock(self):
        tipo = make_tipo_comprobante(
            nombre='Presup', mueve_stock=False, afecta_stock_fisico=False, signo_stock=0
        )
        stock_antes = self._stock_real()
        comp = make_comprobante(
            self.cliente, tipo, self.deposito,
            [{'articulo': self.art, 'cantidad': 10, 'precio_unitario': '100'}],
            condicion=ComprobanteVenta.CondicionVenta.CONTADO,
        )
        confirmar_comprobante(comp)
        self.assertEqual(self._stock_real(), stock_antes)


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 3 — Recibo e imputación
# ═══════════════════════════════════════════════════════════════════════════

class ReciboImputacionTests(TenantAwareTestCase):

    def setUp(self):
        super().setUp()
        # 1. CREAMOS EL USUARIO DE PRUEBA
        self.user = User.objects.create_user(username='cajero_test', password='123')

        self.cliente = make_cliente()
        self.deposito = make_deposito()
        self.tipo_fac = make_tipo_comprobante(mueve_stock=False)
        self.art = make_articulo()
        self.cuenta = make_cuenta_fondo()
        self.t_valor = make_tipo_valor()

    def _factura_cc(self, total='2000.00'):
        comp = make_comprobante(
            self.cliente, self.tipo_fac, self.deposito,
            [{'articulo': self.art, 'cantidad': 1, 'precio_unitario': total}],
            condicion=ComprobanteVenta.CondicionVenta.CTA_CTE,
        )
        comp.estado = ComprobanteVenta.Estado.CONFIRMADO
        comp.save()
        return comp

    def _make_recibo(self, comp, monto):
        global _entidad_counter
        _entidad_counter += 1
        recibo = Recibo.objects.create(
            cliente=self.cliente, estado=Recibo.Estado.BORRADOR,
            origen=Recibo.Origen.COBRANZA,
            monto_total=Decimal(str(monto)),
            numero=_entidad_counter,
            created_by=self.user
        )
        ReciboImputacion.objects.create(
            recibo=recibo, comprobante=comp, monto_imputado=Decimal(str(monto))
        )
        ReciboValor.objects.create(
            recibo=recibo, tipo=self.t_valor,
            destino=self.cuenta, monto=Decimal(str(monto))
        )
        return recibo

    def test_recibo_reduce_saldo_pendiente(self):
        comp = self._factura_cc('1000.00')
        recibo = self._make_recibo(comp, '600.00')
        recibo.estado = Recibo.Estado.CONFIRMADO
        recibo.save()
        recibo.aplicar_finanzas()
        comp.refresh_from_db()
        self.assertEqual(comp.saldo_pendiente, Decimal('400.00'))

    def test_recibo_pago_total_deja_saldo_cero(self):
        comp = self._factura_cc('1500.00')
        recibo = self._make_recibo(comp, '1500.00')
        recibo.estado = Recibo.Estado.CONFIRMADO
        recibo.save()
        recibo.aplicar_finanzas()
        comp.refresh_from_db()
        self.assertEqual(comp.saldo_pendiente, Decimal('0.00'))
        self.assertEqual(comp.estado_pago, 'PAGADO')

    def test_aplicar_finanzas_dos_veces_no_duplica(self):
        comp = self._factura_cc('1000.00')
        recibo = self._make_recibo(comp, '1000.00')
        recibo.estado = Recibo.Estado.CONFIRMADO
        recibo.save()
        recibo.aplicar_finanzas()
        recibo.aplicar_finanzas()
        comp.refresh_from_db()
        self.assertEqual(comp.saldo_pendiente, Decimal('0.00'))

    def test_revertir_recibo_restaura_saldo(self):
        comp = self._factura_cc('2000.00')
        recibo = self._make_recibo(comp, '800.00')
        recibo.estado = Recibo.Estado.CONFIRMADO
        recibo.save()
        recibo.aplicar_finanzas()
        comp.refresh_from_db()
        self.assertEqual(comp.saldo_pendiente, Decimal('1200.00'))
        recibo.revertir_finanzas()
        comp.refresh_from_db()
        self.assertEqual(comp.saldo_pendiente, Decimal('2000.00'))

    def test_recibo_incrementa_saldo_cuenta_fondo(self):
        self.cuenta.saldo_monto = Decimal('500.00')
        self.cuenta.save()
        comp = self._factura_cc('1000.00')
        recibo = self._make_recibo(comp, '1000.00')
        recibo.estado = Recibo.Estado.CONFIRMADO
        recibo.save()
        recibo.aplicar_finanzas()
        self.cuenta.refresh_from_db()
        self.assertEqual(self.cuenta.saldo_monto, Decimal('1500.00'))


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 4 — Saldo de cuenta corriente
# ═══════════════════════════════════════════════════════════════════════════

class SaldoCuentaCorrienteTests(TenantAwareTestCase):

    def setUp(self):
        super().setUp()
        self.cliente = make_cliente()
        self.deposito = make_deposito()
        make_tipo_stock('REAL')
        self.tipo_fac = make_tipo_comprobante(mueve_stock=False, nombre='Fac CC')
        self.tipo_nc = make_tipo_comprobante(
            nombre='NC CC', mueve_stock=False, codigo_afip='003',
            afecta_stock_fisico=False, signo_stock=-1,
        )
        self.art = make_articulo()
        self.cuenta = make_cuenta_fondo(nombre='Caja CC')
        self.t_valor = make_tipo_valor(nombre='Efvo CC')

    def _saldo(self):
        return CuentaCorrienteService._saldo_al_cierre(
            self.cliente, hasta=timezone.localdate()
        )

    def _confirmar_factura_cc(self, total):
        comp = make_comprobante(
            self.cliente, self.tipo_fac, self.deposito,
            [{'articulo': self.art, 'cantidad': 1, 'precio_unitario': str(total)}],
            condicion=ComprobanteVenta.CondicionVenta.CTA_CTE,
        )
        comp.estado = ComprobanteVenta.Estado.CONFIRMADO
        comp.save()
        return comp

    def test_saldo_cero_sin_movimientos(self):
        self.assertEqual(self._saldo(), Decimal('0'))

    def test_factura_cc_aumenta_saldo(self):
        self._confirmar_factura_cc('3000.00')
        self.assertEqual(self._saldo(), Decimal('3000.00'))

    def test_factura_contado_no_afecta_saldo_cc(self):
        comp = make_comprobante(
            self.cliente, self.tipo_fac, self.deposito,
            [{'articulo': self.art, 'cantidad': 1, 'precio_unitario': '5000.00'}],
            condicion=ComprobanteVenta.CondicionVenta.CONTADO,
        )
        comp.estado = ComprobanteVenta.Estado.CONFIRMADO
        comp.save()
        self.assertEqual(self._saldo(), Decimal('0'))

    def test_nc_reduce_saldo(self):
        self._confirmar_factura_cc('4000.00')
        # NC CC: es_nota_credito=True → va a HABER en _saldo_al_cierre
        comp_nc = make_comprobante(
            self.cliente, self.tipo_nc, self.deposito,
            [{'articulo': self.art, 'cantidad': 1, 'precio_unitario': '1000.00'}],
            condicion=ComprobanteVenta.CondicionVenta.CTA_CTE,
        )
        comp_nc.estado = ComprobanteVenta.Estado.CONFIRMADO
        comp_nc.save()
        self.assertEqual(self._saldo(), Decimal('3000.00'))

    def test_recibo_reduce_saldo(self):
        user = User.objects.create_user(username='cajero_cc', password='123')
        comp = self._confirmar_factura_cc('2000.00')

        recibo = Recibo.objects.create(
            cliente=self.cliente, estado=Recibo.Estado.CONFIRMADO,
            origen=Recibo.Origen.COBRANZA,
            monto_total=Decimal('500.00'), numero=9901,
            created_by=user
        )
        ReciboImputacion.objects.create(
            recibo=recibo, comprobante=comp, monto_imputado=Decimal('500.00')
        )
        ReciboValor.objects.create(
            recibo=recibo, tipo=self.t_valor,
            destino=self.cuenta, monto=Decimal('500.00')
        )
        recibo.aplicar_finanzas()
        self.assertEqual(self._saldo(), Decimal('1500.00'))

    def test_multiples_facturas_acumulan_saldo(self):
        self._confirmar_factura_cc('1000.00')
        self._confirmar_factura_cc('2000.00')
        self._confirmar_factura_cc('500.00')
        self.assertEqual(self._saldo(), Decimal('3500.00'))


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 5 — Integridad
# ═══════════════════════════════════════════════════════════════════════════

class IntegridadTests(TenantAwareTestCase):

    def setUp(self):
        super().setUp()
        make_tipo_stock('REAL')
        self.deposito = make_deposito(permite_stock_negativo=False)
        self.cliente = make_cliente()
        self.art = make_articulo(permite_stock_negativo=False)
        set_stock(self.art, self.deposito, TipoStock.objects.get(codigo='REAL'), 5)

    def test_venta_mayor_al_stock_lanza_error(self):
        from django.core.exceptions import ValidationError
        tipo = make_tipo_comprobante(
            nombre='Fac Int', mueve_stock=True, afecta_stock_fisico=True, signo_stock=-1
        )
        comp = make_comprobante(
            self.cliente, tipo, self.deposito,
            [{'articulo': self.art, 'cantidad': 10, 'precio_unitario': '100'}],
            condicion=ComprobanteVenta.CondicionVenta.CONTADO,
        )
        with self.assertRaises((ValidationError, Exception)):
            confirmar_comprobante(comp)
        tipo_stock = TipoStock.objects.get(codigo='REAL')
        balance = BalanceStock.objects.filter(
            articulo=self.art, deposito=self.deposito, tipo_stock=tipo_stock
        ).first()
        self.assertEqual(balance.cantidad if balance else Decimal('0'), Decimal('5'))

    def test_recibo_desbalanceado_lanza_error(self):
        from django.core.exceptions import ValidationError
        tipo_fac = make_tipo_comprobante(mueve_stock=False, nombre='Fac Des')
        art = make_articulo()
        cuenta = make_cuenta_fondo(nombre='Caja Des')
        t_valor = make_tipo_valor(nombre='Efvo Des')
        comp = make_comprobante(
            self.cliente, tipo_fac, self.deposito,
            [{'articulo': art, 'cantidad': 1, 'precio_unitario': '1000.00'}],
            condicion=ComprobanteVenta.CondicionVenta.CTA_CTE,
        )
        comp.estado = ComprobanteVenta.Estado.CONFIRMADO
        comp.save()
        recibo = Recibo.objects.create(
            cliente=self.cliente, estado=Recibo.Estado.CONFIRMADO,
            origen=Recibo.Origen.COBRANZA,
            monto_total=Decimal('1000.00'), numero=9999,
        )
        ReciboImputacion.objects.create(
            recibo=recibo, comprobante=comp, monto_imputado=Decimal('1000.00')
        )
        ReciboValor.objects.create(
            recibo=recibo, tipo=t_valor, destino=cuenta, monto=Decimal('500.00')
        )
        with self.assertRaises(ValidationError):
            recibo.aplicar_finanzas()


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 6 — Ciclo Logístico Completo (Capa 4)
# ═══════════════════════════════════════════════════════════════════════════

class CicloLogisticoCompletoTests(TenantAwareTestCase):
    """
    Test de integración complejo que valida la consistencia de inventario y
    cuenta corriente a lo largo del ciclo: Nota de Pedido → Remito → Factura.
    """

    def setUp(self):
        super().setUp()
        make_tipo_stock('REAL')
        make_tipo_stock('RSRV')
        self.deposito = make_deposito()
        self.cliente = make_cliente(permite_cta_cte=True)
        self.art = make_articulo(precio='2000.00')

        # Definimos las reglas de negocio de los tipos de comprobantes implicados
        self.tipo_pedido = make_tipo_comprobante(
            nombre='Nota de Pedido', letra='X', codigo_afip='991',
            mueve_stock=True, afecta_stock_fisico=False, afecta_stock_comprometido=True,
            signo_stock=1  # Suma al stock comprometido (RSRV)
        )
        self.tipo_remito = make_tipo_comprobante(
            nombre='Remito', letra='R', codigo_afip='091',
            mueve_stock=True, afecta_stock_fisico=True, afecta_stock_comprometido=False,
            signo_stock=-1  # Resta al stock real (REAL)
        )
        self.tipo_factura = make_tipo_comprobante(
            nombre='Factura de Venta', letra='A', codigo_afip='001',
            mueve_stock=False, afecta_stock_fisico=False, afecta_stock_comprometido=False,
            signo_stock=0  # La factura posterior al remito no altera stock
        )

        # Inicializamos el stock físico en 10 unidades
        set_stock(self.art, self.deposito, TipoStock.objects.get(codigo='REAL'), 10)
        set_stock(self.art, self.deposito, TipoStock.objects.get(codigo='RSRV'), 0)

    def _get_cantidad_stock(self, codigo_tipo):
        tipo = TipoStock.objects.get(codigo=codigo_tipo)
        b = BalanceStock.objects.filter(
            articulo=self.art, deposito=self.deposito, tipo_stock=tipo
        ).first()
        return b.cantidad if b else Decimal('0')

    def test_ciclo_logistico_exitoso(self):
        # ──────────────────────────────────────────────────────────────────────
        # PASO 1: Creación de la Nota de Pedido (Reserva de mercadería)
        # ──────────────────────────────────────────────────────────────────────
        pedido = make_comprobante(
            self.cliente, self.tipo_pedido, self.deposito,
            [{'articulo': self.art, 'cantidad': 3, 'precio_unitario': '2000.00'}]
        )
        confirmar_comprobante(pedido)

        # Validaciones del Paso 1:
        # El stock real debe seguir intacto (10), pero el comprometido debe subir a 3
        self.assertEqual(self._get_cantidad_stock('REAL'), Decimal('10'))
        self.assertEqual(self._get_cantidad_stock('RSRV'), Decimal('3'))
        # No debe haber impacto financiero aún porque no es una factura
        self.assertEqual(CuentaCorrienteService._saldo_al_cierre(self.cliente, hasta=timezone.localdate()),
                         Decimal('0'))

        # ──────────────────────────────────────────────────────────────────────
        # PASO 2: Emisión del Remito (Despacho físico de mercadería)
        # ──────────────────────────────────────────────────────────────────────
        remito = make_comprobante(
            self.cliente, self.tipo_remito, self.deposito,
            [{'articulo': self.art, 'cantidad': 3, 'precio_unitario': '2000.00'}]
        )
        # Vinculamos el remito al pedido origen para simular el descompromiso automático
        remito.comprobantes_asociados.add(pedido)
        remito.save()
        confirmar_comprobante(remito)

        # Validaciones del Paso 2:
        # El stock real debió bajar a 7 (10 - 3). El stock RSRV debió liberarse (volver a 0).
        self.assertEqual(self._get_cantidad_stock('REAL'), Decimal('7'))
        self.assertEqual(self._get_cantidad_stock('RSRV'), Decimal('0'))
        # Sigue sin haber deuda contable en la Cta. Cte.
        self.assertEqual(CuentaCorrienteService._saldo_al_cierre(self.cliente, hasta=timezone.localdate()),
                         Decimal('0'))

        # ──────────────────────────────────────────────────────────────────────
        # PASO 3: Facturación del Remito (Impacto Financiero)
        # ──────────────────────────────────────────────────────────────────────
        factura = make_comprobante(
            self.cliente, self.tipo_factura, self.deposito,
            [{'articulo': self.art, 'cantidad': 3, 'precio_unitario': '2000.00'}]
        )
        # Vinculamos al remito previo para dejar trazabilidad
        factura.comprobantes_asociados.add(remito)
        factura.save()
        confirmar_comprobante(factura)

        # Validaciones del Paso 3 (El Escudo Protector que programamos hoy):
        # El stock real se TIENE que mantener en 7. La factura no debe volver a descontarlo.
        self.assertEqual(self._get_cantidad_stock('REAL'), Decimal('7'))

        # Validación de Cuenta Corriente (Capa 1):
        # Ahora sí, el saldo de la Cta. Cte. del cliente debe incrementarse en $6000 (3 unidades * $2000)
        saldo_cliente = CuentaCorrienteService._saldo_al_cierre(self.cliente, hasta=timezone.localdate())
        self.assertEqual(saldo_cliente, Decimal('6000.00'))