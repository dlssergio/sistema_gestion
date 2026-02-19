# inventario/models.py

from django.db import models, transaction
from django.db.models import Sum, Q, F
from decimal import Decimal
from djmoney.money import Money
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils import timezone
from django.conf import settings

from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save

# Importaciones de parametros
from parametros.models import (
    Contador, Moneda, UnidadMedida, get_default_unidad_medida,
    Impuesto, get_default_moneda_pk, GrupoUnidadMedida, CategoriaImpositiva
)

# ==========================================
# CONSTANTES Y DOCUMENTACIÓN
# ==========================================
"""
ESTÁNDARES DE CÓDIGOS DE STOCK (Convención Recomendada)
-------------------------------------------------------
REAL  -> Stock Físico (Disponible para venta y entrega inmediata).
RSRV  -> Comprometido (Reservado por Pedidos, resta disponibilidad).
RCPT  -> A Recibir (Órdenes de Compra confirmadas, futuro ingreso).
TRNS  -> En Tránsito (Mercadería viajando entre depósitos).
QC    -> Control de Calidad / Cuarentena (Físico pero no vendible).
3RD   -> Stock de Terceros (En consignación).
"""


# ==========================================
# NUEVA ARQUITECTURA DE STOCK (ENTERPRISE)
# ==========================================

class TipoStock(models.Model):
    """
    Define la naturaleza del stock. (Data Driven)
    Ej: REAL (Físico), RSRV (Comprometido), RCPT (A Recibir), QC (Calidad).
    """
    codigo = models.CharField(max_length=10, unique=True, help_text="Clave única (ej: REAL, RSRV)")
    nombre = models.CharField(max_length=50)

    # Flags de Comportamiento (Reglas de Negocio)
    es_fisico = models.BooleanField(default=False, help_text="¿La mercadería está físicamente en el depósito?")
    es_vendible = models.BooleanField(default=False, help_text="¿Suma al stock disponible para venta?")
    es_reservado = models.BooleanField(default=False, help_text="¿Resta del stock disponible?")

    # --- FLAGS FUTUROS (PREPARACIÓN ENTERPRISE) ---
    es_en_transito = models.BooleanField(default=False, help_text="Mercadería viajando entre ubicaciones.")
    es_de_terceros = models.BooleanField(default=False, help_text="Mercadería en consignación.")
    afecta_valorizacion = models.BooleanField(default=True, help_text="¿Impacta en la valorización del inventario?")

    class Meta:
        verbose_name = "Configuración de Tipo de Stock"
        verbose_name_plural = "Tipos de Stock (Config)"

    def clean(self):
        # VALIDACIÓN DE REGLAS DE NEGOCIO
        if self.es_vendible and self.es_reservado:
            raise ValidationError(
                "Inconsistencia: Un Tipo de Stock no puede ser 'Vendible' y 'Reservado' simultáneamente. "
                "Debe sumar al disponible O restar del disponible."
            )

    def save(self, *args, **kwargs):
        self.full_clean()  # Forzar validación antes de guardar
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class BalanceStock(models.Model):
    """
    VISTA MATERIALIZADA PROTEGIDA.
    -------------------------------------------------------------------------
    ADVERTENCIA: Este modelo NO debe ser modificado directamente.
    Su integridad depende exclusivamente de StockManager.registrar_movimiento().
    Cualquier escritura manual aquí desincronizará el sistema respecto al Ledger.
    -------------------------------------------------------------------------
    """
    articulo = models.ForeignKey('Articulo', on_delete=models.PROTECT, related_name='balances_stock')
    deposito = models.ForeignKey('Deposito', on_delete=models.PROTECT, related_name='balances_stock')
    tipo_stock = models.ForeignKey(TipoStock, on_delete=models.PROTECT)

    # Futuro: Lote/Serie irían aquí como parte de la clave única

    cantidad = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['articulo', 'deposito', 'tipo_stock']
        indexes = [
            models.Index(fields=['articulo', 'deposito']),
        ]
        verbose_name = "Balance de Stock"
        verbose_name_plural = "Balances de Stock"

    def __str__(self):
        return f"{self.articulo} | {self.tipo_stock.codigo}: {self.cantidad}"


