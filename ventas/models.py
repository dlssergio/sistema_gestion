# ventas/models.py (VERSIÓN COMPLETA: ASOCIADOS MÚLTIPLES + RECIBOS + DISEÑOS)

from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from djmoney.money import Money
from django.conf import settings
from finanzas.models import TipoValor, CuentaFondo, Cheque, MovimientoFondo, Banco, Tarjeta, PlanTarjeta, PlanCuota
from inventario.services import StockManager


def get_default_moneda_pk():
    from parametros.models import Moneda
    moneda, _ = Moneda.objects.get_or_create(
        es_base=True,
        defaults={'nombre': 'Peso Argentino', 'simbolo': 'ARS', 'cotizacion': 1.00}
    )
    return moneda.pk


# --- CLIENTE, COMPROBANTES, LISTAS ---

class Cliente(models.Model):
    entidad = models.OneToOneField('entidades.Entidad', on_delete=models.CASCADE, primary_key=True)
    price_list = models.ForeignKey(
        'PriceList',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Lista de Precios Asignada"
    )
    permite_cta_cte = models.BooleanField(default=False, verbose_name="Habilitar Cuenta Corriente",
                                          help_text="Si está desactivado, este cliente solo puede operar de CONTADO.")
    limite_credito = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Límite de Crédito")

    def __str__(self):
        return self.entidad.razon_social

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"


