# parametros/models.py

from django.db import models
from django.contrib.auth.models import Permission, User
from django.utils import timezone
from django.core.exceptions import ValidationError
from cryptography import x509
from cryptography.hazmat.backends import default_backend


# --- MODELOS DE CONFIGURACIÓN GENERAL ---

class TipoComprobante(models.Model):
    # Definimos las opciones para listas desplegables
    CLASE_CHOICES = [
        ('V', 'Ventas (Cliente)'),
        ('C', 'Compras (Proveedor)'),
        ('F', 'Fondos / Caja'),
        ('S', 'Stock Interno'),
    ]

    SIGNO_STOCK_CHOICES = [
        (1, 'Suma Stock (+)'),
        (-1, 'Resta Stock (-)'),
        (0, 'No Mueve Stock'),
    ]

    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Comprobante")
    codigo_afip = models.CharField(max_length=3, blank=True, null=True, help_text="Código de AFIP si corresponde")
    letra = models.CharField(max_length=1, blank=True, null=True, help_text="A, B, C, X, R...")

    # --- NUEVOS CAMPOS DE COMPORTAMIENTO ---

    # 1. Clasificación
    clase = models.CharField(max_length=1, choices=CLASE_CHOICES, default='V', verbose_name="Clase de Comprobante")

    # 2. Comportamiento de Stock
    mueve_stock = models.BooleanField(default=False, verbose_name="¿Es Movimiento de Stock?",
                                      help_text="Interruptor general. Si está apagado, ignora las opciones de abajo.")

    signo_stock = models.IntegerField(choices=SIGNO_STOCK_CHOICES, default=0, verbose_name="Sentido del Stock",
                                      help_text="Ej: Venta resta (-1), Compra suma (+1), Presupuesto (0)")

    # === NUEVA LÓGICA GRANULAR ===
    afecta_stock_fisico = models.BooleanField(
        default=True,
        verbose_name="¿Mueve Stock Físico (Real)?",
        help_text="Si se marca, aumentará o disminuirá la cantidad real en estantería."
    )

    afecta_stock_comprometido = models.BooleanField(
        default=False,
        verbose_name="¿Mueve Stock Comprometido (Reservas)?",
        help_text="Si se marca, aumentará o disminuirá la columna de 'Reservas/Compromisos'."
    )

    # 3. Comportamiento Financiero
    mueve_cta_cte = models.BooleanField(default=True, verbose_name="¿Afecta Cta. Cte?",
                                        help_text="Si afecta el saldo del cliente/proveedor (Deuda/Crédito)")
    mueve_caja = models.BooleanField(default=False, verbose_name="¿Mueve Caja?",
                                     help_text="Si mueve dinero real inmediatamente (ej: Recibo, Ticket Contado)")

    # 4. Comportamiento Fiscal / Técnico
    es_fiscal = models.BooleanField(
        default=True,
        verbose_name="Es Fiscal / Electrónico",
        help_text="Si está activo, este comprobante pedirá CAE (Esquema Electrónico)."
    )
    numeracion_automatica = models.BooleanField(default=True,
                                                help_text="Si el sistema asigna el número (False para facturas de proveedores)")

    def __str__(self):
        return f"{self.nombre} ({self.letra or 'X'})"

    class Meta:
        verbose_name = "Tipo de Comprobante"
        verbose_name_plural = "Tipos de Comprobante"
        ordering = ['nombre']

    @property
    def es_nota_credito(self):
        """
        Devuelve True si el código AFIP corresponde a una Nota de Crédito.
        Códigos comunes: 003 (A), 008 (B), 013 (C), 020 (A Mipyme), etc.
        """
        codigos_nc = ['003', '008', '013', '020', '021', '025', '112', '117']
        if self.codigo_afip:
            return self.codigo_afip in codigos_nc

        # Fallback por nombre si no hay código AFIP
        return 'NOTA DE CREDITO' in self.nombre.upper() or 'N/C' in self.nombre.upper()


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


# --- ARQUITECTURA DE IMPUESTOS ---

