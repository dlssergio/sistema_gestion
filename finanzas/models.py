# finanzas/models.py

from django.db import models, transaction
from django.utils import timezone
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from djmoney.models.fields import MoneyField
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from parametros.models import Moneda, get_default_moneda_pk


# --- 1. CLASIFICACIÓN DE GASTOS/INGRESOS ---

class CentroCosto(models.Model):
    """
    Permite imputar movimientos a áreas específicas (Marketing, RRHH, Obra X).
    Clave para reportes de rentabilidad reales.
    """
    nombre = models.CharField(max_length=100, unique=True)
    codigo = models.CharField(max_length=20, blank=True, help_text="Código interno (ej: 1.1.0)")
    activo = models.BooleanField(default=True)

    def __str__(self): return f"{self.codigo} - {self.nombre}" if self.codigo else self.nombre

    class Meta:
        verbose_name = "Centro de Costo"
        verbose_name_plural = "Centros de Costo"


# --- 2. CONFIGURACIÓN DE VALORES ---

class TipoValor(models.Model):
    """Define los métodos de pago/cobro."""
    nombre = models.CharField(max_length=50, unique=True)
    requiere_banco = models.BooleanField(default=False, help_text="Pide seleccionar banco (Transferencia).")
    es_cheque = models.BooleanField(default=False, help_text="Habilita la gestión de cheques.")
    es_tarjeta = models.BooleanField(default=False, help_text="Habilita campos de tarjeta (Lote, Cupón).")
    es_retencion = models.BooleanField(default=False, help_text="Para certificados de retención IIBB/Ganancias.")

    def __str__(self): return self.nombre

    class Meta:
        verbose_name = "Tipo de Valor"
        verbose_name_plural = "Tipos de Valores"


class Banco(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    codigo_bcra = models.CharField(max_length=10, blank=True, verbose_name="Código BCRA")

    def __str__(self): return self.nombre

    class Meta:
        verbose_name = "Banco"
        verbose_name_plural = "Bancos"


# --- 3. CUENTAS DE FONDOS (CAJAS Y BANCOS) ---

class CuentaFondo(models.Model):
    class Tipo(models.TextChoices):
        EFECTIVO = 'EF', 'Caja / Efectivo'
        BANCO = 'BA', 'Cuenta Bancaria'
        VIRTUAL = 'VI', 'Billetera Virtual'
        RECAUDADORA = 'RE', 'Cuenta Recaudadora (Tarjetas)'

    nombre = models.CharField(max_length=100, help_text="Ej: Caja Principal, Banco Nación CC$")
    tipo = models.CharField(max_length=2, choices=Tipo.choices, default=Tipo.EFECTIVO)

    saldo_monto = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Saldo Actual")
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, default=get_default_moneda_pk)

    # Datos Bancarios
    banco = models.ForeignKey(Banco, on_delete=models.SET_NULL, null=True, blank=True)
    cbu = models.CharField(max_length=22, blank=True, verbose_name="CBU / CVU")
    alias = models.CharField(max_length=100, blank=True, verbose_name="Alias CBU")

    activa = models.BooleanField(default=True)

    def __str__(self): return f"{self.nombre} ({self.moneda.simbolo})"

    class Meta:
        verbose_name = "Cuenta de Fondos / Caja"
        verbose_name_plural = "Cuentas de Fondos / Cajas"


# --- 4. CHEQUES (FÍSICOS Y E-CHEQ) ---

