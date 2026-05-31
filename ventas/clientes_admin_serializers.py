# clientes_admin_serializers.py
from django.contrib.auth import get_user_model
from django.db.models import Sum
from rest_framework import serializers

from entidades.models import (
    Entidad,
    EntidadDomicilio,
    EntidadTelefono,
    EntidadEmail,
    SituacionIVA,
)
from ventas.models import Cliente, PriceList, ComprobanteVenta


User = get_user_model()


class SituacionIVAOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SituacionIVA
        fields = ['id', 'codigo', 'nombre', 'codigo_afip']


class PriceListOptionSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = PriceList
        fields = ['id', 'label']

    def get_label(self, obj):
        parts = []
        if hasattr(obj, 'name'):
            parts.append(obj.name)
        elif hasattr(obj, 'nombre'):
            parts.append(obj.nombre)
        else:
            parts.append(str(obj))

        discount = getattr(obj, 'discount_percentage', None)
        if discount not in (None, ''):
            try:
                parts.append(f"{discount}%")
            except Exception:
                pass

        return " · ".join(parts)


class UserOptionSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'label']

    def get_label(self, obj):
        full_name = ''
        if hasattr(obj, 'get_full_name'):
            full_name = (obj.get_full_name() or '').strip()
        if full_name:
            return full_name
        return getattr(obj, 'username', str(obj.pk))


class DomicilioSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntidadDomicilio
        fields = [
            'id',
            'calle',
            'numero',
            'piso',
            'dpto',
            'localidad',
            'tipo_direccion',
            'es_principal',
            'referencia',
            'latitud',
            'longitud',
        ]


class TelefonoSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    numero = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tipo = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='CEL')


class EmailSecundarioSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    tipo = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='Secundario')


class ClienteAdminListSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='pk', read_only=True)
    razon_social = serializers.SerializerMethodField()
    cuit = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    situacion_iva = serializers.SerializerMethodField()
    categoria_label = serializers.SerializerMethodField()
    vendedor_label = serializers.SerializerMethodField()
    price_list_label = serializers.SerializerMethodField()
    saldo = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = [
            'id',
            'codigo_cliente',
            'razon_social',
            'nombre_fantasia',
            'cuit',
            'email',
            'situacion_iva',
            'categoria',
            'categoria_label',
            'zona',
            'permite_cta_cte',
            'limite_credito',
            'dias_vencimiento',
            'descuento_base',
            'contacto_nombre',
            'contacto_email',
            'contacto_telefono',
            'vendedor_label',
            'price_list_label',
            'saldo',
            'fecha_alta',
            'esta_activo',
            'observaciones',
        ]

    def get_razon_social(self, obj):
        try:
            return obj.entidad.razon_social
        except Exception:
            return ''

    def get_cuit(self, obj):
        try:
            return obj.entidad.cuit
        except Exception:
            return None

    def get_email(self, obj):
        try:
            return obj.entidad.email
        except Exception:
            return None

    def get_situacion_iva(self, obj):
        s = getattr(obj.entidad, 'situacion_iva', None)
        if not s:
            return None
        return {
            'id': s.id,
            'codigo': getattr(s, 'codigo', ''),
            'nombre': getattr(s, 'nombre', ''),
        }

    def get_categoria_label(self, obj):
        try:
            return obj.get_categoria_display()
        except Exception:
            return obj.categoria

    def get_vendedor_label(self, obj):
        vendedor = getattr(obj, 'vendedor', None)
        if not vendedor:
            return None
        full_name = ''
        if hasattr(vendedor, 'get_full_name'):
            full_name = (vendedor.get_full_name() or '').strip()
        return full_name or getattr(vendedor, 'username', str(vendedor.pk))

    def get_price_list_label(self, obj):
        price_list = getattr(obj, 'price_list', None)
        if not price_list:
            return None
        if hasattr(price_list, 'name'):
            return price_list.name
        if hasattr(price_list, 'nombre'):
            return price_list.nombre
        return str(price_list)

    def get_saldo(self, obj):
        try:
            result = ComprobanteVenta.objects.filter(
                cliente=obj,
                estado=ComprobanteVenta.Estado.CONFIRMADO,
                condicion_venta=ComprobanteVenta.CondicionVenta.CTA_CTE,
            ).aggregate(total=Sum('saldo_pendiente'))
            return float(result['total'] or 0)
        except Exception:
            return 0.0


class ClienteAdminDetailSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='pk', read_only=True)
    entidad = serializers.SerializerMethodField()
    categoria_label = serializers.SerializerMethodField()
    vendedor = serializers.SerializerMethodField()
    price_list = serializers.SerializerMethodField()
    saldo = serializers.SerializerMethodField()
    domicilios = serializers.SerializerMethodField()
    telefonos = serializers.SerializerMethodField()
    emails_secundarios = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = [
            'id',
            'entidad',
            'codigo_cliente',
            'nombre_fantasia',
            'categoria',
            'categoria_label',
            'price_list',
            'descuento_base',
            'vendedor',
            'zona',
            'permite_cta_cte',
            'limite_credito',
            'dias_vencimiento',
            'contacto_nombre',
            'contacto_email',
            'contacto_telefono',
            'saldo',
            'fecha_alta',
            'esta_activo',
            'observaciones',
            'domicilios',
            'telefonos',
            'emails_secundarios',
        ]

    def get_entidad(self, obj):
        e = obj.entidad
        return {
            'id': e.id,
            'razon_social': e.razon_social,
            'sexo': getattr(e, 'sexo', None),
            'tipo_persona': getattr(e, 'tipo_persona', None),
            'tipo_documento': getattr(e, 'tipo_documento', None),
            'dni': getattr(e, 'dni', None),
            'cuit': getattr(e, 'cuit', None),
            'email': getattr(e, 'email', None),
            'situacion_iva': (
                {
                    'id': e.situacion_iva.id,
                    'codigo': getattr(e.situacion_iva, 'codigo', ''),
                    'nombre': getattr(e.situacion_iva, 'nombre', ''),
                }
                if getattr(e, 'situacion_iva', None) else None
            ),
        }

    def get_categoria_label(self, obj):
        try:
            return obj.get_categoria_display()
        except Exception:
            return obj.categoria

    def get_vendedor(self, obj):
        vendedor = getattr(obj, 'vendedor', None)
        if not vendedor:
            return None
        full_name = ''
        if hasattr(vendedor, 'get_full_name'):
            full_name = (vendedor.get_full_name() or '').strip()
        return {
            'id': vendedor.pk,
            'label': full_name or getattr(vendedor, 'username', str(vendedor.pk))
        }

    def get_price_list(self, obj):
        price_list = getattr(obj, 'price_list', None)
        if not price_list:
            return None
        label = getattr(price_list, 'name', None) or getattr(price_list, 'nombre', None) or str(price_list)
        return {
            'id': price_list.pk,
            'label': label,
        }

    def get_saldo(self, obj):
        try:
            result = ComprobanteVenta.objects.filter(
                cliente=obj,
                estado=ComprobanteVenta.Estado.CONFIRMADO,
                condicion_venta=ComprobanteVenta.CondicionVenta.CTA_CTE,
            ).aggregate(total=Sum('saldo_pendiente'))
            return float(result['total'] or 0)
        except Exception:
            return 0.0

    def get_domicilios(self, obj):
        try:
            qs = obj.entidad.domicilios.all().order_by('-es_principal', 'id')
            return DomicilioSerializer(qs, many=True).data
        except Exception:
            return []

    def get_telefonos(self, obj):
        """
        Compatibilidad con esquema histórico:
        la tabla real no tiene columna 'tipo'.
        """
        try:
            rows = list(
                EntidadTelefono.objects
                .filter(entidad=obj.entidad)
                .values('id', 'numero')
                .order_by('id')
            )
            return [
                {
                    'id': row.get('id'),
                    'numero': row.get('numero'),
                    'tipo': 'CEL',
                }
                for row in rows
            ]
        except Exception:
            return []

    def get_emails_secundarios(self, obj):
        """
        Compatibilidad con esquema histórico:
        la tabla real no tiene columna 'tipo'.
        """
        try:
            rows = list(
                EntidadEmail.objects
                .filter(entidad=obj.entidad)
                .values('id', 'email')
                .order_by('id')
            )
            return [
                {
                    'id': row.get('id'),
                    'email': row.get('email'),
                    'tipo': 'Secundario',
                }
                for row in rows
            ]
        except Exception:
            return []