class CategoriaImpositiva(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    codigo_afip = models.IntegerField(
        verbose_name="Código AFIP (Receptor)",
        help_text="1=IVA Resp. Inscripto, 5=Consumidor Final, 6=Monotributo, etc. (Ver Tabla AFIP)",
        default=5
    )
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

    solicitar_cae_automaticamente = models.BooleanField(
        default=False,
        verbose_name="Solicitar CAE Automático",
        help_text="Si se activa, el sistema intentará conectar con AFIP inmediatamente al confirmar la venta. Si falla, quedará pendiente."
    )

    es_manual = models.BooleanField(default=False,
                                    verbose_name="¿Es numeración manual?",
                                    help_text="Si se marca, el usuario escribe el número (factureros papel). Si no, el sistema numera y/o pide CAE.")

    # Automatización
    deposito_defecto = models.ForeignKey('inventario.Deposito', on_delete=models.SET_NULL,
                                         null=True, blank=True, verbose_name="Depósito por Defecto",
                                         help_text="Si se define, los movimientos de stock afectarán a este depósito automáticamente.")

    activo = models.BooleanField(default=True)

    # Auditoría
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    diseno_impresion = models.ForeignKey(
        'ventas.DisenoImpresion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Diseño de Impresión (Template)",
        help_text="Si se deja vacío, usa el diseño estándar."
    )

    def __str__(self):
        # Mostramos info útil: Nombre (PV: 0001 - Letra: A)
        return f"{self.nombre} (PV: {self.punto_venta:04d} - {self.tipo_comprobante.letra})"

    class Meta:
        verbose_name = "Serie de Documento (Talonario)"
        verbose_name_plural = "Series de Documentos (Talonarios)"
        # Evitamos duplicar el mismo tipo legal en el mismo punto de venta
        unique_together = ['tipo_comprobante', 'punto_venta']


# --- CONFIGURACIÓN DE LA EMPRESA (SINGLETON) ---

class ConfiguracionEmpresa(models.Model):
    """
    Datos fiscales y de configuración visual de la empresa (Tenant).
    Solo puede existir UNA instancia por cliente.
    """
    entidad = models.OneToOneField(
        'entidades.Entidad',
        on_delete=models.PROTECT,
        verbose_name="Entidad Fiscal"
    )

    logo = models.ImageField(upload_to='logos_empresa/', null=True, blank=True)
    nombre_fantasia = models.CharField(max_length=200, help_text="Nombre comercial para el ticket")

    inicio_actividades = models.DateField(verbose_name="Inicio de Actividades")
    ingresos_brutos = models.CharField(max_length=50, verbose_name="N° Ingresos Brutos")

    moneda_principal = models.ForeignKey(
        'Moneda',
        on_delete=models.PROTECT,
        related_name='configuracion_principal'
    )

    usar_factura_electronica = models.BooleanField(
        default=True,
        verbose_name="Habilitar Factura Electrónica",
        help_text="Si está activo, el sistema intentará conectar con AFIP."
    )

    modo_facturacion = models.CharField(
        max_length=10,
        choices=[('AUTO', 'Automático (Al confirmar venta)'), ('MANUAL', 'Manual (A pedido del usuario)')],
        default='MANUAL',
        verbose_name="Modo de Autorización (CAE)",
        help_text="Automático: Intenta obtener CAE al guardar. Manual: Requiere acción del usuario."
    )

    class Meta:
        verbose_name = "Configuración de Empresa"
        verbose_name_plural = "Configuración de Empresa"

    def __str__(self):
        return f"Configuración: {self.nombre_fantasia}"

    def clean(self):
        """Valida que no exista ya una configuración creada (Singleton)."""
        model = self.__class__
        if not self.pk and model.objects.exists():
            raise ValidationError("Ya existe una Configuración para esta empresa. Solo se permite una.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# --- INTEGRACIÓN AFIP ---

class AfipCertificado(models.Model):
    """
    Permite al usuario subir y gestionar sus propios certificados digitales.
    Soporta rotación (historial) y múltiples entornos (Homologación/Producción).
    """
    nombre = models.CharField(max_length=100, help_text="Ej: Certificado 2024-2026")
    certificado = models.FileField(upload_to='afip/certs/', verbose_name="Certificado (.crt)")
    clave_privada = models.FileField(upload_to='afip/keys/', verbose_name="Clave Privada (.key)")
    cuit = models.CharField(max_length=11, help_text="CUIT de la empresa emisora (sin guiones)")

    # Automatización Enterprise
    vencimiento = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de Vencimiento",
        help_text="Detectado automáticamente desde el archivo .crt"
    )

    es_produccion = models.BooleanField(
        default=False,
        verbose_name="¿Es Producción?",
        help_text="Si está marcado, emitirá facturas REALES. Si no, usa servidores de prueba."
    )

    activo = models.BooleanField(default=True, help_text="Desactivar certificados vencidos.")
    subido_el = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        estado = "ACTIVO" if self.activo else "INACTIVO"
        env = "PRODUCCIÓN" if self.es_produccion else "TEST"
        return f"{self.nombre} ({env}) [{estado}]"

    def save(self, *args, **kwargs):
        """
        Lógica Enterprise:
        Al guardar, abrimos el archivo .crt, lo parseamos criptográficamente
        y extraemos la fecha de vencimiento real para evitar errores humanos.
        """
        if self.certificado:
            try:
                # 1. Leemos el archivo (funciona tanto para subidas nuevas en memoria como archivos en disco)
                self.certificado.open('rb')
                cert_bytes = self.certificado.read()

                # IMPORTANTE: Rebobinar el archivo para que Django pueda guardarlo después en disco/S3
                self.certificado.seek(0)

                # 2. Usamos la librería 'cryptography' para parsear el X.509
                cert = x509.load_pem_x509_certificate(cert_bytes, default_backend())

                # 3. Extraemos la fecha 'not_valid_after' y la asignamos
                # La librería devuelve un datetime, lo convertimos a date
                self.vencimiento = cert.not_valid_after.date()

                # (Opcional) Podrías extraer también el CUIT del "Subject" del certificado para validarlo
                # subject = cert.subject.rfc4514_string()

            except Exception as e:
                # Si el archivo no es un certificado válido o falla la lectura,
                # no rompemos el guardado, pero dejamos el vencimiento vacío o lo logueamos.
                print(f"⚠️ Alerta: No se pudo leer el vencimiento del certificado: {e}")

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Certificado Digital AFIP"
        verbose_name_plural = "Certificados Digitales AFIP"


class AfipToken(models.Model):
    """
    Tabla técnica interna (invisible al usuario) para cachear el Token de acceso.
    Evita pedir login a AFIP en cada factura.
    """
    certificado = models.ForeignKey(AfipCertificado, on_delete=models.CASCADE)
    service = models.CharField(max_length=10, help_text="Ej: wsfe")
    unique_id = models.CharField(max_length=100, help_text="Identificador único del request")
    token = models.TextField()
    sign = models.TextField()
    generado = models.DateTimeField(auto_now_add=True)
    expira = models.DateTimeField()

    def __str__(self):
        return f"Token {self.service} (Expira: {self.expira})"

    @property
    def es_valido(self):
        # Damos un margen de seguridad de 10 minutos antes de que expire
        margin = timezone.timedelta(minutes=10)
        return timezone.now() < (self.expira - margin)


class ConfiguracionSMTP(models.Model):
    PROVEEDORES = [
        ('smtp.gmail.com', 'Gmail'),
        ('smtp.office365.com', 'Outlook/Office365'),
        ('smtp.mail.yahoo.com', 'Yahoo'),
        ('custom', 'Otro / Personalizado'),
    ]

    nombre = models.CharField(max_length=50, default="Principal", help_text="Ej: Envío Facturas")
    host = models.CharField(max_length=100, default='smtp.gmail.com', choices=PROVEEDORES)
    host_custom = models.CharField(max_length=100, blank=True, null=True, verbose_name="Host Personalizado",
                                   help_text="Llenar solo si eligió 'Otro'")
    puerto = models.IntegerField(default=587, help_text="587 para TLS, 465 para SSL")
    usuario = models.CharField(max_length=100, help_text="Tu correo electrónico")
    password = models.CharField(max_length=100, verbose_name="Contraseña / App Password")
    usar_tls = models.BooleanField(default=True, verbose_name="Usar TLS")
    usar_ssl = models.BooleanField(default=False, verbose_name="Usar SSL")
    email_from = models.EmailField(verbose_name="Dirección 'Desde'", help_text="Generalmente igual al usuario")

    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"SMTP: {self.usuario}"

    class Meta:
        verbose_name = "Configuración de Correo"
        verbose_name_plural = "Configuraciones de Correo"