class MovimientoStockLedger(models.Model):
    """
    FUENTE DE LA VERDAD. Bitácora inmutable. Append-Only.
    Registra cada impacto. Referencia débil al documento origen.
    """
    fecha_registro = models.DateTimeField(auto_now_add=True, db_index=True)
    fecha_movimiento = models.DateTimeField(default=timezone.now, verbose_name="Fecha Efectiva", db_index=True)

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)

    # Dimensiones
    articulo = models.ForeignKey('Articulo', on_delete=models.PROTECT, db_index=True)
    deposito = models.ForeignKey('Deposito', on_delete=models.PROTECT, db_index=True)
    tipo_stock = models.ForeignKey(TipoStock, on_delete=models.PROTECT)

    cantidad = models.DecimalField(max_digits=15, decimal_places=4, help_text="Positivo=Entra, Negativo=Sale")

    # Referencia Desacoplada (Texto puro para trazabilidad sin GenericFK)
    origen_sistema = models.CharField(max_length=50, help_text="Ej: 'VENTAS', 'COMPRAS', 'AJUSTE', 'MIGRACION'")
    origen_referencia = models.CharField(max_length=100, help_text="Ej: 'FC-A 0001-00001234' o ID interno")

    observaciones = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-fecha_registro']
        verbose_name = "Movimiento de Stock (Ledger)"
        verbose_name_plural = "Ledger de Stock"
        indexes = [
            # Índice KARDEX: Optimiza reportes de evolución temporal por tipo
            models.Index(fields=['articulo', 'tipo_stock', 'fecha_movimiento']),
            # Índice TRAZABILIDAD
            models.Index(fields=['origen_sistema', 'origen_referencia']),
        ]


# ==========================================
# MODELOS EXISTENTES (LEGACY & MAESTROS)
# ==========================================