class Cheque(models.Model):
    class Estado(models.TextChoices):
        EN_CARTERA = 'CA', 'En Cartera'
        DEPOSITADO = 'DE', 'Depositado (Acred. Pendiente)'
        COBRADO = 'CO', 'Cobrado / Acreditado'
        ENTREGADO = 'EN', 'Entregado a Tercero'  # (Pago a proveedor)
        RECHAZADO = 'RE', 'Rechazado'
        ANULADO = 'AN', 'Anulado'
        CUSTODIA = 'CU', 'En Custodia (Banco)'  # Específico para físicos

    class Origen(models.TextChoices):
        PROPIO = 'P', 'Propio (Emitido)'
        TERCERO = 'T', 'Tercero (Recibido)'

    class TipoCheque(models.TextChoices):
        FISICO = 'FIS', 'Físico (Papel)'
        ECHEQ = 'ECH', 'E-Cheq (Electrónico)'

    origen = models.CharField(max_length=1, choices=Origen.choices, default=Origen.TERCERO)
    tipo_cheque = models.CharField(max_length=3, choices=TipoCheque.choices, default=TipoCheque.FISICO,
                                   verbose_name="Formato")
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.EN_CARTERA)

    # Identificación
    numero = models.CharField(max_length=50, verbose_name="N° Cheque")
    referencia_bancaria = models.CharField(max_length=100, blank=True, null=True,
                                           help_text="ID de transacción del E-Cheq")
    banco = models.ForeignKey(Banco, on_delete=models.PROTECT, verbose_name="Banco Emisor")

    # Fechas
    fecha_emision = models.DateField()
    fecha_pago = models.DateField(verbose_name="Fecha de Pago / Vencimiento")

    # Montos
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, default=get_default_moneda_pk)

    # Datos del tercero (Librador o Endosante)
    cuit_librador = models.CharField(max_length=11, blank=True, verbose_name="CUIT Librador")
    nombre_librador = models.CharField(max_length=100, blank=True, verbose_name="Nombre Librador")

    observaciones = models.TextField(blank=True)

    def __str__(self):
        tipo = "E-Cheq" if self.tipo_cheque == 'ECH' else "Físico"
        origen = "Propio" if self.origen == 'P' else "3ro"
        return f"{tipo} {origen} #{self.numero} - ${self.monto}"


# --- 4.5 GESTIÓN AVANZADA DE TARJETAS (MODELO ERP) ---

class Tarjeta(models.Model):
    """
    Entidad financiera (Visa, Master, Amex).
    Se vincula a una cuenta contable transitoria (Cuenta Recaudadora).
    """
    nombre = models.CharField(max_length=50, unique=True)

    # SAP/Odoo Style: Cada tarjeta tiene su cuenta de "A cobrar"
    cuenta_contable = models.ForeignKey(
        CuentaFondo,
        on_delete=models.PROTECT,
        related_name='tarjetas_asociadas',
        help_text="Cuenta donde se acreditan provisoriamente los cupones (Ej: 'Visa a Cobrar').",
        limit_choices_to={'tipo': CuentaFondo.Tipo.RECAUDADORA},
        null=True,
        blank=True
    )

    def __str__(self): return self.nombre


class PlanTarjeta(models.Model):
    """
    MAESTRO: Define el acuerdo comercial.
    Ej: 'Ahora 12', 'Visa Galicia', 'Cuota Simple'.
    """
    tarjeta = models.ForeignKey(Tarjeta, on_delete=models.CASCADE, related_name='planes')
    nombre = models.CharField(max_length=100, help_text="Ej: Ahora 3, Visa Galicia")
    activo = models.BooleanField(default=True)

    def __str__(self): return f"{self.tarjeta} - {self.nombre}"


class PlanCuota(models.Model):
    """
    DETALLE: Las condiciones para X cantidad de cuotas dentro de un plan.
    """
    plan = models.ForeignKey(PlanTarjeta, on_delete=models.CASCADE, related_name='cuotas_detalle')
    cuotas = models.PositiveIntegerField()
    coeficiente = models.DecimalField(max_digits=6, decimal_places=4, default=1.0000,
                                      help_text="Coeficiente multiplicador (Ej: 1.20 para 20% interés)")
    tna = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name="TNA %", help_text="Costo financiero implícito")

    class Meta:
        ordering = ['cuotas']
        unique_together = ('plan', 'cuotas') # No puede haber dos veces "3 cuotas" en el mismo plan

    def __str__(self): return f"{self.cuotas} cuotas (Coef: {self.coeficiente})"


