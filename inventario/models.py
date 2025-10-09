# en inventario/models.py (Versión Corregida)

from django.db import models, transaction
from django.db.models import Sum # <-- Importamos Sum para agregar
from decimal import Decimal
from parametros.models import Moneda, Contador, Impuesto

# ... (Clases Marca, Rubro, Deposito, StockArticulo sin cambios) ...
class Marca(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")
    def __str__(self): return self.nombre
    class Meta:
        verbose_name = "Marca"
        verbose_name_plural = "Marcas"

class Rubro(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")
    def __str__(self): return self.nombre
    class Meta:
        verbose_name = "Rubro"
        verbose_name_plural = "Rubros"

class Deposito(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    es_principal = models.BooleanField(default=False, help_text="Marcar si este es el depósito principal o por defecto.")
    def __str__(self): return self.nombre
    class Meta:
        verbose_name = "Depósito"
        verbose_name_plural = "Depósitos"

class StockArticulo(models.Model):
    articulo = models.ForeignKey('Articulo', on_delete=models.CASCADE, related_name="stocks")
    deposito = models.ForeignKey(Deposito, on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    def __str__(self): return f"{self.articulo.descripcion} en {self.deposito.nombre}: {self.cantidad}"
    class Meta:
        unique_together = ('articulo', 'deposito')
        verbose_name = "Stock por Depósito"
        verbose_name_plural = "Stocks por Depósito"


class Articulo(models.Model):
    # ... (Todos los campos de Articulo hasta 'administra_stock' no cambian) ...
    class UnidadMedida(models.TextChoices):
        UNIDADES = 'UN', 'Unidades'
        KILOGRAMO = 'KG', 'Kilogramo'
        LITRO = 'LT', 'Litro'
        METRO = 'MT', 'Metro'

    class Perfil(models.TextChoices):
        COMPRA_VENTA = 'CV', 'Compra/Venta'
        COMPRA = 'CO', 'Compra'
        VENTA = 'VE', 'Venta'

    cod_articulo = models.CharField(max_length=50, unique=True, primary_key=True, blank=True,
                                    verbose_name="Código de Artículo",
                                    help_text="Dejar en blanco para generar un código automático.")
    ean = models.CharField(max_length=13, blank=True, null=True, db_index=True, verbose_name="Código de Barras (EAN)")
    qr_code = models.CharField(max_length=255, blank=True, null=True, verbose_name="Código QR")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")
    perfil = models.CharField(max_length=2, choices=Perfil.choices, default=Perfil.COMPRA_VENTA,
                              verbose_name="Perfil del Artículo")
    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Marca")
    rubro = models.ForeignKey(Rubro, on_delete=models.PROTECT, verbose_name="Rubro")
    unidad_medida = models.CharField(max_length=2, choices=UnidadMedida.choices, default=UnidadMedida.UNIDADES,
                                     verbose_name="Unidad de Medida")
    moneda_costo = models.ForeignKey(Moneda, on_delete=models.PROTECT, related_name="articulos_costo",
                                     verbose_name="Moneda de Costo", default=1)
    precio_costo_original = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                                verbose_name="Costo Original")
    moneda_venta = models.ForeignKey(Moneda, on_delete=models.PROTECT, related_name="articulos_venta",
                                     verbose_name="Moneda de Venta", default=1)
    precio_venta_original = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                                verbose_name="Venta Original")
    utilidad = models.DecimalField(max_digits=5, decimal_places=2, default=0.00,
                                   help_text="Porcentaje de ganancia sobre el costo en moneda base.",
                                   verbose_name="Utilidad (%)")
    precio_costo_base = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False,
                                            verbose_name="Costo en Moneda Base")
    precio_venta_base = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False,
                                            verbose_name="Venta en Moneda Base")
    impuesto = models.ForeignKey(Impuesto, on_delete=models.PROTECT, verbose_name="Impuesto (IVA)")
    administra_stock = models.BooleanField(default=True, verbose_name="¿Administra Stock?")
    stock_minimo = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="Stock Mínimo")
    stock_maximo = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="Stock Máximo")
    punto_pedido = models.DecimalField(max_digits=12, decimal_places=3, default=0, verbose_name="Punto de Pedido")
    esta_activo = models.BooleanField(default=True, verbose_name="¿Está Activo?")
    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones")
    nota = models.TextField(blank=True, null=True, verbose_name="Nota Interna")

    @property
    def precio_final_calculado(self):
        if self.precio_venta_base and self.impuesto:
            precio_calculado = self.precio_venta_base * (Decimal('1.0') + (self.impuesto.tasa / Decimal('100.0')))
            return round(precio_calculado, 2)
        return Decimal('0.00')

    # --- NUEVA PROPIEDAD AÑADIDA ---
    @property
    def stock_total(self):
        """Calcula y devuelve la suma del stock de este artículo en todos los depósitos."""
        if self.administra_stock:
            # Usamos el related_name "stocks" y el agregador Sum de Django para eficiencia
            total = self.stocks.aggregate(total_stock=Sum('cantidad'))['total_stock']
            return total if total is not None else Decimal('0.000')
        return Decimal('0.000')

    def save(self, *args, **kwargs):
        # ... (método save sin cambios) ...
        if not self.cod_articulo:
            try:
                with transaction.atomic():
                    contador = Contador.objects.select_for_update().get(nombre='codigo_articulo')
                    contador.ultimo_valor += 1
                    self.cod_articulo = f"{contador.prefijo}{str(contador.ultimo_valor).zfill(5)}"
                    contador.save()
            except Contador.DoesNotExist:
                print("ADVERTENCIA: No se encontró el contador 'codigo_articulo'.")
        if self.moneda_costo: self.precio_costo_base = self.precio_costo_original * self.moneda_costo.cotizacion
        if self.moneda_venta: self.precio_venta_base = self.precio_venta_original * self.moneda_venta.cotizacion
        if self.precio_costo_base and self.precio_costo_base > 0:
            self.utilidad = ((self.precio_venta_base / self.precio_costo_base) - Decimal('1.0')) * Decimal('100.0')
        else:
            self.utilidad = Decimal('0.00')
        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.descripcion} ({self.cod_articulo})"

    class Meta:
        verbose_name = "Artículo"
        verbose_name_plural = "Artículos"