class Marca(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")

    def __str__(self): return self.nombre

    class Meta: verbose_name = "Marca"; verbose_name_plural = "Marcas"


class Rubro(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")

    def __str__(self): return self.nombre

    class Meta: verbose_name = "Rubro"; verbose_name_plural = "Rubros"


class Deposito(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    es_principal = models.BooleanField(default=False, help_text="Marcar si este es el depósito principal.")

    # NUEVO FLAG A.2: Regla por Depósito
    permite_stock_negativo = models.BooleanField(
        default=False,
        verbose_name="¿Permite Stock Negativo?",
        help_text="Si está marcado, este depósito permite egresos sin stock suficiente, salvo override manual."
    )

    def __str__(self): return self.nombre

    class Meta: verbose_name = "Depósito"; verbose_name_plural = "Depósitos"


class StockArticulo(models.Model):
    """
    MODELO LEGACY / VISTA MATERIALIZADA.
    Se mantiene por compatibilidad hacia atrás.
    Se actualiza automáticamente desde el StockManager junto con el Ledger.
    """
    articulo = models.ForeignKey('Articulo', on_delete=models.CASCADE, related_name="stocks")
    deposito = models.ForeignKey(Deposito, on_delete=models.CASCADE)

    cantidad_real = models.DecimalField(
        max_digits=12, decimal_places=3, default=0,
        verbose_name="Stock Físico Real"
    )
    cantidad_comprometida = models.DecimalField(
        max_digits=12, decimal_places=3, default=0,
        verbose_name="Stock Comprometido"
    )

    @property
    def cantidad_disponible(self):
        return self.cantidad_real - self.cantidad_comprometida

    def __str__(self):
        return f"{self.articulo.descripcion}: Físico {self.cantidad_real} | Disp {self.cantidad_disponible}"

    class Meta:
        unique_together = ('articulo', 'deposito')
        verbose_name = "Stock por Depósito (Legacy)"
        verbose_name_plural = "Stocks por Depósito (Legacy)"


class Articulo(models.Model):
    class Perfil(models.TextChoices):
        COMPRA_VENTA = 'CV', 'Compra/Venta'
        COMPRA = 'CO', 'Compra'
        VENTA = 'VE', 'Venta'

    cod_articulo = models.CharField(max_length=20,
                                    unique=True,
                                    verbose_name="Código Artículo",
                                    help_text="Dejar en blanco para autogenerar.")
    ean = models.CharField(max_length=13, blank=True, null=True, db_index=True,
                           verbose_name="Código de Barras EAN",
                           help_text="Código de barras EAN-13.")
    qr = models.CharField(max_length=255, blank=True, null=True, verbose_name="Código QR")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")
    perfil = models.CharField(max_length=2, choices=Perfil.choices, default=Perfil.COMPRA_VENTA,
                              verbose_name="Perfil")

    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Marca")
    rubro = models.ForeignKey(Rubro, on_delete=models.PROTECT, verbose_name="Rubro")

    grupo_unidades = models.ForeignKey(GrupoUnidadMedida, on_delete=models.PROTECT, null=True, blank=True,
                                       verbose_name="Grupo de Unidades",
                                       help_text="Define la categoría de unidades del artículo (Peso, Volumen, etc.)")
    unidad_medida_stock = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, default=get_default_unidad_medida,
                                            related_name='articulos_stock',
                                            verbose_name="U.M. de Stock")
    unidad_medida_venta = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, default=get_default_unidad_medida,
                                            related_name='articulos_venta',
                                            verbose_name="U.M. de Venta")

    precio_costo_monto = models.DecimalField(max_digits=14, decimal_places=4, default=0, verbose_name="Costo")
    precio_costo_moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, default=get_default_moneda_pk,
                                            verbose_name="Moneda Costo", related_name='articulos_costo')

    precio_venta_monto = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Venta")
    precio_venta_moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, default=get_default_moneda_pk,
                                            verbose_name="Moneda Venta", related_name='articulos_venta_moneda')

    utilidad = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                   help_text="Porcentaje de ganancia sobre el costo.", verbose_name="Utilidad (%)")

    categoria_impositiva = models.ForeignKey(CategoriaImpositiva, on_delete=models.PROTECT, null=True, blank=True,
                                             verbose_name="Categoría Impositiva")
    impuestos = models.ManyToManyField(Impuesto, blank=True,
                                       verbose_name="Impuestos Aplicables",
                                       help_text="Seleccione todos los impuestos que aplican a este artículo (IVA, Internos, etc.)")

    proveedores = models.ManyToManyField('compras.Proveedor', through='ProveedorArticulo',
                                         related_name='articulos_directos', blank=True,
                                         verbose_name="Proveedores Relacionados")

    administra_stock = models.BooleanField(default=True, verbose_name="¿Administra Stock?")
    esta_activo = models.BooleanField(default=True, verbose_name="¿Está Activo?")
    foto = models.ImageField(
        upload_to='productos/',
        null=True,
        blank=True,
        verbose_name="Foto del Producto"
    )
    ubicacion = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Ubicación Física",
        help_text="Ej: Pasillo 4, Estantería B"
    )
    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones")
    nota = models.TextField(blank=True, null=True, verbose_name="Nota Interna")

    # NUEVO FLAG A.1: Regla por Artículo
    permite_stock_negativo = models.BooleanField(
        default=False,
        verbose_name="¿Permite Stock Negativo?",
        help_text="Define si este artículo específico puede quedar en saldo negativo."
    )

    @property
    def precio_costo(self):
        return Money(self.precio_costo_monto, self.precio_costo_moneda.simbolo)

    @property
    def precio_venta(self):
        return Money(self.precio_venta_monto, self.precio_venta_moneda.simbolo)

    @property
    def proveedor_actualiza_precio(self):
        try:
            return self.proveedorarticulo_set.get(es_fuente_de_verdad=True).proveedor
        except ObjectDoesNotExist:
            return None

    @property
    def stock_total(self):
        """
        Calcula el stock total físico sumando la tabla legacy.
        """
        if self.administra_stock:
            total = self.stocks.aggregate(total_stock=Sum('cantidad_real'))['total_stock']
            return total if total is not None else Decimal('0.000')
        return Decimal('0.000')

    # MEJORA B.1: Corrección Aritmética Segura
    @property
    def stock_disponible_calculado(self):
        """
        NUEVO: Calcula disponibilidad real basada en Tipos de Stock.
        Formula: Sum(Vendibles) - Sum(Reservados) usando BalanceStock.
        """
        if not self.administra_stock: return Decimal(0)

        balances = self.balances_stock.all().select_related('tipo_stock')
        total = Decimal(0)
        for b in balances:
            # Aseguramos tipo Decimal para evitar errores de coerción
            cant = b.cantidad if isinstance(b.cantidad, Decimal) else Decimal(str(b.cantidad))

            if b.tipo_stock.es_vendible:
                total += cant
            if b.tipo_stock.es_reservado:
                total -= cant
        return total

    def save(self, *args, **kwargs):
        if not self.cod_articulo:
            try:
                with transaction.atomic():
                    contador, created = Contador.objects.get_or_create(nombre='codigo_articulo',
                                                                       defaults={'prefijo': 'A', 'ultimo_valor': 0})
                    contador.ultimo_valor += 1
                    self.cod_articulo = f"{contador.prefijo}{str(contador.ultimo_valor).zfill(5)}"
                    contador.save()
            except Contador.DoesNotExist:
                pass

        if self.precio_costo_monto > 0 and self.utilidad is not None:
            costo_en_base = self.precio_costo_monto * self.precio_costo_moneda.cotizacion
            venta_en_base = costo_en_base * (Decimal(1) + (self.utilidad / Decimal(100)))
            if self.precio_venta_moneda.cotizacion > 0:
                self.precio_venta_monto = venta_en_base / self.precio_venta_moneda.cotizacion
            else:
                self.precio_venta_monto = venta_en_base

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descripcion} ({self.cod_articulo})"

    class Meta:
        verbose_name = "Artículo";
        verbose_name_plural = "Artículos"