class LiquidacionTarjeta(models.Model):
    """
    Documento que refleja el resumen de pago de la procesadora (Prisma/Fiserv).
    Aquí se transforman los Cupones (Activo exigible) en Dinero en Banco (Activo líquido)
    menos los Gastos (Pérdida).
    """
    fecha_liquidacion = models.DateField(default=timezone.now)
    numero_liquidacion = models.CharField(max_length=50, verbose_name="N° Liquidación")
    tarjeta = models.ForeignKey(Tarjeta, on_delete=models.PROTECT)

    # Cuenta donde entra la plata real (Banco Galicia, etc)
    cuenta_banco = models.ForeignKey(
        CuentaFondo,
        on_delete=models.PROTECT,
        limit_choices_to={'tipo': CuentaFondo.Tipo.BANCO},
        verbose_name="Banco Destino"
    )

    # Totales (Se llenan al procesar)
    total_bruto = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Suma de cupones")
    total_descuentos = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                           help_text="Comisiones + Impuestos")
    total_neto = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                     help_text="Lo que realmente entró al banco")

    # Detalles de Gastos (Conceptos de Odoo/SAP)
    comision = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    retencion_iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    retencion_iibb = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    retencion_ganancias = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    otros_gastos = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    procesada = models.BooleanField(default=False)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def __str__(self): return f"Liq {self.tarjeta} #{self.numero_liquidacion}"

    def calcular_totales(self):
        # Sumar gastos manuales
        gastos = self.comision + self.retencion_iva + self.retencion_iibb + self.retencion_ganancias + self.otros_gastos
        # Sumar cupones vinculados
        bruto = sum(c.monto for c in self.cupones_asociados.all())

        self.total_bruto = bruto
        self.total_descuentos = gastos
        self.total_neto = bruto - gastos
        self.save()

    def confirmar_liquidacion(self):
        """
        Ejecuta el asiento contable (Movimientos de Fondo):
        1. Ingresa el NETO en Banco.
        2. Egresa el BRUTO de la Cuenta Puente (Recaudadora).
        3. Genera movimientos de GASTO por la diferencia.
        """
        if self.procesada: return

        with transaction.atomic():
            # A. Ingreso al Banco (NETO)
            tipo_val_transf, _ = TipoValor.objects.get_or_create(nombre="Transferencia Bancaria")

            MovimientoFondo.objects.create(
                fecha=self.fecha_liquidacion,
                cuenta=self.cuenta_banco,
                tipo_movimiento=MovimientoFondo.TipoMov.INGRESO,
                tipo_valor=tipo_val_transf,
                monto_ingreso=self.total_neto,
                concepto=f"Liq. {self.tarjeta} #{self.numero_liquidacion} (Acreditación)",
                usuario=self.creado_por
            )
            self.cuenta_banco.saldo_monto += self.total_neto
            self.cuenta_banco.save()

            # B. Egresos de la Cuenta Recaudadora (BRUTO y GASTOS)
            cuenta_puente = self.tarjeta.cuenta_contable
            tipo_val_tarjeta = TipoValor.objects.filter(es_tarjeta=True).first()

            # B1. Movimiento espejo del NETO que sale de la tarjeta
            MovimientoFondo.objects.create(
                fecha=self.fecha_liquidacion,
                cuenta=cuenta_puente,
                tipo_movimiento=MovimientoFondo.TipoMov.EGRESO,
                tipo_valor=tipo_val_tarjeta,
                monto_egreso=self.total_neto,
                concepto=f"Transferencia a Banco {self.cuenta_banco} (Liq #{self.numero_liquidacion})",
                usuario=self.creado_por
            )

            # B2. Movimientos de Gastos
            gastos_detalle = [
                (self.comision, "Comisión Bancaria"),
                (self.retencion_iva, "Retención IVA"),
                (self.retencion_iibb, "Retención IIBB"),
                (self.retencion_ganancias, "Retención Ganancias"),
                (self.otros_gastos, "Otros Gastos Liq.")
            ]

            total_gastos = Decimal(0)
            for monto, desc in gastos_detalle:
                if monto > 0:
                    MovimientoFondo.objects.create(
                        fecha=self.fecha_liquidacion,
                        cuenta=cuenta_puente,
                        tipo_movimiento=MovimientoFondo.TipoMov.EGRESO,
                        tipo_valor=tipo_val_tarjeta,
                        monto_egreso=monto,
                        concepto=f"{desc} - Liq. {self.tarjeta} #{self.numero_liquidacion}",
                        usuario=self.creado_por
                    )
                    total_gastos += monto

            # Actualizamos saldo cuenta puente
            cuenta_puente.saldo_monto -= (self.total_neto + total_gastos)
            cuenta_puente.save()

            # C. Marcar cupones como liquidados
            self.cupones_asociados.update(estado=CuponTarjeta.Estado.ACREDITADO)

            self.procesada = True
            self.save()


