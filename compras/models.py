# compras/models.py (VERSIÓN CORREGIDA Y BLINDADA)

from django.db import models, transaction
from decimal import Decimal
from djmoney.models.fields import MoneyField
from djmoney.money import Money
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings

from entidades.models import Entidad
from parametros.models import Contador, TipoComprobante, Role, Moneda, UnidadMedida, get_default_unidad_medida


def get_default_moneda_pk():
    """
    Obtiene el PK de la moneda base o crea una por defecto (ARS) si no existe.
    Esto es crucial para que las migraciones no fallen en una base de datos vacía.
    """
    moneda, created = Moneda.objects.get_or_create(
        es_base=True,
        defaults={'nombre': 'Peso Argentino', 'simbolo': 'ARS', 'cotizacion': 1.00}
    )
    return moneda.pk


# --- MODELO PROVEEDOR ---
class Proveedor(models.Model):
    entidad = models.OneToOneField(Entidad, on_delete=models.CASCADE, primary_key=True)
    codigo_proveedor = models.CharField(max_length=50, unique=True, blank=True, null=True,
                                        verbose_name="Código de Proveedor")
    nombre_fantasia = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nombre de Fantasía")
    limite_credito = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Límite de Crédito")
    roles = models.ManyToManyField(Role, blank=True, help_text="Roles que pueden gestionar este proveedor.")

    def __str__(self):
        return self.entidad.razon_social

    def save(self, *args, **kwargs):
        if not self.codigo_proveedor:
            try:
                with transaction.atomic():
                    contador, created = Contador.objects.get_or_create(nombre='codigo_proveedor',
                                                                       defaults={'prefijo': 'P', 'ultimo_valor': 0})
                    contador.ultimo_valor += 1
                    self.codigo_proveedor = f"{contador.prefijo}{str(contador.ultimo_valor).zfill(5)}"
                    contador.save()
            except Exception:
                pass
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Proveedor";
        verbose_name_plural = "Proveedores"


# --- COMPROBANTE DE COMPRA ---
class ComprobanteCompra(models.Model):
    proveedor = models.ForeignKey('Proveedor', on_delete=models.PROTECT, verbose_name="Proveedor")
    deposito = models.ForeignKey('inventario.Deposito', on_delete=models.PROTECT, null=True, blank=True)

    class Estado(
        models.TextChoices): BORRADOR = 'BR', 'Borrador'; FINALIZADO = 'FN', 'Finalizado'; ANULADO = 'AN', 'Anulado'

    tipo_comprobante = models.ForeignKey('parametros.TipoComprobante', on_delete=models.PROTECT,
                                         verbose_name="Tipo de Comprobante")
    letra = models.CharField(max_length=1, editable=False)
    punto_venta = models.PositiveIntegerField(default=1, verbose_name="Punto de Venta")
    numero = models.PositiveIntegerField(verbose_name="Número")
    fecha = models.DateField(verbose_name="Fecha del Comprobante")
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR, verbose_name="Estado")
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    impuestos = models.JSONField(default=dict, editable=False, help_text="Desglose de impuestos")
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    comprobante_origen = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name='comprobantes_derivados')

    def __str__(self): return f"{self.tipo_comprobante.nombre} de {self.proveedor}"

    def save(self, *args, **kwargs):
        if self.tipo_comprobante: self.letra = self.tipo_comprobante.letra
        super().save(*args, **kwargs)

    class Meta: verbose_name = "Comprobante de Compra"; verbose_name_plural = "Comprobantes de Compra"


class ComprobanteCompraItem(models.Model):
    comprobante = models.ForeignKey(ComprobanteCompra, related_name='items', on_delete=models.CASCADE)
    articulo = models.ForeignKey('inventario.Articulo', on_delete=models.PROTECT, verbose_name="Artículo")
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)
    precio_costo_unitario_monto = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="Costo Unitario",
                                                      default=0)
    precio_costo_unitario_moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, default=get_default_moneda_pk)
    datos_costo_efectivo = models.JSONField(default=dict, editable=False)

    @property
    def precio_costo_unitario(self): return Money(self.precio_costo_unitario_monto,
                                                  self.precio_costo_unitario_moneda.simbolo)

    @property
    def subtotal(self): return (self.cantidad or Decimal(0)) * self.precio_costo_unitario

    def __str__(self): return f"{self.cantidad} x {self.articulo.descripcion if self.articulo else 'N/A'}"