class ProveedorArticulo(models.Model):
    proveedor = models.ForeignKey('compras.Proveedor', on_delete=models.CASCADE)
    articulo = models.ForeignKey('Articulo', on_delete=models.CASCADE)
    es_fuente_de_verdad = models.BooleanField(default=False, verbose_name="Fuente de Costo Base",
                                              help_text="Marcar si este proveedor tiene autoridad para actualizar el precio_costo del artículo.")
    fecha_relacion = models.DateField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.es_fuente_de_verdad:
            ProveedorArticulo.objects.filter(articulo=self.articulo).exclude(pk=self.pk).update(
                es_fuente_de_verdad=False)
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ('proveedor', 'articulo')
        verbose_name = "Proveedor de Artículo";
        verbose_name_plural = "Proveedores de Artículos"
        constraints = [
            models.UniqueConstraint(fields=['articulo'], condition=models.Q(es_fuente_de_verdad=True),
                                    name='unique_fuente_de_verdad_por_articulo')
        ]


class ConversionUnidadMedida(models.Model):
    articulo = models.ForeignKey(Articulo, on_delete=models.CASCADE, related_name="conversiones_uom")
    unidad_externa = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, related_name="conversiones_externas",
                                       default=get_default_unidad_medida,
                                       help_text="Unidad a convertir (ej: Caja, Botella, Bulto)")
    factor_conversion = models.DecimalField(max_digits=14, decimal_places=6,
                                            help_text="¿Cuántas unidades de stock (la más pequeña) caben en la unidad externa? Ej: 1 Caja = 150 Unidades.")

    class Meta:
        unique_together = ('articulo', 'unidad_externa')
        verbose_name = "Factor de Conversión de U.M.";
        verbose_name_plural = "Factores de Conversión de U.M."

    def __str__(self):
        return f"1 {self.unidad_externa.simbolo} = {self.factor_conversion}"


# --- MOVIMIENTOS INTERNOS DE STOCK ---

