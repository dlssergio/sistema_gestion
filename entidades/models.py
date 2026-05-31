from django.db import models
from django.core.exceptions import ValidationError


class TipoDireccion(models.TextChoices):
    FISCAL = 'FISCAL', 'Fiscal'
    ENTREGA = 'ENTREGA', 'Entrega'
    COMERCIAL = 'COMERCIAL', 'Comercial'
    OTRA = 'OTRA', 'Otra'


class TipoPersona(models.TextChoices):
    FISICA = 'F', 'Persona Física'
    JURIDICA = 'J', 'Persona Jurídica'


class TipoDocumento(models.TextChoices):
    DNI = 'DNI', 'DNI'
    CUIT = 'CUIT', 'CUIT/CUIL'
    OTRO = 'OTRO', 'Otro'


class SituacionIVA(models.Model):
    codigo = models.CharField(max_length=3, unique=True, verbose_name="Código")
    nombre = models.CharField(max_length=100, unique=True)
    codigo_afip = models.IntegerField(
        verbose_name="Código AFIP (Receptor)",
        help_text="1=IVA Resp. Inscripto, 5=Consumidor Final, 6=Monotributo",
        default=5
    )
    mostrar_precio_con_iva = models.BooleanField(
        default=False,
        verbose_name="Mostrar precio con IVA en venta",
        help_text="Si está activo, el POS muestra precios con IVA incluido para clientes con esta situación (ej: Consumidor Final)."
    )

    def __str__(self):
        return f"({self.codigo}) {self.nombre}"

    class Meta:
        verbose_name = "Situación frente al IVA"
        verbose_name_plural = "Situaciones frente al IVA"


class Entidad(models.Model):
    class Sexo(models.TextChoices):
        MASCULINO = 'M', 'Masculino'
        FEMENINO = 'F', 'Femenino'
        JURIDICA = 'J', 'Persona Jurídica'

    razon_social = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Razón Social / Nombre y Apellido"
    )

    tipo_persona = models.CharField(
        max_length=1,
        choices=TipoPersona.choices,
        default=TipoPersona.JURIDICA,
        verbose_name="Tipo de Persona"
    )

    tipo_documento = models.CharField(
        max_length=10,
        choices=TipoDocumento.choices,
        default=TipoDocumento.CUIT,
        verbose_name="Tipo de Documento"
    )

    sexo = models.CharField(
        max_length=1,
        choices=Sexo.choices,
        blank=True,
        null=True
    )

    dni = models.CharField(
        max_length=8,
        blank=True,
        null=True,
        verbose_name="DNI"
    )

    cuit = models.CharField(
        max_length=13,
        unique=True,
        blank=True,
        null=True,
        verbose_name="CUIT/CUIL"
    )

    situacion_iva = models.ForeignKey(
        SituacionIVA,
        on_delete=models.PROTECT,
        verbose_name="Situación IVA"
    )

    email = models.EmailField(
        max_length=254,
        blank=True,
        null=True,
        verbose_name="Email Facturación"
    )

    def _cuit_es_valido(self, cuit):
        if not isinstance(cuit, str) or len(cuit) != 11 or not cuit.isdigit():
            return False

        base = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        cuit_sin_verificador = cuit[:-1]
        verificador = int(cuit[-1])

        suma = sum(int(cuit_sin_verificador[i]) * base[i] for i in range(10))
        resto = suma % 11
        digito_esperado = 11 - resto

        if digito_esperado == 11:
            digito_esperado = 0
        elif digito_esperado == 10:
            digito_esperado = 9

        return verificador == digito_esperado

    def _generar_cuil(self, dni, sexo):
        if not dni or not sexo or len(dni) != 8:
            return None

        if sexo == self.Sexo.MASCULINO:
            prefijo = "20"
        elif sexo == self.Sexo.FEMENINO:
            prefijo = "27"
        else:
            return None

        base = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        numero_sin_verificador = prefijo + dni
        suma = sum(int(numero_sin_verificador[i]) * base[i] for i in range(10))
        resto = suma % 11
        verificador = 11 - resto

        if verificador == 11:
            verificador = 0
        elif verificador == 10:
            prefijo = "23"
            numero_sin_verificador = prefijo + dni
            suma = sum(int(numero_sin_verificador[i]) * base[i] for i in range(10))
            resto = suma % 11
            verificador = 11 - resto
            if verificador == 11:
                verificador = 0

        return f"{prefijo}{dni}{verificador}"

    def clean(self):
        super().clean()

        cuit_normalizado = (self.cuit or "").replace("-", "").strip()
        if cuit_normalizado and not self._cuit_es_valido(cuit_normalizado):
            raise ValidationError({'cuit': 'El CUIT/CUIL ingresado no es válido.'})

    def save(self, *args, **kwargs):
        if self.cuit:
            self.cuit = self.cuit.replace("-", "").strip()

        if self.sexo == self.Sexo.JURIDICA:
            self.tipo_persona = TipoPersona.JURIDICA
        elif self.sexo in (self.Sexo.MASCULINO, self.Sexo.FEMENINO):
            self.tipo_persona = TipoPersona.FISICA

        if self.tipo_persona == TipoPersona.FISICA:
            self.tipo_documento = TipoDocumento.DNI
        elif self.tipo_persona == TipoPersona.JURIDICA:
            self.tipo_documento = TipoDocumento.CUIT

        if not self.cuit and self.dni and self.sexo in (self.Sexo.MASCULINO, self.Sexo.FEMENINO):
            self.cuit = self._generar_cuil(self.dni, self.sexo)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.razon_social

    class Meta:
        verbose_name = "Entidad"
        verbose_name_plural = "Entidades"


