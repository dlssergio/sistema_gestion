from django.db import models



class TipoComprobante(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Comprobante")
    codigo_afip = models.CharField(max_length=3, blank=True, null=True, help_text="Código de AFIP si corresponde")
    letra = models.CharField(max_length=1)
    afecta_stock = models.BooleanField(default=False, help_text="Marcar si este comprobante modifica el stock de los artículos.")
    def __str__(self): return self.nombre
    class Meta:
        verbose_name = "Tipo de Comprobante"
        verbose_name_plural = "Tipos de Comprobante"

class Contador(models.Model):
    nombre = models.CharField(max_length=100, unique=True, help_text="Nombre clave del contador, ej: 'codigo_articulo'")
    prefijo = models.CharField(max_length=5, default='P', help_text="Prefijo para el código, ej: 'P'")
    ultimo_valor = models.PositiveIntegerField(default=0, verbose_name="Último Valor Utilizado")
    def __str__(self): return f"Contador para {self.nombre}"
    class Meta:
        verbose_name = "Contador del Sistema"
        verbose_name_plural = "Contadores del Sistema"

class Moneda(models.Model):
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Nombre")
    simbolo = models.CharField(max_length=5, verbose_name="Símbolo")
    cotizacion = models.DecimalField(max_digits=10, decimal_places=2, help_text="Cotización respecto a la moneda base", verbose_name="Cotización")
    es_base = models.BooleanField(default=False, help_text="Marcar si esta es la moneda base del sistema", verbose_name="¿Es Moneda Base?")
    def __str__(self): return self.nombre

    def save(self, *args, **kwargs):
        # Si esta moneda se marca como base, nos aseguramos de que ninguna otra lo sea.
        if self.es_base:
            # CORRECCIÓN: Usamos 'es_base' en lugar de 'por_defecto'
            Moneda.objects.filter(es_base=True).exclude(pk=self.pk).update(es_base=False)
        super().save(*args, **kwargs)
    class Meta:
        verbose_name = "Moneda"
        verbose_name_plural = "Monedas"

class Pais(models.Model):
    codigo = models.CharField(max_length=2, unique=True, verbose_name="Código ISO")
    nombre = models.CharField(max_length=100, unique=True)
    por_defecto = models.BooleanField(default=False, verbose_name="¿Es el país por defecto?")
    def __str__(self): return self.nombre
    def save(self, *args, **kwargs):
        if self.por_defecto: Pais.objects.filter(por_defecto=True).update(por_defecto=False)
        super().save(*args, **kwargs)
    class Meta:
        verbose_name_plural = "Países"

def get_default_pais():
    pais = Pais.objects.filter(por_defecto=True).first()
    if pais: return pais.pk
    return None

class Provincia(models.Model):
    codigo = models.CharField(max_length=3, verbose_name="Código")
    nombre = models.CharField(max_length=100)
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, default=get_default_pais)
    def __str__(self): return self.nombre
    class Meta:
        verbose_name_plural = "Provincias"
        unique_together = ('nombre', 'pais')

class Localidad(models.Model):
    nombre = models.CharField(max_length=255)
    codigo_postal = models.CharField(max_length=10)
    codigo_area_telefonico = models.CharField(max_length=10, blank=True, null=True, verbose_name="Código de Área")
    provincia = models.ForeignKey(Provincia, on_delete=models.PROTECT)
    def __str__(self): return f"{self.nombre} ({self.provincia.nombre})"
    class Meta:
        verbose_name_plural = "Localidades"
        unique_together = ('nombre', 'provincia')

class Impuesto(models.Model):
    descripcion = models.CharField(max_length=100, verbose_name="Descripción")
    tasa = models.DecimalField(max_digits=5, decimal_places=2, help_text="Porcentaje. Ej: 21.00 para 21%",
                               verbose_name="Tasa")

    def __str__(self): return f"{self.descripcion} ({self.tasa}%)"

    class Meta: verbose_name, verbose_name_plural = "Impuesto", "Impuestos"