class MovimientoStock(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = 'ENT', 'Entrada / Ajuste Positivo'
        SALIDA = 'SAL', 'Salida / Ajuste Negativo'
        TRANSFERENCIA = 'TRF', 'Transferencia entre Depósitos'

    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        CONFIRMADO = 'CN', 'Confirmado'
        ANULADO = 'AN', 'Anulado'

    fecha = models.DateField(default=timezone.now, verbose_name="Fecha")
    serie = models.ForeignKey('parametros.SerieDocumento', on_delete=models.PROTECT,
                              verbose_name="Serie / Concepto",
                              help_text="Ej: 'Ajuste Inventario', 'Transferencia Sucursal 1'")
    numero = models.PositiveIntegerField(verbose_name="Número", blank=True, null=True)
    tipo_movimiento = models.CharField(max_length=3, choices=Tipo.choices, default=Tipo.SALIDA,
                                       verbose_name="Tipo de Operación")
    deposito_origen = models.ForeignKey(Deposito, on_delete=models.PROTECT,
                                        related_name='movimientos_salida',
                                        null=True, blank=True,
                                        verbose_name="Depósito Origen (Sale de aquí)")
    deposito_destino = models.ForeignKey(Deposito, on_delete=models.PROTECT,
                                         related_name='movimientos_entrada',
                                         null=True, blank=True,
                                         verbose_name="Depósito Destino (Entra aquí)")
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR)
    observaciones = models.TextField(blank=True)
    stock_aplicado = models.BooleanField(default=False, editable=False)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def clean(self):
        if self.tipo_movimiento == self.Tipo.TRANSFERENCIA:
            if not self.deposito_origen or not self.deposito_destino:
                raise ValidationError("En una transferencia, debe especificar Origen y Destino.")
            if self.deposito_origen == self.deposito_destino:
                raise ValidationError("El origen y el destino no pueden ser el mismo.")
        if self.tipo_movimiento == self.Tipo.SALIDA and not self.deposito_origen:
            raise ValidationError("Para una Salida, debe especificar el Depósito Origen.")
        if self.tipo_movimiento == self.Tipo.ENTRADA and not self.deposito_destino:
            raise ValidationError("Para una Entrada, debe especificar el Depósito Destino.")

    def save(self, *args, **kwargs):
        if self.serie and not self.numero and not self.serie.es_manual:
            from parametros.models import SerieDocumento
            with transaction.atomic():
                serie_lock = SerieDocumento.objects.select_for_update().get(pk=self.serie.pk)
                self.numero = serie_lock.ultimo_numero + 1
                serie_lock.ultimo_numero = self.numero
                serie_lock.save()
        if self.serie.deposito_defecto:
            if self.tipo_movimiento == self.Tipo.SALIDA and not self.deposito_origen:
                self.deposito_origen = self.serie.deposito_defecto
            elif self.tipo_movimiento == self.Tipo.ENTRADA and not self.deposito_destino:
                self.deposito_destino = self.serie.deposito_defecto
        super().save(*args, **kwargs)

    # --- MÉTODOS DE DOMINIO EXPLÍCITOS (Reemplazan lógica dispersa) ---
    @transaction.atomic
    def confirmar_movimiento(self):
        """
        Ejecuta el impacto de stock de forma controlada e idempotente.
        Delega en StockManager.
        """
        if self.estado != self.Estado.CONFIRMADO:
            raise ValidationError("No se puede aplicar stock de un movimiento no confirmado.")

        if self.stock_aplicado:
            return  # Idempotencia: Si ya se aplicó, no hacer nada.

        if not self.items.exists():
            return

        from .services import StockManager  # Importación diferida

        ref = f"Mov. Interno #{self.numero}"
        usuario = self.creado_por

        # El código 'REAL' debe coincidir con un TipoStock existente en la BD.
        # Convención: Movimientos Internos operan sobre stock Físico (REAL).
        CODIGO_TIPO_STD = 'REAL'

        for item in self.items.all():
            if self.tipo_movimiento == self.Tipo.SALIDA:
                # Salida = Movimiento Negativo de Stock REAL
                # NOTA: En movimientos internos, generalmente NO se permite negativo salvo configuración.
                # Aquí pasamos None para que aplique la regla de Depósito/Artículo.
                StockManager.registrar_movimiento(
                    articulo=item.articulo, deposito=self.deposito_origen,
                    codigo_tipo=CODIGO_TIPO_STD, cantidad=-item.cantidad,  # Negativo
                    origen_sistema='MOV_INTERNO', origen_referencia=ref, usuario=usuario,
                    permitir_stock_negativo=None  # Aplica Reglas de Negocio
                )
            elif self.tipo_movimiento == self.Tipo.ENTRADA:
                StockManager.registrar_movimiento(
                    articulo=item.articulo, deposito=self.deposito_destino,
                    codigo_tipo=CODIGO_TIPO_STD, cantidad=item.cantidad,  # Positivo
                    origen_sistema='MOV_INTERNO', origen_referencia=ref, usuario=usuario,
                    permitir_stock_negativo=None
                )
            elif self.tipo_movimiento == self.Tipo.TRANSFERENCIA:
                StockManager.registrar_movimiento(
                    articulo=item.articulo, deposito=self.deposito_origen,
                    codigo_tipo=CODIGO_TIPO_STD, cantidad=-item.cantidad,
                    origen_sistema='MOV_INTERNO', origen_referencia=ref + " (Salida)", usuario=usuario,
                    permitir_stock_negativo=None
                )
                StockManager.registrar_movimiento(
                    articulo=item.articulo, deposito=self.deposito_destino,
                    codigo_tipo=CODIGO_TIPO_STD, cantidad=item.cantidad,
                    origen_sistema='MOV_INTERNO', origen_referencia=ref + " (Entrada)", usuario=usuario,
                    permitir_stock_negativo=None
                )

        self.stock_aplicado = True
        MovimientoStock.objects.filter(pk=self.pk).update(stock_aplicado=True)

    @transaction.atomic
    def revertir_movimiento(self):
        """
        Método explícito para anular impacto de stock.
        """
        if not self.stock_aplicado:
            return

        from .services import StockManager
        ref = f"Reversión Mov. #{self.numero}"
        usuario = self.creado_por
        CODIGO_TIPO_STD = 'REAL'

        for item in self.items.all():
            # Invertimos los signos (La reversión suele ser permisiva para corregir errores)
            if self.tipo_movimiento == self.Tipo.SALIDA:
                StockManager.registrar_movimiento(
                    articulo=item.articulo, deposito=self.deposito_origen,
                    codigo_tipo=CODIGO_TIPO_STD, cantidad=item.cantidad,  # Sumamos para devolver
                    origen_sistema='MOV_INTERNO', origen_referencia=ref, usuario=usuario,
                    permitir_stock_negativo=True
                )
            elif self.tipo_movimiento == self.Tipo.ENTRADA:
                StockManager.registrar_movimiento(
                    articulo=item.articulo, deposito=self.deposito_destino,
                    codigo_tipo=CODIGO_TIPO_STD, cantidad=-item.cantidad,  # Restamos
                    origen_sistema='MOV_INTERNO', origen_referencia=ref, usuario=usuario,
                    permitir_stock_negativo=True
                )
            elif self.tipo_movimiento == self.Tipo.TRANSFERENCIA:
                StockManager.registrar_movimiento(
                    articulo=item.articulo, deposito=self.deposito_origen,
                    codigo_tipo=CODIGO_TIPO_STD, cantidad=item.cantidad,
                    origen_sistema='MOV_INTERNO', origen_referencia=ref, usuario=usuario,
                    permitir_stock_negativo=True
                )
                StockManager.registrar_movimiento(
                    articulo=item.articulo, deposito=self.deposito_destino,
                    codigo_tipo=CODIGO_TIPO_STD, cantidad=-item.cantidad,
                    origen_sistema='MOV_INTERNO', origen_referencia=ref, usuario=usuario,
                    permitir_stock_negativo=True
                )

        self.stock_aplicado = False
        MovimientoStock.objects.filter(pk=self.pk).update(stock_aplicado=False)

    # --- Wrappers de compatibilidad para código existente (Signals) ---
    def aplicar_stock(self):
        self.confirmar_movimiento()

    def revertir_stock(self):
        self.revertir_movimiento()

    def __str__(self):
        return f"{self.get_tipo_movimiento_display()} #{self.numero or '?'}"

    class Meta:
        verbose_name = "Movimiento de Stock Interno"
        verbose_name_plural = "Movimientos de Stock Internos"