class ClienteAdminWriteSerializer(serializers.Serializer):
    razon_social = serializers.CharField(max_length=255)
    sexo = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tipo_persona = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    dni = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    cuit = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    situacion_iva = serializers.PrimaryKeyRelatedField(
        queryset=SituacionIVA.objects.all(),
        required=False,
        allow_null=True,
    )
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)

    codigo_cliente = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    nombre_fantasia = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    categoria = serializers.ChoiceField(choices=Cliente.Categoria.choices, required=False)
    price_list = serializers.PrimaryKeyRelatedField(
        queryset=PriceList.objects.all(),
        required=False,
        allow_null=True,
    )
    descuento_base = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    vendedor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    zona = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    permite_cta_cte = serializers.BooleanField(required=False)
    limite_credito = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    dias_vencimiento = serializers.IntegerField(required=False)
    contacto_nombre = serializers.CharField(max_length=150, required=False, allow_blank=True, allow_null=True)
    contacto_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    contacto_telefono = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    fecha_alta = serializers.DateField(required=False, allow_null=True)
    esta_activo = serializers.BooleanField(required=False)
    observaciones = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    domicilios = DomicilioSerializer(many=True, required=False)
    telefonos = TelefonoSerializer(many=True, required=False)
    emails_secundarios = EmailSecundarioSerializer(many=True, required=False)

    def _clean_nullable_str(self, value):
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _infer_tipo_persona(self, attrs):
        tipo_persona = self._clean_nullable_str(attrs.get('tipo_persona'))
        if tipo_persona:
            return tipo_persona

        sexo = self._clean_nullable_str(attrs.get('sexo'))
        if sexo == 'J':
            return 'J'
        if sexo in ('M', 'F'):
            return 'F'

        return 'J'

    def validate(self, attrs):
        razon_social = (attrs.get('razon_social') or '').strip()
        if not razon_social:
            raise serializers.ValidationError({
                'razon_social': 'La razón social es obligatoria.'
            })
        attrs['razon_social'] = razon_social

        cuit = self._clean_nullable_str(attrs.get('cuit'))
        if cuit:
            cuit = cuit.replace('-', '').replace(' ', '')
            attrs['cuit'] = cuit

            if len(cuit) < 11:
                raise serializers.ValidationError({
                    'cuit': 'El CUIT/CUIL debe tener al menos 11 dígitos.'
                })

            qs = Entidad.objects.filter(cuit=cuit)
            if self.instance:
                qs = qs.exclude(pk=self.instance.entidad_id)
            if qs.exists():
                raise serializers.ValidationError({
                    'cuit': 'Ya existe una entidad con ese CUIT/CUIL.'
                })
        else:
            attrs['cuit'] = None

        attrs['tipo_persona'] = self._infer_tipo_persona(attrs)
        attrs['dni'] = self._clean_nullable_str(attrs.get('dni'))
        attrs['email'] = self._clean_nullable_str(attrs.get('email'))
        attrs['codigo_cliente'] = self._clean_nullable_str(attrs.get('codigo_cliente'))
        attrs['nombre_fantasia'] = self._clean_nullable_str(attrs.get('nombre_fantasia'))
        attrs['zona'] = self._clean_nullable_str(attrs.get('zona'))
        attrs['contacto_nombre'] = self._clean_nullable_str(attrs.get('contacto_nombre'))
        attrs['contacto_email'] = self._clean_nullable_str(attrs.get('contacto_email'))
        attrs['contacto_telefono'] = self._clean_nullable_str(attrs.get('contacto_telefono'))
        attrs['observaciones'] = self._clean_nullable_str(attrs.get('observaciones'))
        attrs['sexo'] = self._clean_nullable_str(attrs.get('sexo'))

        if attrs.get('limite_credito') is not None and attrs['limite_credito'] < 0:
            raise serializers.ValidationError({
                'limite_credito': 'El límite de crédito no puede ser negativo.'
            })

        if attrs.get('dias_vencimiento') is not None and attrs['dias_vencimiento'] < 0:
            raise serializers.ValidationError({
                'dias_vencimiento': 'Los días de vencimiento no pueden ser negativos.'
            })

        if attrs.get('descuento_base') is not None:
            if attrs['descuento_base'] < 0 or attrs['descuento_base'] > 100:
                raise serializers.ValidationError({
                    'descuento_base': 'El descuento debe estar entre 0 y 100.'
                })

        return attrs

    def _save_nested(self, entidad, validated_data):
        domicilios = validated_data.pop('domicilios', None)
        telefonos = validated_data.pop('telefonos', None)
        emails_secundarios = validated_data.pop('emails_secundarios', None)

        if domicilios is not None:
            entidad.domicilios.all().delete()
            for item in domicilios:
                EntidadDomicilio.objects.create(entidad=entidad, **item)

        # Compatibilidad con esquema histórico:
        # la tabla real de teléfonos no tiene columna "tipo".
        # No persistimos teléfonos adicionales hasta alinear modelo y BD.
        if telefonos is not None:
            pass

        # Compatibilidad con esquema histórico:
        # la tabla real de emails no tiene columna "tipo".
        # No persistimos emails secundarios hasta alinear modelo y BD.
        if emails_secundarios is not None:
            pass

    def create(self, validated_data):
        tipo_persona = validated_data.get('tipo_persona')
        tipo_documento = 'DNI' if tipo_persona == 'F' else 'CUIT'

        entidad = Entidad.objects.create(
            razon_social=validated_data['razon_social'],
            tipo_persona=tipo_persona,
            tipo_documento=tipo_documento,
            sexo=validated_data.get('sexo'),
            dni=validated_data.get('dni'),
            cuit=validated_data.get('cuit'),
            situacion_iva=validated_data.get('situacion_iva'),
            email=validated_data.get('email'),
        )

        cliente = Cliente(
            entidad=entidad,
            codigo_cliente=validated_data.get('codigo_cliente'),
            nombre_fantasia=validated_data.get('nombre_fantasia'),
            categoria=validated_data.get('categoria') or Cliente.Categoria.MINORISTA,
            price_list=validated_data.get('price_list'),
            descuento_base=validated_data.get('descuento_base', 0),
            vendedor=validated_data.get('vendedor'),
            zona=validated_data.get('zona'),
            permite_cta_cte=validated_data.get('permite_cta_cte', False),
            limite_credito=validated_data.get('limite_credito', 0),
            dias_vencimiento=validated_data.get('dias_vencimiento', 0),
            contacto_nombre=validated_data.get('contacto_nombre'),
            contacto_email=validated_data.get('contacto_email'),
            contacto_telefono=validated_data.get('contacto_telefono'),
            fecha_alta=validated_data.get('fecha_alta'),
            esta_activo=validated_data.get('esta_activo', True),
            observaciones=validated_data.get('observaciones'),
        )
        cliente.save()

        self._save_nested(entidad, validated_data)
        return cliente

    def update(self, instance, validated_data):
        entidad = instance.entidad
        entidad.razon_social = validated_data.get('razon_social', entidad.razon_social)
        entidad.tipo_persona = validated_data.get('tipo_persona', getattr(entidad, 'tipo_persona', None))

        if entidad.tipo_persona == 'F':
            entidad.tipo_documento = 'DNI'
        elif entidad.tipo_persona == 'J':
            entidad.tipo_documento = 'CUIT'

        entidad.sexo = validated_data.get('sexo', entidad.sexo)
        entidad.dni = validated_data.get('dni', entidad.dni)
        entidad.cuit = validated_data.get('cuit', entidad.cuit)
        entidad.situacion_iva = validated_data.get('situacion_iva', entidad.situacion_iva)
        entidad.email = validated_data.get('email', entidad.email)
        entidad.save()

        scalar_fields = [
            'codigo_cliente',
            'nombre_fantasia',
            'categoria',
            'descuento_base',
            'zona',
            'permite_cta_cte',
            'limite_credito',
            'dias_vencimiento',
            'contacto_nombre',
            'contacto_email',
            'contacto_telefono',
            'fecha_alta',
            'esta_activo',
            'observaciones',
        ]
        for field in scalar_fields:
            if field in validated_data:
                setattr(instance, field, validated_data.get(field))

        if 'price_list' in validated_data:
            instance.price_list = validated_data.get('price_list')

        if 'vendedor' in validated_data:
            instance.vendedor = validated_data.get('vendedor')

        instance.save()
        self._save_nested(entidad, validated_data)
        return instance

    def to_representation(self, instance):
        return ClienteAdminDetailSerializer(instance, context=self.context).data