# parametros/models.py

from django.db import models
from django.contrib.auth.models import Permission, User
from django.utils import timezone
from django.core.exceptions import ValidationError


# --- MODELOS DE CONFIGURACIÓN GENERAL ---

class TipoComprobante(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Comprobante")
    codigo_afip = models.CharField(max_length=3, blank=True, null=True, help_text="Código de AFIP si corresponde")
    letra = models.CharField(max_length=1)
    afecta_stock = models.BooleanField(default=False, help_text="Marcar si este comprobante modifica el stock.")

    def __str__(self): return self.nombre

    class Meta:
        verbose_name = "Tipo de Comprobante";
        verbose_name_plural = "Tipos de Comprobante"


class Contador(models.Model):
    nombre = models.CharField(max_length=100, unique=True, help_text="Nombre clave del contador, ej: 'codigo_articulo'")
    prefijo = models.CharField(max_length=5, default='P', help_text="Prefijo para el código, ej: 'P'")
    ultimo_valor = models.PositiveIntegerField(default=0, verbose_name="Último Valor Utilizado")

    def __str__(self): return f"Contador para {self.nombre}"

    class Meta:
        verbose_name = "Contador del Sistema";
        verbose_name_plural = "Contadores del Sistema"


class Moneda(models.Model):
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Nombre")
    simbolo = models.CharField(max_length=5, verbose_name="Símbolo")
    cotizacion = models.DecimalField(max_digits=10, decimal_places=2, help_text="Cotización respecto a la moneda base.",
                                     verbose_name="Cotización")
    es_base = models.BooleanField(default=False, help_text="Marcar si esta es la moneda base del sistema.",
                                  verbose_name="¿Es Moneda Base?")

    # MEJORA: El __str__ es más informativo para los selectores del admin.
    def __str__(self): return f"{self.simbolo} - {self.nombre}"

    def save(self, *args, **kwargs):
        if self.es_base: Moneda.objects.filter(es_base=True).exclude(pk=self.pk).update(es_base=False)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Moneda";
        verbose_name_plural = "Monedas"


# --- MODELOS GEOGRÁFICOS ---

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
    pais, _ = Pais.objects.get_or_create(por_defecto=True, defaults={'nombre': 'Argentina', 'codigo': 'AR'})
    return pais.pk


class Provincia(models.Model):
    codigo = models.CharField(max_length=3, verbose_name="Código")
    nombre = models.CharField(max_length=100)
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, default=get_default_pais)

    def __str__(self): return self.nombre

    class Meta:
        verbose_name_plural = "Provincias";
        unique_together = ('nombre', 'pais')


class Localidad(models.Model):
    nombre = models.CharField(max_length=255)
    codigo_postal = models.CharField(max_length=10)
    codigo_area_telefonico = models.CharField(max_length=10, blank=True, null=True, verbose_name="Código de Área")
    provincia = models.ForeignKey(Provincia, on_delete=models.PROTECT)

    def __str__(self): return f"{self.nombre} ({self.provincia.nombre})"

    class Meta:
        verbose_name_plural = "Localidades";
        unique_together = ('nombre', 'provincia')


# --- ARQUITECTURA DE IMPUESTOS ROBUSTA (NUEVA) ---

class CategoriaImpositiva(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)

    def __str__(self): return self.nombre

    class Meta:
        verbose_name = "Categoría Impositiva de Artículo"
        verbose_name_plural = "Categorías Impositivas de Artículos"


class Impuesto(models.Model):
    nombre = models.CharField(max_length=100, unique=True, help_text="Ej: IVA 21%, Impuestos Internos Tabaco")
    tasa = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="Tasa/Alícuota (%)")
    es_porcentaje = models.BooleanField(default=True,
                                        help_text="Marcar si la tasa es un porcentaje. Desmarcar si es un monto fijo.")
    APLICA_A_CHOICES = [('venta', 'Ventas'), ('compra', 'Compras'), ('ambos', 'Ambos')]
    aplica_a = models.CharField(max_length=10, choices=APLICA_A_CHOICES, default='ambos')
    vigente_desde = models.DateField(default=timezone.now)
    vigente_hasta = models.DateField(null=True, blank=True)

    def __str__(self): return f"{self.nombre} ({self.tasa}%)"

    class Meta:
        verbose_name = "Impuesto"
        verbose_name_plural = "Impuestos"