class ComprobanteVenta(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        CONFIRMADO = 'CN', 'Confirmado'
        ANULADO = 'AN', 'Anulado'

    class CondicionVenta(models.TextChoices):
        CONTADO = 'CO', 'Contado'
        CTA_CTE = 'CC', 'Cuenta Corriente'

    class ConceptoNC(models.TextChoices):
        DEVOLUCION = 'DEV', 'Devolución de Mercadería (Mueve Stock)'
        FINANCIERO = 'FIN', 'Ajuste Financiero / Descuento (No Mueve Stock)'
        ANULACION = 'ANU', 'Anulación de Operación (Mueve Stock)'

    serie = models.ForeignKey('parametros.SerieDocumento', on_delete=models.PROTECT,
                              null=True, blank=True, verbose_name="Serie / Talonario")
    tipo_comprobante = models.ForeignKey('parametros.TipoComprobante', on_delete=models.PROTECT,
                                         null=True, blank=True, verbose_name="Tipo de Comprobante")
    numero = models.PositiveIntegerField(blank=True, null=True, verbose_name="Número")
    letra = models.CharField(max_length=1, editable=False)
    punto_venta = models.PositiveIntegerField(default=1, verbose_name="Punto de Venta")
    cliente = models.ForeignKey('Cliente', on_delete=models.PROTECT, verbose_name="Cliente")
    fecha = models.DateField(default=timezone.now, verbose_name="Fecha del Comprobante")
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR)
    condicion_venta = models.CharField(max_length=2, choices=CondicionVenta.choices, default=CondicionVenta.CONTADO)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    impuestos = models.JSONField(default=dict, editable=False)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    deposito = models.ForeignKey('inventario.Deposito', on_delete=models.PROTECT, null=True, blank=True)
    stock_aplicado = models.BooleanField(default=False, editable=False)
    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones / Notas")

    comprobantes_asociados = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='notas_asociadas',
        verbose_name="Comprobantes de Origen"
    )

    concepto_nota_credito = models.CharField(
        max_length=3,
        choices=ConceptoNC.choices,
        null=True,
        blank=True,
        verbose_name="Motivo de Nota de Crédito",
        help_text="Define si se debe reintegrar el stock o solo ajustar saldo."
    )

    # --- CAMPOS AFIP ---
    cae = models.CharField(max_length=50, blank=True, null=True, verbose_name="CAE")
    vto_cae = models.DateField(blank=True, null=True, verbose_name="Vencimiento CAE")
    afip_resultado = models.CharField(max_length=2, blank=True, null=True)
    afip_observaciones = models.TextField(blank=True, null=True)
    afip_error = models.TextField(blank=True, null=True, verbose_name="Error AFIP")
    afip_xml_request = models.TextField(blank=True, null=True, editable=False)
    afip_xml_response = models.TextField(blank=True, null=True, editable=False)

    referencia_externa = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Ref. Comprobante Externo",
        help_text="Formato: PuntoVenta-Numero (Ej: 1-123). Usar solo si no se selecciona un comprobante asociado del sistema."
    )
    periodo_asociado_inicio = models.DateField(null=True, blank=True, verbose_name="Periodo Asoc. Desde")
    periodo_asociado_fin = models.DateField(null=True, blank=True, verbose_name="Periodo Asoc. Hasta")

    def debe_mover_stock(self):
        if self.estado != self.Estado.CONFIRMADO:
            return False
        if not self.tipo_comprobante:
            return False
        if self.tipo_comprobante.codigo_afip in ['003', '008', '013']:
            return self.concepto_nota_credito in [self.ConceptoNC.DEVOLUCION, self.ConceptoNC.ANULACION]
        return self.tipo_comprobante.mueve_stock

    def es_electronica(self):
        return self.serie and self.serie.tipo_comprobante.codigo_afip is not None

    @property
    def numero_completo(self):
        return f"{self.letra} {self.punto_venta:05d}-{self.numero or 0:08d}"

    @property
    def estado_pago(self):
        if self.saldo_pendiente == 0: return "PAGADO"
        if self.saldo_pendiente == self.total: return "IMPAGO"
        return "PARCIAL"

    def clean(self):
        if self.condicion_venta == self.CondicionVenta.CTA_CTE and not self.cliente.permite_cta_cte:
            raise ValidationError(
                f"El cliente {self.cliente} NO está habilitado para operar en Cuenta Corriente. Debe ser CONTADO.")

    def save(self, *args, **kwargs):
        if self.serie:
            self.tipo_comprobante = self.serie.tipo_comprobante
            self.letra = self.serie.tipo_comprobante.letra
            self.punto_venta = self.serie.punto_venta
            if not self.deposito and self.serie.deposito_defecto:
                self.deposito = self.serie.deposito_defecto
            if not self.serie.es_manual and not self.numero:
                from parametros.models import SerieDocumento
                with transaction.atomic():
                    serie_lock = SerieDocumento.objects.select_for_update().get(pk=self.serie.pk)
                    self.numero = serie_lock.ultimo_numero + 1
                    serie_lock.ultimo_numero = self.numero
                    serie_lock.save()
        if self.tipo_comprobante and not self.letra:
            self.letra = self.tipo_comprobante.letra

        # Asignar depósito por defecto si no tiene
        if not self.deposito_id and self.deposito is None:
            from inventario.models import Deposito
            deposito_principal = Deposito.objects.filter(es_principal=True).first()
            if deposito_principal:
                self.deposito = deposito_principal

        super().save(*args, **kwargs)

    def __str__(self):
        fecha_str = self.fecha.strftime('%d/%m/%Y') if self.fecha else 'S/F'
        tipo = self.tipo_comprobante.nombre if self.tipo_comprobante else 'Venta'
        return f"{tipo} {self.numero_completo} ({fecha_str}) - $ {self.total:,.2f}"

    class Meta:
        verbose_name = "Comprobante de Venta"
        verbose_name_plural = "Comprobantes de Venta"


