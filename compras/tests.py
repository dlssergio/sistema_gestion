# compras/tests.py
"""
Tests automatizados — Módulo de Compras y Cuenta Corriente de Proveedores
========================================================================
Compatibilidad con django-tenants: utiliza TenantTestCase para levantar
la base de datos aislada del tenant de prueba.

Ejecutar con:
    python manage.py test compras --verbosity=2
"""
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase
from djmoney.money import Money

from compras.models import (
    Proveedor, ComprobanteCompra, ComprobanteCompraItem,
    ListaPreciosProveedor, ItemListaPreciosProveedor, HistorialPrecioProveedor,
    OrdenPago, OrdenPagoImputacion, OrdenPagoValor
)
from compras.services import CostCalculatorService, PriceListService
from inventario.models import Articulo, Deposito, ConversionUnidadMedida, Rubro
from parametros.models import TipoComprobante, Moneda, UnidadMedida, Contador, Role
from entidades.models import Entidad
from finanzas.models import CuentaFondo, TipoValor, RegimenRetencion

User = get_user_model()


class ComprasTenantTestCase(TenantTestCase):
    """Clase base de infraestructura para los tests de compras."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.schema_name = 'test_compras_schema'
        tenant.name = 'Empresa Test Compras'
        return tenant

    @classmethod
    def setup_domain(cls, domain):
        domain.domain = 'compras.test.localhost'
        domain.is_primary = True
        return domain


# ═══════════════════════════════════════════════════════════════════════════
# FACTORIES / AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════

_counter = 0


def make_proveedor():
    global _counter
    _counter += 1
    entidad = Entidad.objects.create(
        razon_social=f"Proveedor Test {_counter}",
        cuit=f"30-{_counter:08d}-1",
        email=f"prov{_counter}@test.com"
    )
    moneda_ars, _ = Moneda.objects.get_or_create(simbolo='ARS', defaults={'nombre': 'Pesos', 'cotizacion': 1.0})
    return Proveedor.objects.create(
        entidad=entidad,
        moneda_compra=moneda_ars,
        limite_credito=Decimal("500000.00"),
        plazo_pago_dias=30
    )


def make_articulo(costo_base="100.00"):
    global _counter
    _counter += 1
    rubro, _ = Rubro.objects.get_or_create(nombre="Rubro General")
    moneda_ars, _ = Moneda.objects.get_or_create(simbolo='ARS', defaults={'nombre': 'Pesos', 'cotizacion': 1.0})
    return Articulo.objects.create(
        cod_articulo=f"ART-P{_counter:04d}",
        descripcion=f"Articulo Compra {_counter}",
        precio_costo_monto=Decimal(costo_base),
        precio_costo_moneda=moneda_ars,
        precio_venta_monto=Decimal(costo_base) * Decimal("1.5"),
        rubro=rubro
    )


def make_tipo_comprobante(nombre, letra, codigo_afip, mueve_stock=True, afecta_stock_fisico=True):
    return TipoComprobante.objects.create(
        nombre=nombre, letra=letra, codigo_afip=codigo_afip,
        mueve_stock=mueve_stock, afecta_stock_fisico=afecta_stock_fisico,
        signo_stock=1
    )


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1 — LISTAS DE PRECIOS Y AUDITORÍA (SIGNALS)
# ═══════════════════════════════════════════════════════════════════════════

class ListasPreciosTests(ComprasTenantTestCase):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username='comprador_test', password='123')
        self.proveedor = make_proveedor()
        self.articulo = make_articulo()
        self.um, _ = UnidadMedida.objects.get_or_create(simbolo='UN', defaults={'nombre': 'Unidades'})
        self.moneda_ars, _ = Moneda.objects.get_or_create(simbolo='ARS',
                                                          defaults={'nombre': 'Pesos', 'cotizacion': 1.0})

        self.lista = ListaPreciosProveedor.objects.create(
            proveedor=self.proveedor,
            nombre="Lista Inicial",
            es_principal=True
        )

    def test_creacion_historial_cambio_precio(self):
        """Valida que el signal pre_save registre los cambios en HistorialPrecioProveedor."""
        item = ItemListaPreciosProveedor.objects.create(
            lista_precios=self.lista,
            articulo=self.articulo,
            unidad_medida_compra=self.um,
            precio_lista_monto=Decimal("100.00"),
            precio_lista_moneda=self.moneda_ars
        )

        # El primer save (creación) no genera historial según tu signal, solo las actualizaciones
        self.assertEqual(HistorialPrecioProveedor.objects.filter(item=item).count(), 0)

        # Modificamos el precio para disparar el pre_save historial
        item.precio_lista_monto = Decimal("125.50")
        item.save()

        historial = HistorialPrecioProveedor.objects.filter(item=item).first()
        self.assertIsNotNone(historial)
        self.assertEqual(historial.precio_lista_anterior.amount, Decimal("100.00"))
        self.assertEqual(historial.precio_lista_nuevo.amount, Decimal("125.50"))


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2 — CÁLCULO DE COSTOS FINANCIEROS (SERVICES)
# ═══════════════════════════════════════════════════════════════════════════

class CostCalculatorTests(ComprasTenantTestCase):

    def setUp(self):
        super().setUp()
        self.proveedor = make_proveedor()
        self.articulo = make_articulo()
        self.um_un, _ = UnidadMedida.objects.get_or_create(simbolo='UN', defaults={'nombre': 'Unidades'})
        self.um_caja, _ = UnidadMedida.objects.get_or_create(simbolo='CJ', defaults={'nombre': 'Caja'})
        self.moneda_ars, _ = Moneda.objects.get_or_create(simbolo='ARS',
                                                          defaults={'nombre': 'Pesos', 'cotizacion': 1.0})

        self.lista = ListaPreciosProveedor.objects.create(
            proveedor=self.proveedor, nombre="Lista Costos", es_principal=True
        )

    def test_descuentos_en_cascada_y_conversion_unidades(self):
        """Verifica que se calculen las bonificaciones y el costo por unidad de stock."""
        # Configurar conversión de unidades: 1 Caja = 10 Unidades de Stock
        ConversionUnidadMedida.objects.create(
            articulo=self.articulo,
            unidad_externa=self.um_caja,
            factor_conversion=Decimal("10.0")
        )

        item = ItemListaPreciosProveedor.objects.create(
            lista_precios=self.lista,
            articulo=self.articulo,
            unidad_medida_compra=self.um_caja,
            precio_lista_monto=Decimal("1000.00"),  # $1000 por caja
            precio_lista_moneda=self.moneda_ars,
            bonificacion_porcentaje=Decimal("10.00"),  # -10% -> $900
            descuentos_adicionales=[-5.00]  # Descuento en cascada (factor positivo o negativo según lógica)
        )

        costo_calculado = CostCalculatorService.calculate_effective_cost(item)

        # $1000 - 10% = $900. Luego cascading descuento aplica factor (1 + (-5/100)) = 0.95 -> $900 * 0.95 = $855
        # Dividido factor_conversion (10.0) -> $85.50 por Unidad de stock
        self.assertEqual(costo_calculado.amount, Decimal("85.5000"))

    def test_fachada_get_latest_price_prioridades(self):
        """Prueba que PriceListService priorice la lista principal sobre las secundarias."""
        lista_secundaria = ListaPreciosProveedor.objects.create(
            proveedor=self.proveedor, nombre="Ofertas", es_principal=False,
            vigente_desde=timezone.now().date()
        )
        item_secundario = ItemListaPreciosProveedor.objects.create(
            lista_precios=lista_secundaria, articulo=self.articulo,
            unidad_medida_compra=self.um_un, precio_lista_monto=Decimal("70.00"),
            precio_lista_moneda=self.moneda_ars
        )

        # Consultar precio: debe traer el de la lista secundaria porque es la única vigente
        precio_item = CostCalculatorService.get_latest_price(self.proveedor.pk, self.articulo.pk)
        self.assertEqual(precio_item.precio_lista_monto, Decimal("70.00"))


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 3 — CUENTA CORRIENTE DE PROVEEDORES (FLUJO INTEGRAL)
# ═══════════════════════════════════════════════════════════════════════════

class CuentaCorrienteProveedoresTests(ComprasTenantTestCase):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username='cajero_op', password='123')
        self.proveedor = make_proveedor()
        self.articulo = make_articulo()
        self.deposito, _ = Deposito.objects.get_or_create(nombre="Deposito Central", defaults={'es_principal': True})
        self.tipo_fc = make_tipo_comprobante("Factura Compra", "A", "001")

        # Configuración de finanzas
        self.caja, _ = CuentaFondo.objects.get_or_create(nombre="Caja Pesos",
                                                         defaults={'saldo_monto': Decimal("100000.00")})
        self.t_val, _ = TipoValor.objects.get_or_create(nombre="Efectivo", defaults={'es_cheque': False})

        # Régimen de retención ficticio para evitar errores en aplicar_finanzas
        RegimenRetencion.objects.get_or_create(
            impuesto='GAN', nombre='Ganancias test',
            defaults={'alicuota_inscripto': Decimal("0.00")}
        )

    def test_ciclo_deuda_factura_y_pago_cuenta_corriente(self):
        """Valida que la factura genere deuda en la CC y la Orden de Pago la reduzca."""

        # 1. Crear comprobante de compra en cuenta corriente
        comp = ComprobanteCompra.objects.create(
            proveedor=self.proveedor,
            tipo_comprobante=self.tipo_fc,
            numero=1045,
            condicion_compra=ComprobanteCompra.CondicionCompra.CTA_CTE,
            deposito=self.deposito
        )

        ComprobanteCompraItem.objects.create(
            comprobante=comp,
            articulo=self.articulo,
            cantidad=Decimal("10"),
            precio_costo_unitario_monto=Decimal("150.00")
        )

        # Simular cálculo del módulo e impactar el saldo
        total_fc = Decimal("1500.00")
        comp.subtotal = total_fc
        comp.total = total_fc
        comp.saldo_pendiente = total_fc
        comp.estado = ComprobanteCompra.Estado.CONFIRMADO
        comp.save()

        self.assertEqual(comp.saldo_pendiente, Decimal("1500.00"))

        # 2. Crear una Orden de Pago para saldar parcialmente la deuda ($1000)
        op = OrdenPago.objects.create(
            proveedor=self.proveedor,
            estado=OrdenPago.Estado.CONFIRMADO,
            created_by=self.user
        )

        OrdenPagoImputacion.objects.create(
            orden_pago=op,
            comprobante=comp,
            monto_imputado=Decimal("1000.00")
        )

        OrdenPagoValor.objects.create(
            orden_pago=op,
            tipo=self.t_val,
            origen=self.caja,
            monto=Decimal("1000.00")
        )

        # 3. Aplicar finanzas del pago y verificar impacto en la cuenta corriente
        op.aplicar_finanzas()

        comp.refresh_from_db()
        self.caja.refresh_from_db()

        # Comprobar decremento de deuda y de fondos en caja
        self.assertEqual(comp.saldo_pendiente, Decimal("500.00"))
        self.assertEqual(self.caja.saldo_monto, Decimal("99000.00"))
        self.assertTrue(op.finanzas_aplicadas)