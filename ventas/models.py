# ventas/models.py (VERSIÓN CON CORRECCIÓN DE IMPORTACIÓN)

from django.db import models
from django.db.models import Sum
from decimal import Decimal
from djmoney.money import Money

# --- INICIO DE LA CORRECCIÓN ---
# 1. Eliminamos la importación problemática de 'parametros.models'.

# 2. Definimos la función localmente para evitar la dependencia circular.
#    Importamos el modelo 'Moneda' aquí dentro para que se cargue cuando se necesite.
def get_default_moneda_pk():
    from parametros.models import Moneda
    moneda, created = Moneda.objects.get_or_create(
        es_base=True,
        defaults={'nombre': 'Peso Argentino', 'simbolo': 'ARS', 'cotizacion': 1.00}
    )
    return moneda.pk
# --- FIN DE LA CORRECCIÓN ---


# --- Tus modelos existentes ---
class Cliente(models.Model):
    entidad = models.OneToOneField('entidades.Entidad', on_delete=models.CASCADE, primary_key=True)
    price_list = models.ForeignKey(
        'PriceList',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Lista de Precios Asignada"
    )

    def __str__(self):
        return self.entidad.razon_social

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

# ... (El resto de tus modelos ComprobanteVenta y ComprobanteVentaItem permanecen exactamente igual) ...
class ComprobanteVenta(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BR', 'Borrador'
        FINALIZADO = 'FN', 'Finalizado'
        ANULADO = 'AN', 'Anulado'

    tipo_comprobante = models.ForeignKey('parametros.TipoComprobante', on_delete=models.PROTECT, verbose_name="Tipo de Comprobante")
    letra = models.CharField(max_length=1, editable=False)
    punto_venta = models.PositiveIntegerField(default=1, verbose_name="Punto de Venta")
    numero = models.PositiveIntegerField(verbose_name="Número")
    cliente = models.ForeignKey('Cliente', on_delete=models.PROTECT, verbose_name="Cliente")
    fecha = models.DateField(verbose_name="Fecha del Comprobante")
    estado = models.CharField(max_length=2, choices=Estado.choices, default=Estado.BORRADOR, verbose_name="Estado")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    impuestos = models.JSONField(default=dict, editable=False, help_text="Desglose de impuestos calculados")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    deposito = models.ForeignKey('inventario.Deposito', on_delete=models.PROTECT, null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.tipo_comprobante: self.letra = self.tipo_comprobante.letra
        from inventario.models import Deposito
        if not self.deposito_id and self.deposito is None:
            deposito_principal = Deposito.objects.filter(es_principal=True).first()
            if deposito_principal:
                self.deposito = deposito_principal
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tipo_comprobante.nombre} {self.numero_completo} a {self.cliente}"

    @property
    def numero_completo(self):
        return f"{self.letra} {self.punto_venta:05d}-{self.numero:08d}"

    class Meta:
        verbose_name = "Comprobante de Venta"
        verbose_name_plural = "Comprobantes de Venta"
        unique_together = ('tipo_comprobante', 'punto_venta', 'numero')


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

# --- NUEVOS MODELOS PARA LISTAS DE PRECIOS DE VENTA ---

class PriceList(models.Model):
    """
    Listas de precios de venta múltiples (Ej: 'Minorista', 'Mayorista', 'VIP').
    """
    # company = models.ForeignKey('companies.Company', on_delete=models.CASCADE) # Comentado para simplificar
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
        # unique_together = ['company', 'code'] # Comentado para simplificar
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
    max_quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Cantidad Máxima")

    class Meta:
        unique_together = ['product', 'price_list', 'min_quantity']
        ordering = ['min_quantity']
        verbose_name = "Precio de Producto"
        verbose_name_plural = "Precios de Productos"

    @property
    def price(self):
        return Money(self.price_monto, self.price_moneda.simbolo)