class CuponTarjeta(models.Model):
    """
    Representa el voucher/cupón físico o digital de una venta con tarjeta.
    No es dinero líquido hasta que el banco lo liquida.
    """

    class Estado(models.TextChoices):
        PENDIENTE = 'PE', 'Pendiente de Presentación'
        PRESENTADO = 'PR', 'Presentado (Cierre Lote)'
        LIQUIDADO = 'LI', 'Liquidado / En Banco'
        ACREDITADO = 'AC', 'Acreditado / Finalizado'
        RECHAZADO = 'RE', 'Rechazado / Contracargo'

    tarjeta = models.ForeignKey(Tarjeta, on_delete=models.PROTECT)
    lote = models.CharField(max_length=20, blank=True, help_text="N° de Lote de la terminal POS")
    cupon = models.CharField(max_length=50, verbose_name="N° Cupón/Ticket")
    cuotas = models.PositiveIntegerField(default=1)

    plan = models.ForeignKey(PlanTarjeta, on_delete=models.PROTECT, null=True, blank=True)

    monto = models.DecimalField(max_digits=14, decimal_places=2)
    fecha_operacion = models.DateField(default=timezone.now)
    fecha_acreditacion_estimada = models.DateField(null=True, blank=True)

    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.PENDIENTE)

    # Vinculación con la liquidación
    liquidacion = models.ForeignKey(LiquidacionTarjeta, on_delete=models.SET_NULL, null=True, blank=True, related_name='cupones_asociados')

    def __str__(self):
        return f"{self.tarjeta} Cupon:{self.cupon} (${self.monto})"


# --- 5. MOVIMIENTOS DE FONDOS (LIBRO DIARIO) ---

