# parametros/importers/contactos.py
from .base import BaseImporter
from entidades.models import Entidad, SituacionIVA
from ventas.models import Cliente
from compras.models import Proveedor
from parametros.models import CargaMasiva
from decimal import Decimal


class ContactoImporter(BaseImporter):
    def __init__(self, carga_id, tipo_contacto):
        super().__init__(carga_id)
        self.tipo_contacto = tipo_contacto  # 'CLIENTE' o 'PROVEEDOR'

        self.entidades_db = {}
        self.perfiles_db = {}
        self.situaciones_iva_db = {}

        self.entidades_a_actualizar = {}
        self.perfiles_a_actualizar = {}

        # Instancia vacía de Entidad para acceder a sus métodos de validación
        self.validador_entidad = Entidad()

    def pre_procesar(self, columnas):
        # Limpiamos asteriscos internos por seguridad
        columnas = [col.replace('*', '') for col in columnas]

        if 'cuit_o_dni' not in columnas and 'cuit' not in columnas and 'dni' not in columnas:
            raise ValueError("PLANTILLA INVÁLIDA: Falta columna identificatoria ('cuit_o_dni', 'cuit' o 'dni').")

        if 'razon_social' not in columnas or 'situacion_iva' not in columnas:
            raise ValueError("PLANTILLA INVÁLIDA: Faltan las columnas obligatorias 'razon_social' o 'situacion_iva'.")

        # Cachés rápidos
        self.entidades_db = {e.cuit: e for e in Entidad.objects.filter(cuit__isnull=False)}
        for e in Entidad.objects.filter(dni__isnull=False):
            self.entidades_db[f"DNI_{e.dni}"] = e

        # Inteligencia de mapeo de IVA (Buscable por código AFIP, código interno o nombre exacto)
        for s in SituacionIVA.objects.all():
            self.situaciones_iva_db[str(s.codigo_afip)] = s
            self.situaciones_iva_db[str(s.codigo).lower()] = s
            self.situaciones_iva_db[s.nombre.lower()] = s

        if self.tipo_contacto == 'CLIENTE':
            self.perfiles_db = {c.entidad_id: c for c in Cliente.objects.select_related('entidad').all()}
        else:
            self.perfiles_db = {p.entidad_id: p for p in Proveedor.objects.select_related('entidad').all()}

    def _parse_decimal(self, value, default='0'):
        try:
            return Decimal(str(value).replace(',', '.').strip() or default)
        except:
            return Decimal(default)

    def _parse_bool(self, value):
        return str(value).strip().upper() in ['S', 'SI', '1', 'TRUE', 'Y', 'YES']

    def procesar_fila(self, fila, num_fila):
        # Limpieza de asteriscos para lectura segura
        fila_limpia = {k.replace('*', ''): v for k, v in fila.items()}

        cuit_raw = str(fila_limpia.get('cuit_o_dni', fila_limpia.get('cuit', ''))).strip()
        cuit = cuit_raw.replace('-', '').replace(' ', '')
        dni = str(fila_limpia.get('dni', '')).strip()

        # Inteligencia DNI/CUIT: Si envían 8 números o menos, asumimos que es DNI
        if len(cuit) <= 8 and cuit.isdigit():
            dni = cuit
            cuit = ''

        razon_social = str(fila_limpia.get('razon_social', '')).strip()
        situacion_iva_str = str(fila_limpia.get('situacion_iva', '')).strip().lower()
        sexo_str = str(fila_limpia.get('sexo', '')).strip().upper()[:1]  # M, F, J
        email = str(fila_limpia.get('email', '')).strip()
        direccion = str(fila_limpia.get('direccion', '')).strip()  # Agregamos la dirección que solicitaste

        # --- 1. CONTROLES ESTRICTOS ---
        if not cuit and not dni:
            raise ValueError("Debe indicar un CUIT o DNI válido.")

        # Validación nativa usando el algoritmo Módulo 11 de AFIP de tu modelo Entidad
        if cuit and not self.validador_entidad._cuit_es_valido(cuit):
            raise ValueError(f"El CUIT/CUIL '{cuit_raw}' es INVÁLIDO según el algoritmo AFIP Módulo 11.")

        if not razon_social:
            raise ValueError("La Razón Social es obligatoria.")

        sit_iva = self.situaciones_iva_db.get(situacion_iva_str)
        if not sit_iva:
            # Fallback seguro a Consumidor Final (AFIP 5)
            sit_iva = self.situaciones_iva_db.get('5')
            if not sit_iva:
                raise ValueError(f"No se reconoció la Situación IVA '{situacion_iva_str}'.")

        # --- 2. GESTIÓN DE ENTIDAD ---
        entidad = self.entidades_db.get(cuit) if cuit else self.entidades_db.get(f"DNI_{dni}")

        if entidad:
            if self.modo == CargaMasiva.Modo.CREAR:
                raise ValueError(f"La Entidad ya existe (Modo: Solo Crear).")

            entidad.razon_social = razon_social
            entidad.situacion_iva = sit_iva
            if email: entidad.email = email
            if sexo_str in ['M', 'F', 'J']: entidad.sexo = sexo_str
            self.entidades_a_actualizar[entidad.pk] = entidad
            # Nota: La dirección no la actualizamos aquí porque en tu modelo la dirección va en `EntidadDomicilio`.
            # Lo omitimos por simplicidad masiva, pero se podría agregar.
        else:
            if self.modo == CargaMasiva.Modo.ACTUALIZAR:
                raise ValueError(f"La Entidad no existe (Modo: Solo Actualizar).")

            # Al instanciarla y guardarla, se disparará tu método save() en models.py
            # que genera el CUIL automáticamente si enviaste DNI + Sexo.
            entidad = Entidad(
                cuit=cuit if cuit else None,
                dni=dni if dni else None,
                razon_social=razon_social,
                situacion_iva=sit_iva,
                email=email,
                sexo=sexo_str if sexo_str in ['M', 'F', 'J'] else ('J' if cuit and cuit.startswith('30') else 'M')
            )
            entidad.save()

            if entidad.cuit: self.entidades_db[entidad.cuit] = entidad
            if entidad.dni: self.entidades_db[f"DNI_{entidad.dni}"] = entidad

        # --- 3. GESTIÓN DEL PERFIL ESPECÍFICO ---
        perfil = self.perfiles_db.get(entidad.pk)

        if self.tipo_contacto == 'CLIENTE':
            if perfil:
                perfil.nombre_fantasia = fila_limpia.get('nombre_fantasia', perfil.nombre_fantasia)
                cat = fila_limpia.get('categoria', '').strip().upper()[:3]
                if cat: perfil.categoria = cat
                perfil.limite_credito = self._parse_decimal(fila_limpia.get('limite_credito'), perfil.limite_credito)
                perfil.descuento_base = self._parse_decimal(fila_limpia.get('descuento_base'), perfil.descuento_base)
                perfil.dias_vencimiento = int(
                    self._parse_decimal(fila_limpia.get('dias_vencimiento'), perfil.dias_vencimiento))
                perfil.zona = fila_limpia.get('zona', perfil.zona)

                if 'permite_cta_cte' in fila_limpia:
                    perfil.permite_cta_cte = self._parse_bool(fila_limpia['permite_cta_cte'])

                perfil.contacto_nombre = fila_limpia.get('contacto_nombre', perfil.contacto_nombre)
                perfil.contacto_telefono = fila_limpia.get('contacto_telefono', perfil.contacto_telefono)
                perfil.observaciones = fila_limpia.get('observaciones', perfil.observaciones)

                self.perfiles_a_actualizar[perfil.pk] = perfil
            else:
                cat = fila_limpia.get('categoria', 'MIN').strip().upper()[:3]
                nuevo_cliente = Cliente(
                    entidad=entidad,
                    nombre_fantasia=fila_limpia.get('nombre_fantasia', ''),
                    categoria=cat if cat else 'MIN',
                    limite_credito=self._parse_decimal(fila_limpia.get('limite_credito', 0)),
                    descuento_base=self._parse_decimal(fila_limpia.get('descuento_base', 0)),
                    dias_vencimiento=int(self._parse_decimal(fila_limpia.get('dias_vencimiento', 0))),
                    zona=fila_limpia.get('zona', ''),
                    permite_cta_cte=self._parse_bool(fila_limpia.get('permite_cta_cte', 'N')),
                    contacto_nombre=fila_limpia.get('contacto_nombre', ''),
                    contacto_telefono=fila_limpia.get('contacto_telefono', ''),
                    observaciones=fila_limpia.get('observaciones', '')
                )
                nuevo_cliente.save()
                self.perfiles_db[entidad.pk] = nuevo_cliente

        elif self.tipo_contacto == 'PROVEEDOR':
            if perfil:
                perfil.nombre_fantasia = fila_limpia.get('nombre_fantasia', perfil.nombre_fantasia)
                perfil.limite_credito = self._parse_decimal(fila_limpia.get('limite_credito'), perfil.limite_credito)
                perfil.plazo_pago_dias = int(
                    self._parse_decimal(fila_limpia.get('plazo_pago_dias'), perfil.plazo_pago_dias))
                perfil.descuento_compra = self._parse_decimal(fila_limpia.get('descuento_compra'),
                                                              perfil.descuento_compra)
                perfil.situacion_iibb = fila_limpia.get('situacion_iibb', perfil.situacion_iibb)
                perfil.nro_iibb = fila_limpia.get('nro_iibb', perfil.nro_iibb)
                perfil.banco_nombre = fila_limpia.get('banco_nombre', perfil.banco_nombre)
                perfil.banco_cbu = fila_limpia.get('banco_cbu', perfil.banco_cbu)
                perfil.contacto_nombre = fila_limpia.get('contacto_nombre', perfil.contacto_nombre)
                perfil.contacto_telefono = fila_limpia.get('contacto_telefono', perfil.contacto_telefono)
                perfil.observaciones = fila_limpia.get('observaciones', perfil.observaciones)
                self.perfiles_a_actualizar[perfil.pk] = perfil
            else:
                nuevo_proveedor = Proveedor(
                    entidad=entidad,
                    nombre_fantasia=fila_limpia.get('nombre_fantasia', ''),
                    limite_credito=self._parse_decimal(fila_limpia.get('limite_credito', 0)),
                    plazo_pago_dias=int(self._parse_decimal(fila_limpia.get('plazo_pago_dias', 0))),
                    descuento_compra=self._parse_decimal(fila_limpia.get('descuento_compra', 0)),
                    situacion_iibb=fila_limpia.get('situacion_iibb', ''),
                    nro_iibb=fila_limpia.get('nro_iibb', ''),
                    banco_nombre=fila_limpia.get('banco_nombre', ''),
                    banco_cbu=fila_limpia.get('banco_cbu', ''),
                    contacto_nombre=fila_limpia.get('contacto_nombre', ''),
                    contacto_telefono=fila_limpia.get('contacto_telefono', ''),
                    observaciones=fila_limpia.get('observaciones', '')
                )
                nuevo_proveedor.save()
                self.perfiles_db[entidad.pk] = nuevo_proveedor

    def post_procesar(self):
        # VOLCADO MASIVO
        if self.entidades_a_actualizar:
            Entidad.objects.bulk_update(
                self.entidades_a_actualizar.values(),
                ['razon_social', 'situacion_iva', 'email', 'sexo'],
                batch_size=500
            )

        if self.perfiles_a_actualizar:
            if self.tipo_contacto == 'CLIENTE':
                Cliente.objects.bulk_update(
                    self.perfiles_a_actualizar.values(),
                    ['nombre_fantasia', 'categoria', 'limite_credito', 'descuento_base',
                     'dias_vencimiento', 'zona', 'permite_cta_cte', 'contacto_nombre',
                     'contacto_telefono', 'observaciones'],
                    batch_size=500
                )
            elif self.tipo_contacto == 'PROVEEDOR':
                Proveedor.objects.bulk_update(
                    self.perfiles_a_actualizar.values(),
                    ['nombre_fantasia', 'limite_credito', 'plazo_pago_dias', 'descuento_compra',
                     'situacion_iibb', 'nro_iibb', 'banco_nombre', 'banco_cbu',
                     'contacto_nombre', 'contacto_telefono', 'observaciones'],
                    batch_size=500
                )