class ComprobanteVentaItem(models.Model):
    comprobante = models.ForeignKey(ComprobanteVenta, related_name='items', on_delete=models.CASCADE)
    articulo = models.ForeignKey('inventario.Articulo', on_delete=models.PROTECT, verbose_name="Artículo")
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)
    precio_unitario_original = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Precio Unitario")

    @property
    def subtotal(self):
        return (self.cantidad or Decimal(0)) * (self.precio_unitario_original or Decimal(0))

    def __str__(self):
        return f"{self.cantidad} x {self.articulo.descripcion}"

    # --- VALIDACIÓN PREVENTIVA DE STOCK ---
    def clean(self):
        super().clean()
        # Si el comprobante padre existe en memoria y se está confirmando
        if self.comprobante and hasattr(self.comprobante, 'estado') and hasattr(self.comprobante, 'tipo_comprobante'):
            if self.comprobante.estado == ComprobanteVenta.Estado.CONFIRMADO:
                tipo = self.comprobante.tipo_comprobante
                deposito = self.comprobante.deposito

                # Solo validamos si mueve stock físico (REAL)
                if tipo and tipo.mueve_stock and tipo.afecta_stock_fisico and deposito:

                    # Verificamos si se permite negativo
                    puede_negativo = self.articulo.permite_stock_negativo or deposito.permite_stock_negativo

                    if not puede_negativo:
                        # Consultamos saldo actual (sin bloquear DB)
                        saldo_actual = StockManager.obtener_saldo_actual(self.articulo, deposito, 'REAL')

                        # Si estamos editando un item existente, sumamos su cantidad anterior al saldo
                        # para no contar doble la reserva.
                        if self.pk:
                            try:
                                old_item = ComprobanteVentaItem.objects.get(pk=self.pk)
                                saldo_actual += old_item.cantidad
                            except ComprobanteVentaItem.DoesNotExist:
                                pass

                        if saldo_actual < self.cantidad:
                            # Lanzamos el error que Django Admin debería mostrar en el campo
                            raise ValidationError(
                                f"Stock insuficiente en {deposito}. Disponible: {saldo_actual}. "
                                f"Solicitado: {self.cantidad}."
                            )


class PriceList(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nombre")
    code = models.CharField(max_length=20, unique=True, verbose_name="Código")
    valid_from = models.DateField(verbose_name="Válido Desde", null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True, verbose_name="Válido Hasta")
    is_default = models.BooleanField(default=False, verbose_name="¿Es la lista por defecto?")
    discount_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        verbose_name="Descuento general (%)"
    )
    formula = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Fórmula de Precio Personalizada",
        help_text="Ej: 'costo * 1.5 + 50'. Usa 'costo' como variable. Se aplica si no hay precio específico."
    )

    class Meta:
        verbose_name = "Lista de Precios de Venta"
        verbose_name_plural = "Listas de Precios de Venta"

    def __str__(self):
        return self.name


class ProductPrice(models.Model):
    """
    Define el precio de un producto para una lista de precios específica,
    con soporte para precios escalonados por cantidad.
    """
    product = models.ForeignKey('inventario.Articulo', on_delete=models.CASCADE, related_name='sales_prices')
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name='product_prices')
    price_monto = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Monto del Precio")
    price_moneda = models.ForeignKey('parametros.Moneda', on_delete=models.PROTECT, default=get_default_moneda_pk)
    min_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1, verbose_name="Cantidad Mínima")
    max_quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True,
                                       verbose_name="Cantidad Máxima")

    @property
    def price(self): return Money(self.price_monto, self.price_moneda.simbolo)

    class Meta:
        unique_together = ['product', 'price_list', 'min_quantity']
        ordering = ['min_quantity']
        verbose_name = "Precio de Producto"
        verbose_name_plural = "Precios de Productos"