class MovimientoFondo(models.Model):
    class TipoMov(models.TextChoices):
        INGRESO = 'IN', 'Ingreso'
        EGRESO = 'EG', 'Egreso'
        TRANSFERENCIA = 'TR', 'Transferencia Interna'

    fecha = models.DateField(default=timezone.now)
    cuenta = models.ForeignKey(CuentaFondo, on_delete=models.PROTECT, related_name='movimientos')

    tipo_movimiento = models.CharField(max_length=2, choices=TipoMov.choices)
    tipo_valor = models.ForeignKey(TipoValor, on_delete=models.PROTECT, null=True, blank=True)

    # Vinculación con Cupón (NUEVO)
    cupon = models.ForeignKey(CuponTarjeta, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Cupón Tarjeta")

    # Montos
    monto_ingreso = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_egreso = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Referencias
    concepto = models.CharField(max_length=200, help_text="Ej: Cobro Factura F-0001, Pago Luz")

    # Enterprise Features
    centro_costo = models.ForeignKey(CentroCosto, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Centro de Costo")
    cheque = models.ForeignKey(Cheque, on_delete=models.SET_NULL, null=True, blank=True)

    # Conciliación Bancaria
    conciliado = models.BooleanField(default=False, help_text="Marcar si ya figura en el resumen bancario.")
    fecha_conciliacion = models.DateField(null=True, blank=True)

    # Auditoría
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    @property
    def saldo_movimiento(self):
        """Retorna el valor neto (positivo o negativo)"""
        return self.monto_ingreso - self.monto_egreso

    def save(self, *args, **kwargs):
        # Aquí irá luego la lógica de actualización de saldo de la cuenta
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Movimiento de Fondo"
        verbose_name_plural = "Movimientos de Fondos"
        ordering = ['-fecha', '-id']


# --- TRANSFERENCIAS INTERNAS (MOVIMIENTOS ENTRE CUENTAS) ---

class TransferenciaInterna(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        CONFIRMADO = 'CN', 'Confirmado'
        ANULADO = 'AN', 'Anulado'

    fecha = models.DateField(default=timezone.now)

    # Origen (De donde sale la plata)
    origen = models.ForeignKey(CuentaFondo, on_delete=models.PROTECT, related_name='transferencias_salida',
                               verbose_name="Cuenta Origen")

    # Destino (A donde entra la plata)
    destino = models.ForeignKey(CuentaFondo, on_delete=models.PROTECT, related_name='transferencias_entrada',
                                verbose_name="Cuenta Destino")

    monto = models.DecimalField(max_digits=14, decimal_places=2)

    # Opcional: Si es un depósito de efectivo o transferencia bancaria
    concepto = models.CharField(max_length=200, blank=True, default="Transferencia interna de fondos")
    referencia = models.CharField(max_length=100, blank=True, help_text="N° de Transacción Bancaria o Lote")

    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)

    # Bandera de control
    finanzas_aplicadas = models.BooleanField(default=False, editable=False)

    def clean(self):
        if self.origen == self.destino:
            raise ValidationError("La cuenta de origen y destino no pueden ser la misma.")
        if self.origen.moneda != self.destino.moneda:
            # Por ahora bloqueamos cambio de divisa directo para simplificar.
            # En el futuro se puede agregar campo 'cotizacion'.
            raise ValidationError("Las cuentas deben ser de la misma moneda.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def aplicar_transferencia(self):
        """Ejecuta el movimiento de fondos"""
        if self.estado != self.Estado.CONFIRMADO or self.finanzas_aplicadas: return

        with transaction.atomic():
            # 1. Obtener tipo de valor genérico (Efectivo o Transferencia)
            # Para simplificar, asumimos que si hay bancos involucrados es Transferencia, sino Efectivo.
            # Idealmente esto se selecciona, pero para automatizar:
            nombre_tipo = "Transferencia" if (
                    self.origen.tipo == CuentaFondo.Tipo.BANCO or self.destino.tipo == CuentaFondo.Tipo.BANCO) else "Efectivo"
            tipo_valor, _ = TipoValor.objects.get_or_create(nombre=nombre_tipo)

            # 2. Crear Egreso en Origen
            MovimientoFondo.objects.create(
                fecha=self.fecha,
                cuenta=self.origen,
                tipo_movimiento=MovimientoFondo.TipoMov.EGRESO,
                tipo_valor=tipo_valor,
                monto_egreso=self.monto,
                concepto=f"TRF Salida a {self.destino}: {self.concepto}",
                usuario=self.creado_por
            )
            self.origen.saldo_monto -= self.monto
            self.origen.save()

            # 3. Crear Ingreso en Destino
            MovimientoFondo.objects.create(
                fecha=self.fecha,
                cuenta=self.destino,
                tipo_movimiento=MovimientoFondo.TipoMov.INGRESO,
                tipo_valor=tipo_valor,
                monto_ingreso=self.monto,
                concepto=f"TRF Entrada desde {self.origen}: {self.concepto}",
                usuario=self.creado_por
            )
            self.destino.saldo_monto += self.monto
            self.destino.save()

            self.finanzas_aplicadas = True
            self.save(update_fields=['finanzas_aplicadas'])

    def revertir_transferencia(self):
        """Deshace la transferencia"""
        if not self.finanzas_aplicadas: return

        with transaction.atomic():
            # Devolver al Origen
            self.origen.saldo_monto += self.monto
            self.origen.save()

            # Quitar del Destino
            self.destino.saldo_monto -= self.monto
            self.destino.save()

            # Nota: Los movimientos de fondo quedan como histórico, o se podrían marcar anulados.
            # Por simplicidad contable, generamos contra-movimientos o simplemente ajustamos saldo.
            # Aquí ajustamos saldo directo para mantener consistencia simple.

            self.finanzas_aplicadas = False
            self.save(update_fields=['finanzas_aplicadas'])

    def __str__(self):
        return f"TRF ${self.monto} ({self.origen} -> {self.destino})"

    class Meta:
        verbose_name = "Transferencia Interna / Depósito"
        verbose_name_plural = "Transferencias Internas / Depósitos"


# --- SIGNALS (Para conectar el admin con el modelo) ---

@receiver(post_save, sender=TransferenciaInterna)
def trigger_transferencia(sender, instance, **kwargs):
    """
    Disparador automático para Transferencias.
    Al ser un modelo simple sin inlines, podemos usar post_save con seguridad.
    """
    if instance.estado == TransferenciaInterna.Estado.CONFIRMADO:
        # Intentar aplicar (el método tiene su propia validación para no duplicar)
        instance.aplicar_transferencia()

    elif instance.estado == TransferenciaInterna.Estado.ANULADO:
        # Revertir
        instance.revertir_transferencia()


@receiver(pre_delete, sender=TransferenciaInterna)
def reversar_al_eliminar_trf(sender, instance, **kwargs):
    if instance.finanzas_aplicadas:
        instance.revertir_transferencia()


# ========================================================
#  MÓDULO E: IMPUESTOS Y RETENCIONES
# ========================================================

class RegimenRetencion(models.Model):
    class Impuesto(models.TextChoices):
        GANANCIAS = 'GAN', 'Ganancias'
        IIBB = 'IIBB', 'Ingresos Brutos'
        SUSS = 'SUSS', 'SUSS / Seguridad Social'
        IVA = 'IVA', 'IVA'

    nombre = models.CharField(max_length=100)
    impuesto = models.CharField(max_length=4, choices=Impuesto.choices, default=Impuesto.GANANCIAS)
    codigo_afip = models.CharField(max_length=10, blank=True, help_text="Código de régimen según AFIP")

    # Lógica de Cálculo Simplificada
    alicuota_inscripto = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                             verbose_name="% Inscripto")
    alicuota_no_inscripto = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                verbose_name="% No Inscripto")
    monto_no_imponible = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                             help_text="Monto mínimo sobre el cual se aplica")
    monto_minimo_retencion = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                                 help_text="Si el cálculo da menos que esto, no se retiene")

    def __str__(self): return f"[{self.impuesto}] {self.nombre}"

    class Meta:
        verbose_name = "Régimen de Retención"
        verbose_name_plural = "Regímenes de Retención"


class CertificadoRetencion(models.Model):
    """
    Documento que avala que retuvimos dinero al proveedor.
    Se genera automáticamente desde la Orden de Pago.
    """
    fecha = models.DateField(default=timezone.now)
    numero = models.CharField(max_length=50, verbose_name="N° Certificado")
    proveedor = models.ForeignKey('compras.Proveedor', on_delete=models.PROTECT)
    regimen = models.ForeignKey(RegimenRetencion, on_delete=models.PROTECT)

    # Vínculo con el pago (string para evitar dependencia circular estricta)
    orden_pago = models.ForeignKey('compras.OrdenPago', on_delete=models.CASCADE,
                                   related_name='certificados_emitidos')

    # Detalles del cálculo
    base_calculo = models.DecimalField(max_digits=14, decimal_places=2, help_text="Monto sujeto a retención")
    importe_retenido = models.DecimalField(max_digits=14, decimal_places=2)

    # Hash de seguridad para validar (opcional)
    token_validacion = models.CharField(max_length=64, blank=True, editable=False)

    def __str__(self): return f"Cert. {self.regimen.impuesto} #{self.numero}"

    class Meta:
        verbose_name = "Certificado de Retención"
        verbose_name_plural = "Certificados de Retención"