# --- LISTAS DE PRECIOS ---
class ListaPreciosProveedor(models.Model):
    proveedor = models.ForeignKey('Proveedor', on_delete=models.CASCADE, related_name='listas_precios')
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Lista")
    codigo = models.CharField(max_length=20, blank=True, verbose_name="Código")
    vigente_desde = models.DateField(default=timezone.now, verbose_name="Vigente Desde")
    vigente_hasta = models.DateField(null=True, blank=True, verbose_name="Vigente Hasta")
    es_activa = models.BooleanField(default=True, verbose_name="¿Está Activa?")
    es_principal = models.BooleanField(default=False, verbose_name="¿Es la Lista Principal?")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    observaciones = models.TextField(blank=True, verbose_name="Observaciones")

    def clean(self):
        if self.vigente_hasta and self.vigente_desde > self.vigente_hasta: raise ValidationError(
            "La fecha de fin debe ser posterior a la fecha de inicio")
        if self.es_principal:
            if ListaPreciosProveedor.objects.filter(proveedor=self.proveedor, es_principal=True).exclude(
                    pk=self.pk).exists():
                raise ValidationError(f"El proveedor {self.proveedor} ya tiene una lista principal")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.es_principal:
            ListaPreciosProveedor.objects.filter(proveedor=self.proveedor, es_principal=True).exclude(
                pk=self.pk).update(es_principal=False)

    def __str__(self):
        return f"{self.proveedor.entidad.razon_social} - {self.nombre}"

    class Meta:
        verbose_name = "1. Lista de Precios de Proveedor";
        verbose_name_plural = "1. Listas de Precios de Proveedores"
        ordering = ['proveedor__entidad__razon_social', '-es_principal', '-vigente_desde']
        unique_together = ['proveedor', 'nombre']


class ItemListaPreciosProveedor(models.Model):
    lista_precios = models.ForeignKey(ListaPreciosProveedor, on_delete=models.CASCADE, related_name='items')
    articulo = models.ForeignKey('inventario.Articulo', on_delete=models.CASCADE, related_name='precios_proveedor')
    unidad_medida_compra = models.ForeignKey('parametros.UnidadMedida', on_delete=models.PROTECT,
                                             verbose_name="Unidad de Medida de Compra",
                                             help_text="En qué unidad el proveedor vende este artículo")
    # Campos explícitos para el precio
    precio_lista_monto = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="Monto del Precio",
                                             default=0)
    precio_lista_moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT, verbose_name="Moneda",
                                            default=get_default_moneda_pk)

    bonificacion_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                  verbose_name="Bonificación (%)",
                                                  help_text="Ej: 15% significa pagar 85 de cada 100")
    descuentos_adicionales = models.JSONField(default=list, blank=True, verbose_name="Descuentos Adicionales (%)",
                                              help_text="Lista de descuentos en cascada. Ej: [-5, -2, 1]")
    descuentos_financieros = models.JSONField(default=list, blank=True,
                                              verbose_name="Descuentos/Recargos Financieros (%)",
                                              help_text="Ej: [-10] para 10% descuento por pago contado")
    cantidad_minima = models.DecimalField(max_digits=10, decimal_places=3, default=1, verbose_name="Cantidad Mínima",
                                          help_text="Cantidad mínima para aplicar este precio")
    codigo_articulo_proveedor = models.CharField(max_length=50, blank=True, verbose_name="Código del Proveedor",
                                                 help_text="Cómo el proveedor identifica este artículo")

    @property
    def precio_lista(self):
        return Money(self.precio_lista_monto, self.precio_lista_moneda.simbolo)

    @property
    def costo_efectivo(self):
        from compras.services import CostCalculatorService
        return CostCalculatorService.calculate_effective_cost(self)

    def __str__(self): return f"{self.articulo.descripcion} - {self.lista_precios.nombre}"

    class Meta:
        verbose_name = "2. Ítem de Lista de Precios";
        verbose_name_plural = "2. Ítems de Listas de Precios"
        unique_together = ['lista_precios', 'articulo', 'cantidad_minima']
        ordering = ['articulo__descripcion', 'cantidad_minima']