# --- RECIBOS ---
class Recibo(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        CONFIRMADO = 'CN', 'Confirmado'
        ANULADO = 'AN', 'Anulado'

    class Origen(models.TextChoices):
        COBRANZA = 'CTA', 'Cobranza Cuenta Corriente'
        CONTADO = 'CON', 'Venta Contado'
        DEVOLUCION = 'DEV', 'Devolución (Salida de Dinero)'

    serie = models.ForeignKey('parametros.SerieDocumento', on_delete=models.PROTECT,
                              null=True, blank=True)
    numero = models.PositiveIntegerField(blank=True, null=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    fecha = models.DateField(default=timezone.now)
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR)
    monto_total = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    finanzas_aplicadas = models.BooleanField(default=False, editable=False)
    origen = models.CharField(max_length=3, choices=Origen.choices, default=Origen.COBRANZA,
                              verbose_name="Origen de Fondos")

    def save(self, *args, **kwargs):
        if self.serie and not self.numero and not self.serie.es_manual:
            from parametros.models import SerieDocumento
            with transaction.atomic():
                serie_lock = SerieDocumento.objects.select_for_update().get(pk=self.serie.pk)
                siguiente = serie_lock.ultimo_numero + 1
                self.numero = siguiente
                serie_lock.ultimo_numero = siguiente
                serie_lock.save()
        super().save(*args, **kwargs)

    def aplicar_finanzas(self):
        if self.estado != self.Estado.CONFIRMADO or self.finanzas_aplicadas: return

        # Validación Balanceo
        total_valores = sum(v.monto for v in self.valores.all())
        total_imputado = sum(i.monto_imputado for i in self.imputaciones.all())
        # Permitimos pequeña diferencia por redondeo
        if abs(total_imputado - total_valores) > Decimal('0.05'):
            raise ValidationError(f"Desbalance: Valores ${total_valores} vs Imputado ${total_imputado}.")
        if not self.valores.exists():
            raise ValidationError("Debe ingresar valores de pago.")

        es_salida = (self.origen == self.Origen.DEVOLUCION)

        with transaction.atomic():
            # A. Movimiento de Valores
            for valor in self.valores.all():
                nuevo_cheque = None
                if not es_salida and valor.tipo.es_cheque and not valor.cheque_tercero:
                    nuevo_cheque = Cheque.objects.create(
                        numero=valor.referencia, banco=valor.banco_origen, monto=valor.monto,
                        moneda=valor.destino.moneda, fecha_emision=self.fecha,
                        fecha_pago=valor.fecha_cobro or self.fecha, tipo_cheque='FIS',
                        origen=Cheque.Origen.TERCERO, estado=Cheque.Estado.EN_CARTERA,
                        cuit_librador=valor.cuit_librador, nombre_librador=f"Cliente: {self.cliente}"
                    )

                MovimientoFondo.objects.create(
                    fecha=self.fecha,
                    cuenta=valor.destino,
                    tipo_movimiento=MovimientoFondo.TipoMov.EGRESO if es_salida else MovimientoFondo.TipoMov.INGRESO,
                    tipo_valor=valor.tipo,
                    monto_egreso=valor.monto if es_salida else 0,
                    monto_ingreso=0 if es_salida else valor.monto,
                    concepto=f"{'Devolución' if es_salida else 'Cobro'} Recibo #{self.numero} - {self.cliente}",
                    usuario=self.creado_por,
                    cheque=nuevo_cheque or valor.cheque_tercero
                )

                if es_salida:
                    valor.destino.saldo_monto -= valor.monto
                else:
                    valor.destino.saldo_monto += valor.monto
                valor.destino.save()

            # B. Bajar Deuda (Imputación)
            for imputacion in self.imputaciones.all():
                comp = imputacion.comprobante
                comp.saldo_pendiente -= imputacion.monto_imputado
                if comp.saldo_pendiente < 0: comp.saldo_pendiente = 0
                comp.save()

            self.finanzas_aplicadas = True
            self.save(update_fields=['finanzas_aplicadas'])

    def revertir_finanzas(self):
        if not self.finanzas_aplicadas: return
        es_salida = (self.origen == self.Origen.DEVOLUCION)
        imputaciones = list(self.imputaciones.all())
        valores = list(self.valores.all())

        with transaction.atomic():
            for imputacion in imputaciones:
                comp = imputacion.comprobante
                comp.saldo_pendiente += imputacion.monto_imputado
                comp.save()

            for valor in valores:
                if es_salida:
                    valor.destino.saldo_monto += valor.monto
                else:
                    valor.destino.saldo_monto -= valor.monto

                valor.destino.save()

                if valor.tipo.es_cheque:
                    Cheque.objects.filter(numero=valor.referencia, cuit_librador=valor.cuit_librador).update(
                        estado=Cheque.Estado.ANULADO)

            self.finanzas_aplicadas = False
            self.save(update_fields=['finanzas_aplicadas'])

    def __str__(self):
        return f"Recibo X {self.numero or '?'} - {self.cliente}"

    class Meta:
        verbose_name = "Recibo de Cobro"
        verbose_name_plural = "Recibos de Cobro"


class ReciboImputacion(models.Model):
    recibo = models.ForeignKey(Recibo, related_name='imputaciones', on_delete=models.CASCADE)
    comprobante = models.ForeignKey(ComprobanteVenta, on_delete=models.PROTECT)
    monto_imputado = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self): return f"Pago a {self.comprobante}"