class EntidadDomicilio(models.Model):
    entidad = models.ForeignKey(
        Entidad,
        related_name='domicilios',
        on_delete=models.CASCADE
    )
    calle = models.CharField(max_length=255)
    numero = models.CharField(max_length=20, blank=True, null=True)
    piso = models.CharField(max_length=10, blank=True, null=True)
    dpto = models.CharField(max_length=10, blank=True, null=True)
    localidad = models.CharField(max_length=100, blank=True, null=True)
    tipo_direccion = models.CharField(
        max_length=20,
        choices=TipoDireccion.choices,
        default=TipoDireccion.COMERCIAL
    )
    es_principal = models.BooleanField(default=False)
    referencia = models.CharField(max_length=255, blank=True, null=True)
    latitud = models.FloatField(null=True, blank=True)
    longitud = models.FloatField(null=True, blank=True)

    def __str__(self):
        base = f"{self.calle or ''} {self.numero or ''}".strip()
        if self.localidad:
            return f"{base} - {self.localidad}"
        return base or "Domicilio"

    class Meta:
        verbose_name = "Domicilio"
        verbose_name_plural = "Domicilios"


class EntidadTelefono(models.Model):
    TIPO_CHOICES = [
        ('FIJO', 'Fijo'),
        ('CEL', 'Celular'),
        ('FAX', 'Fax'),
        ('COM', 'Comercial'),
    ]

    entidad = models.ForeignKey(
        Entidad,
        related_name='telefonos',
        on_delete=models.CASCADE
    )
    numero = models.CharField(max_length=50, verbose_name="Número")
    tipo = models.CharField(max_length=4, choices=TIPO_CHOICES, default='CEL')

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.numero}"

    class Meta:
        verbose_name = "Teléfono"
        verbose_name_plural = "Teléfonos"


class EntidadEmail(models.Model):
    entidad = models.ForeignKey(
        Entidad,
        related_name='emails_secundarios',
        on_delete=models.CASCADE
    )
    email = models.EmailField()
    tipo = models.CharField(
        max_length=50,
        default="Secundario",
        help_text="Ej: Administración, Compras"
    )

    def __str__(self):
        return self.email

    class Meta:
        verbose_name = "Email Adicional"
        verbose_name_plural = "Emails Adicionales"