class ItemMovimientoStock(models.Model):
    movimiento = models.ForeignKey(MovimientoStock, related_name='items', on_delete=models.CASCADE)
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)

    def __str__(self):
        return f"{self.cantidad} x {self.articulo.cod_articulo}"


@receiver(post_save, sender=MovimientoStock)
def trigger_movimiento_interno(sender, instance, **kwargs):
    """
    WRAPPER DE COMPATIBILIDAD.
    Delega a métodos del modelo. Idealmente, llamar a confirmar_movimiento() explícitamente desde Vistas.
    """
    if instance.estado == MovimientoStock.Estado.CONFIRMADO and not instance.stock_aplicado:
        instance.confirmar_movimiento()
    elif instance.estado == MovimientoStock.Estado.ANULADO and instance.stock_aplicado:
        instance.revertir_movimiento()


class HistoricoMovimientos(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    articulo = models.ForeignKey('Articulo', on_delete=models.PROTECT)
    deposito = models.ForeignKey('Deposito', on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    TIPO_STOCK_CHOICES = [('REAL', 'Físico/Real'), ('COMPROMETIDO', 'Comprometido/Reserva')]
    tipo_stock = models.CharField(max_length=15, choices=TIPO_STOCK_CHOICES)
    OPERACION_CHOICES = [('SUMAR', 'Suma (+)'), ('RESTAR', 'Resta (-)')]
    operacion = models.CharField(max_length=10, choices=OPERACION_CHOICES)
    saldo_post_movimiento = models.DecimalField(max_digits=12, decimal_places=3)
    referencia = models.CharField(max_length=150, blank=True, null=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Legacy Hist: {self.articulo}"

    class Meta:
        verbose_name = "Histórico Legacy (DEPRECADO)"
        verbose_name_plural = "Historial Legacy (DEPRECADO)"


class TransferenciaInterna(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        EN_TRANSITO = 'TR', 'En Tránsito (Enviado)'
        COMPLETADA = 'CP', 'Completada (Recibida)'
        ANULADA = 'AN', 'Anulada'

    fecha = models.DateField(default=timezone.now, verbose_name="Fecha de Creación")
    origen = models.ForeignKey(Deposito, on_delete=models.PROTECT, related_name='transferencias_salida',
                               verbose_name="Depósito Origen")
    destino = models.ForeignKey(Deposito, on_delete=models.PROTECT, related_name='transferencias_entrada',
                                verbose_name="Depósito Destino")
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='transferencias_inventario'
    )

    # Flags para evitar duplicar movimientos
    movimiento_salida_aplicado = models.BooleanField(default=False, editable=False)
    movimiento_entrada_aplicado = models.BooleanField(default=False, editable=False)

    def __str__(self):
        return f"TRF #{self.pk} ({self.origen} -> {self.destino})"

    def clean(self):
        if self.origen_id and self.destino_id and self.origen_id == self.destino_id:
            raise ValidationError("El depósito de origen y destino no pueden ser el mismo.")

    class Meta:
        verbose_name = "Transferencia entre Depósitos"
        verbose_name_plural = "Transferencias entre Depósitos"
        permissions = [
            ("enviar_transferencia", "Puede enviar mercadería (Salida)"),
            ("recibir_transferencia", "Puede recibir mercadería (Entrada)"),
        ]


class ItemTransferencia(models.Model):
    transferencia = models.ForeignKey(TransferenciaInterna, related_name='items', on_delete=models.CASCADE)
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)

    def __str__(self):
        return f"{self.cantidad} x {self.articulo}"


class MotivoAjuste(models.Model):
    """Clasificación para reportes (Ej: Rotura, Robo, Diferencia de Inventario)"""
    nombre = models.CharField(max_length=50, unique=True)

    def __str__(self): return self.nombre

    class Meta:
        verbose_name = "Motivo de Ajuste"
        verbose_name_plural = "Motivos de Ajuste"


class AjusteStock(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        CONFIRMADO = 'CN', 'Confirmado'
        ANULADO = 'AN', 'Anulado'

    fecha = models.DateField(default=timezone.now)
    deposito = models.ForeignKey(Deposito, on_delete=models.PROTECT, verbose_name="Depósito")
    motivo = models.ForeignKey(MotivoAjuste, on_delete=models.PROTECT)
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='ajustes_inventario'  # Related name para evitar choque con otros apps
    )
    stock_aplicado = models.BooleanField(default=False, editable=False)

    def __str__(self):
        return f"Ajuste #{self.pk} - {self.motivo} ({self.fecha})"

    class Meta:
        verbose_name = "Ajuste Manual de Stock"
        verbose_name_plural = "Ajustes Manuales de Stock"


class ItemAjusteStock(models.Model):
    class TipoMovimiento(models.TextChoices):
        ENTRADA = 'E', 'Entrada (+ Suma Stock)'
        SALIDA = 'S', 'Salida (- Resta Stock)'

    ajuste = models.ForeignKey(AjusteStock, related_name='items', on_delete=models.CASCADE)
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT)
    tipo_movimiento = models.CharField(max_length=1, choices=TipoMovimiento.choices, default=TipoMovimiento.SALIDA)
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, help_text="Ingrese siempre valor positivo.")

    def __str__(self):
        signo = "+" if self.tipo_movimiento == 'E' else "-"
        return f"{signo}{self.cantidad} x {self.articulo}"