class ReciboValor(models.Model):
    recibo = models.ForeignKey(Recibo, related_name='valores', on_delete=models.CASCADE)
    tipo = models.ForeignKey(TipoValor, on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    # Destino de los fondos (Caja o Banco)
    destino = models.ForeignKey(CuentaFondo, on_delete=models.PROTECT, verbose_name="Caja/Cuenta Destino")
    observaciones = models.CharField(max_length=150, blank=True,
                                     help_text="Detalle: N° Cheque, Banco, Lote Tarjeta, etc.")
    cheque_tercero = models.ForeignKey(Cheque, on_delete=models.SET_NULL, null=True, blank=True)
    banco_origen = models.ForeignKey(Banco, on_delete=models.SET_NULL, null=True, blank=True)
    referencia = models.CharField(max_length=100, blank=True)
    fecha_cobro = models.DateField(null=True, blank=True)
    cuit_librador = models.CharField(max_length=11, blank=True)

    def __str__(self): return f"{self.tipo} ${self.monto}"


class ComprobantePendienteCAE(ComprobanteVenta):
    class Meta:
        proxy = True
        verbose_name = "⚠️ Bandeja Factura Electrónica"
        verbose_name_plural = "⚠️ Bandeja Factura Electrónica (Pendientes)"


class DisenoImpresion(models.Model):
    nombre = models.CharField(max_length=50, verbose_name="Nombre del Diseño")
    archivo_template = models.CharField(
        max_length=100,
        default="ventas/pdf/factura_premium.html",
        verbose_name="Ruta del Template PDF",
        help_text="Ej: ventas/pdf/factura_premium.html"
    )
    contenido_html = models.TextField(
        verbose_name="Código HTML (Base de Datos)",
        blank=True,
        null=True,
        help_text="Si pegas código aquí, el sistema lo usará PRIORITARIAMENTE sobre el archivo físico."
    )
    asunto_email = models.CharField(
        max_length=200,
        blank=True, null=True,
        verbose_name="Asunto del Email",
        help_text="Ej: Factura {numero} de {empresa}"
    )
    cuerpo_email = models.TextField(
        verbose_name="Cuerpo del Email",
        blank=True, null=True,
        help_text="Variables disponibles: {cliente}, {numero}, {fecha}, {empresa}, {vencimiento}. Salto de línea funciona."
    )

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Diseño de Impresión y Email"
        verbose_name_plural = "Diseños de Impresión y Email"


class ComprobanteCobroItem(models.Model):
    """
    Permite cargar múltiples formas de pago en una sola factura.
    """
    comprobante = models.ForeignKey('ComprobanteVenta', on_delete=models.CASCADE, related_name='cobros_asociados')

    tipo_valor = models.ForeignKey(TipoValor, on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=14, decimal_places=2, help_text="Monto a cobrar (El sistema sumará el recargo si corresponde)")

    # Destino de fondos
    destino = models.ForeignKey(CuentaFondo, on_delete=models.PROTECT, limit_choices_to={'activa': True})

    observaciones = models.CharField(max_length=100, blank=True, help_text="Detalle opcional")

    # --- CAMBIO CLAVE: ELEGIR LA CUOTA ESPECÍFICA ---
    # Antes: tarjeta_plan (PlanTarjeta) -> Solo elegía la marca
    # Ahora: opcion_cuota (PlanCuota) -> Elige "Visa Galicia - 3 Cuotas (1.15)"
    opcion_cuota = models.ForeignKey(PlanCuota, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Plan y Cuotas")

    tarjeta_lote = models.CharField(max_length=20, blank=True, verbose_name="Lote")
    tarjeta_cupon = models.CharField(max_length=50, blank=True, verbose_name="Cupón")

    # Este campo es opcional, si el plan ya define las cuotas, no hace falta.
    # Pero si quieres permitir editarlo manual, déjalo. Si no, bórralo.
    # Por compatibilidad con el admin, lo dejo, pero lo ideal es sacarlo si usas Plan.
    # Si lo borras aquí, bórralo del admin también.

    def __str__(self):
        return f"{self.tipo_valor}: ${self.monto}"