# --- CAPA 3: El Historial de Auditoría ---
class HistorialPrecioProveedor(models.Model):
    item = models.ForeignKey(ItemListaPreciosProveedor, on_delete=models.CASCADE, related_name='historial')
    precio_lista_anterior = MoneyField(max_digits=14, decimal_places=4, default_currency='ARS')
    precio_lista_nuevo = MoneyField(max_digits=14, decimal_places=4, default_currency='ARS')
    costo_efectivo_anterior = MoneyField(max_digits=14, decimal_places=4, default_currency='ARS', null=True)
    costo_efectivo_nuevo = MoneyField(max_digits=14, decimal_places=4, default_currency='ARS', null=True)
    fecha_cambio = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    motivo = models.CharField(max_length=255, blank=True, verbose_name="Motivo del Cambio")

    def __str__(self):
        return f"Cambio en {self.item.articulo.descripcion} el {self.fecha_cambio.strftime('%d/%m/%Y')}"

    class Meta:
        verbose_name = "3. Historial de Precio de Proveedor"
        verbose_name_plural = "3. Historial de Precios de Proveedores"
        ordering = ['-fecha_cambio']


# --- SIGNALS ---

@receiver(pre_save, sender=ItemListaPreciosProveedor)
def crear_historial_precio(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            if old.precio_lista_monto != instance.precio_lista_monto:
                HistorialPrecioProveedor.objects.create(
                    item=instance,
                    precio_lista_anterior=old.precio_lista,
                    precio_lista_nuevo=instance.precio_lista,
                    costo_efectivo_anterior=None,
                    costo_efectivo_nuevo=None,
                    motivo="Actualización manual."
                )
        except Exception:
            pass


@receiver(post_save, sender=ItemListaPreciosProveedor)
def actualizar_costo_articulo_signal(sender, instance, created, **kwargs):
    """
    Signal robusta para actualizar el costo del artículo maestro.
    """
    print(f"--- SIGNAL DISPARADA: {instance} ---")
    articulo = instance.articulo
    proveedor_lista = instance.lista_precios.proveedor

    # 1. Obtener quién es la fuente de verdad
    proveedor_autoridad = articulo.proveedor_actualiza_precio

    print(f"Autoridad: {proveedor_autoridad} | Prov. Lista: {proveedor_lista}")

    # 2. Comparación robusta (por PK si existen)
    es_autoridad = False
    if proveedor_autoridad and proveedor_lista:
        if proveedor_autoridad.pk == proveedor_lista.pk:
            es_autoridad = True

    if es_autoridad:
        print(">> Es autoridad. Procediendo a actualizar costo.")

        # Calcular costo efectivo (con descuentos si los hubiera)
        costo_nuevo_money = instance.costo_efectivo

        # Si cost_efectivo falla o devuelve 0, usamos el precio de lista directo
        if not costo_nuevo_money or costo_nuevo_money.amount == 0:
            costo_nuevo_money = instance.precio_lista

        monto_nuevo = costo_nuevo_money.amount
        moneda_nueva_cod = costo_nuevo_money.currency.code

        # Definimos la variable correctamente
        moneda_actual_cod = articulo.precio_costo_moneda.simbolo if articulo.precio_costo_moneda else 'ARS'

        # 3. Actualizamos si hay cambios (CORREGIDO: Usamos moneda_actual_cod)
        if (articulo.precio_costo_monto != monto_nuevo) or (moneda_actual_cod != moneda_nueva_cod):
            print(f">> Cambio detectado: {articulo.precio_costo_monto} -> {monto_nuevo}")

            articulo.precio_costo_monto = monto_nuevo

            # Buscar objeto moneda
            try:
                moneda_obj = Moneda.objects.filter(simbolo=moneda_nueva_cod).first()
                if moneda_obj:
                    articulo.precio_costo_moneda = moneda_obj
            except Exception:
                pass

            articulo.save()
            print(">> Artículo guardado exitosamente.")
        else:
            print(">> El costo ya estaba actualizado.")
    else:
        print(">> Este proveedor NO es la fuente de verdad.")