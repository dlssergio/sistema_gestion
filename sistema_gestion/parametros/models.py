from django.db import models
from django.contrib.auth.models import Permission, User

class TipoComprobante(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Comprobante")
    codigo_afip = models.CharField(max_length=3, blank=True, null=True, help_text="Código de AFIP si corresponde")
    letra = models.CharField(max_length=1)
    afecta_stock = models.BooleanField(default=False, help_text="Marcar si este comprobante modifica el stock.")
    def __str__(self): return self.nombre
    class Meta:
        verbose_name = "Tipo de Comprobante"; verbose_name_plural = "Tipos de Comprobante"

class Contador(models.Model):
    nombre = models.CharField(max_length=100, unique=True, help_text="Nombre clave del contador, ej: 'codigo_articulo'")
    prefijo = models.CharField(max_length=5, default='P', help_text="Prefijo para el código, ej: 'P'")
    ultimo_valor = models.PositiveIntegerField(default=0, verbose_name="Último Valor Utilizado")
    def __str__(self): return f"Contador para {self.nombre}"
    class Meta:
        verbose_name = "Contador del Sistema"; verbose_name_plural = "Contadores del Sistema"

class Moneda(models.Model):
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Nombre")
    simbolo = models.CharField(max_length=5, verbose_name="Símbolo")
    cotizacion = models.DecimalField(max_digits=10, decimal_places=2, help_text="Cotización respecto a la moneda base.", verbose_name="Cotización")
    es_base = models.BooleanField(default=False, help_text="Marcar si esta es la moneda base del sistema.", verbose_name="¿Es Moneda Base?")
    def __str__(self): return self.nombre
    def save(self, *args, **kwargs):
        if self.es_base: Moneda.objects.filter(es_base=True).exclude(pk=self.pk).update(es_base=False)
        super().save(*args, **kwargs)
    class Meta:
        verbose_name = "Moneda"; verbose_name_plural = "Monedas"

class Pais(models.Model):
    codigo = models.CharField(max_length=2, unique=True, verbose_name="Código ISO")
    nombre = models.CharField(max_length=100, unique=True)
    por_defecto = models.BooleanField(default=False, verbose_name="¿Es el país por defecto?")
    def __str__(self): return self.nombre
    def save(self, *args, **kwargs):
        if self.por_defecto: Pais.objects.filter(por_defecto=True).update(por_defecto=False)
        super().save(*args, **kwargs)
    class Meta: verbose_name_plural = "Países"

def get_default_pais():
    # Usamos get_or_create para evitar errores si la base de datos está vacía
    pais, _ = Pais.objects.get_or_create(por_defecto=True, defaults={'nombre': 'Argentina', 'codigo': 'AR'})
    return pais.pk

class Provincia(models.Model):
    codigo = models.CharField(max_length=3, verbose_name="Código")
    nombre = models.CharField(max_length=100)
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, default=get_default_pais)
    def __str__(self): return self.nombre
    class Meta:
        verbose_name_plural = "Provincias"; unique_together = ('nombre', 'pais')

class Localidad(models.Model):
    nombre = models.CharField(max_length=255)
    codigo_postal = models.CharField(max_length=10)
    codigo_area_telefonico = models.CharField(max_length=10, blank=True, null=True, verbose_name="Código de Área")
    provincia = models.ForeignKey(Provincia, on_delete=models.PROTECT)
    def __str__(self): return f"{self.nombre} ({self.provincia.nombre})"
    class Meta:
        verbose_name_plural = "Localidades"; unique_together = ('nombre', 'provincia')

class ReglaImpuesto(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Regla", help_text="Ej: 'IVA 21% General'")
    tasa = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="Tasa/Alícuota")
    TIPO_IMPUESTO_CHOICES = [('porcentaje', 'Porcentaje'), ('fijo', 'Monto Fijo')]
    tipo_impuesto = models.CharField(max_length=20, choices=TIPO_IMPUESTO_CHOICES, default='porcentaje', verbose_name="Tipo de Cálculo")
    APLICA_A_CHOICES = [('venta', 'Ventas'), ('compra', 'Compras')]
    aplica_a = models.CharField(max_length=50, choices=APLICA_A_CHOICES, default='venta', verbose_name="Aplica a")
    categorias_producto = models.ManyToManyField('inventario.Rubro', blank=True, verbose_name="Categorías de Producto (Rubros)", help_text="Dejar en blanco para que aplique a todas.")
    tipos_comprobante = models.ManyToManyField('parametros.TipoComprobante', blank=True, verbose_name="Tipos de Comprobante", help_text="Dejar en blanco para que aplique a todos.")
    activo = models.BooleanField(default=True, verbose_name="¿Está Activa?")
    valido_desde = models.DateField(verbose_name="Válido Desde")
    valido_hasta = models.DateField(null=True, blank=True, verbose_name="Válido Hasta")
    def __str__(self): return f"{self.nombre} ({self.tasa}%)"
    class Meta:
        verbose_name = "Regla de Impuesto"; verbose_name_plural = "Reglas de Impuesto"

class Role(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Nombre del rol, ej: Vendedor")
    permissions = models.ManyToManyField(Permission, blank=True, help_text="Permisos generales asignados.")
    users = models.ManyToManyField(User, blank=True, related_name='roles', help_text="Usuarios con este rol.")
    class Meta:
        verbose_name = "Rol"; verbose_name_plural = "Roles"
    def __str__(self): return self.name


# Función para obtener la PK de la Unidad de Medida por defecto
def get_default_unidad_medida():
    # Asume que 'UN' (Unidad) es la U.M. base para artículos que no especifican.
    # Usamos get_or_create para evitar errores si la tabla está vacía.
    unidad, _ = UnidadMedida.objects.get_or_create(
        simbolo='UN',
        defaults={'nombre': 'Unidad'}
    )
    return unidad.pk

# <<< --- NUEVO MODELO PARA UNIDADES DE MEDIDA CONFIGURABLES --- >>>
class UnidadMedida(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    simbolo = models.CharField(max_length=10, unique=True)
    def __str__(self): return f"{self.nombre} ({self.simbolo})"
    class Meta:
        verbose_name = "Unidad de Medida"; verbose_name_plural = "Unidades de Medida"