# --- ROLES Y UNIDADES DE MEDIDA ---

class Role(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Nombre del rol, ej: Vendedor")
    permissions = models.ManyToManyField(Permission, blank=True, help_text="Permisos generales asignados.")
    users = models.ManyToManyField(User, blank=True, related_name='roles', help_text="Usuarios con este rol.")

    def __str__(self): return self.name

    class Meta:
        verbose_name = "Rol";
        verbose_name_plural = "Roles"


class GrupoUnidadMedida(models.Model):
    nombre = models.CharField(max_length=50, unique=True, help_text="Ej: Peso, Volumen, Unidades Discretas")

    def __str__(self): return self.nombre

    class Meta:
        verbose_name = "Grupo de Unidad de Medida"
        verbose_name_plural = "Grupos de Unidades de Medida"


class UnidadMedida(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    simbolo = models.CharField(max_length=10, unique=True)
    grupo = models.ForeignKey(GrupoUnidadMedida, on_delete=models.PROTECT, null=True, blank=True)

    def __str__(self): return f"{self.nombre} ({self.simbolo})"

    class Meta:
        verbose_name = "Unidad de Medida";
        verbose_name_plural = "Unidades de Medida"


# --- FUNCIONES AUXILIARES ---

def get_default_unidad_medida():
    unidad, _ = UnidadMedida.objects.get_or_create(simbolo='UN', defaults={'nombre': 'Unidad'})
    return unidad.pk


def get_default_moneda_pk():
    moneda, _ = Moneda.objects.get_or_create(es_base=True, defaults={'nombre': 'Peso Argentino', 'simbolo': 'ARS',
                                                                     'cotizacion': 1.00})
    return moneda.pk


# --- NUEVA ARQUITECTURA DE EMISIÓN (SERIES / TALONARIOS) ---

class SerieDocumento(models.Model):
    """
    Define una secuencia de numeración y configuración operativa para un tipo de documento.
    Reemplaza el concepto de 'Talonario' rígido por uno flexible.
    """
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Serie",
                              help_text="Ej: Facturación Electrónica Sucursal Centro")

    tipo_comprobante = models.ForeignKey(TipoComprobante, on_delete=models.PROTECT,
                                         verbose_name="Tipo de Comprobante Legal")

    punto_venta = models.PositiveIntegerField(default=1, verbose_name="Punto de Venta (AFIP)")

    # Configuración de Numeración
    ultimo_numero = models.PositiveIntegerField(default=0, verbose_name="Último Número Usado")

    es_manual = models.BooleanField(default=False,
                                    verbose_name="¿Es numeración manual?",
                                    help_text="Si se marca, el usuario debe escribir el número (ej: facturas viejas). Si no, es automático.")

    # Automatización
    deposito_defecto = models.ForeignKey('inventario.Deposito', on_delete=models.SET_NULL,
                                         null=True, blank=True, verbose_name="Depósito por Defecto",
                                         help_text="Si se define, los movimientos de stock afectarán a este depósito automáticamente.")

    activo = models.BooleanField(default=True)

    # Auditoría
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Mostramos info útil: Nombre (PV: 0001 - Letra: A)
        return f"{self.nombre} (PV: {self.punto_venta:04d} - {self.tipo_comprobante.letra})"

    class Meta:
        verbose_name = "Serie de Documento (Talonario)"
        verbose_name_plural = "Series de Documentos (Talonarios)"
        # Evitamos duplicar el mismo tipo legal en el mismo punto de venta
        unique_together = ['tipo_comprobante', 'punto_venta']