# parametros/admin.py

from django.contrib import admin
from .models import (
    TipoComprobante, Contador, Moneda, Pais, Provincia, Localidad,
    CategoriaImpositiva, Impuesto, Role, GrupoUnidadMedida, UnidadMedida,
    SerieDocumento, ConfiguracionEmpresa, AfipCertificado, AfipToken,
    ConfiguracionSMTP
)


# --- MODELOS GENERALES ---

@admin.register(TipoComprobante)
class TipoComprobanteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'letra', 'codigo_afip', 'mueve_stock')
    search_fields = ['nombre', 'codigo_afip']


@admin.register(Contador)
class ContadorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'prefijo', 'ultimo_valor')
    list_editable = ('ultimo_valor',)


@admin.register(Moneda)
class MonedaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'simbolo', 'cotizacion', 'es_base')
    list_editable = ('cotizacion',)
    search_fields = ('nombre', 'simbolo')


# --- GEOGRAFÍA ---

@admin.register(Pais)
class PaisAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'por_defecto')
    search_fields = ('nombre', 'codigo')


@admin.register(Provincia)
class ProvinciaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'pais')
    search_fields = ('nombre', 'codigo')
    list_filter = ('pais',)
    autocomplete_fields = ['pais']


@admin.register(Localidad)
class LocalidadAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo_postal', 'provincia')
    search_fields = ('nombre', 'codigo_postal')
    list_filter = ('provincia__pais', 'provincia')
    autocomplete_fields = ['provincia']


# --- IMPUESTOS Y UNIDADES ---

@admin.register(Impuesto)
class ImpuestoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tasa', 'aplica_a', 'es_porcentaje', 'vigente_desde', 'vigente_hasta')
    list_filter = ('aplica_a', 'es_porcentaje')
    search_fields = ('nombre',)


@admin.register(CategoriaImpositiva)
class CategoriaImpositivaAdmin(admin.ModelAdmin):
    search_fields = ('nombre',)


@admin.register(GrupoUnidadMedida)
class GrupoUnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)


@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'simbolo', 'grupo')
    list_filter = ('grupo',)
    search_fields = ('nombre', 'simbolo')
    autocomplete_fields = ['grupo']


# --- CONFIGURACIÓN DE EMPRESA Y SERIES ---

@admin.register(SerieDocumento)
class SerieDocumentoAdmin(admin.ModelAdmin):
    # 1. Agregamos 'diseno_impresion' a la lista para verlo en la tabla general
    list_display = (
    'nombre', 'tipo_comprobante', 'punto_venta', 'ultimo_numero', 'es_manual', 'solicitar_cae_automaticamente', 'activo', 'diseno_impresion')

    list_filter = ('tipo_comprobante', 'es_manual', 'activo')
    search_fields = ('nombre', 'punto_venta')

    # Asegúrate de que estos campos tengan search_fields definidos en sus propios admins
    autocomplete_fields = ['tipo_comprobante', 'deposito_defecto']

    fieldsets = (
        ('Configuración Principal', {
            'fields': ('nombre', 'tipo_comprobante', 'punto_venta', 'activo')
        }),
        ('Numeración y Automatización', {
            'fields': (
                'ultimo_numero',
                'es_manual',
                'solicitar_cae_automaticamente',  # <--- Agregado aquí para poder editarlo
                'deposito_defecto'
            )
        }),
        ('Diseño de Reporte', {
            'fields': ('diseno_impresion',),
            'description': 'Selecciona la plantilla PDF específica para este talonario (Ej: Factura A, Presupuesto, etc).'
        }),
    )


@admin.register(ConfiguracionEmpresa)
class ConfiguracionEmpresaAdmin(admin.ModelAdmin):
    list_display = ('nombre_fantasia', 'entidad', 'usar_factura_electronica', 'modo_facturacion')

    fieldsets = (
        ('Identidad', {
            'fields': ('entidad', 'nombre_fantasia', 'logo')
        }),
        ('Datos Fiscales', {
            'fields': ('inicio_actividades', 'ingresos_brutos', 'moneda_principal')
        }),
        ('Facturación Electrónica', {
            'fields': ('usar_factura_electronica', 'modo_facturacion'),
            'description': 'Configure si desea emitir facturas con CAE y si el proceso debe ser automático.'
        })
    )

    def has_add_permission(self, request):
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name',)
    filter_horizontal = ('permissions', 'users',)


# --- AFIP (CERTIFICADOS) ---

@admin.register(AfipCertificado)
class AfipCertificadoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cuit', 'vencimiento', 'es_produccion', 'activo', 'subido_el')
    list_filter = ('activo', 'es_produccion')

    fieldsets = (
        ('Configuración', {
            'fields': ('nombre', 'cuit', 'es_produccion', 'activo')
        }),
        ('Vigencia y Seguridad', {
            'fields': ('vencimiento', 'certificado', 'clave_privada'),
            'description': 'Sube los archivos .crt y .key generados en la web de AFIP. La fecha de vencimiento se detectará automáticamente.'
        }),
    )


# Opcional: Para ver los tokens generados (útil para debug)
@admin.register(AfipToken)
class AfipTokenAdmin(admin.ModelAdmin):
    list_display = ('certificado', 'service', 'generado', 'expira')
    readonly_fields = ('token', 'sign', 'unique_id', 'generado', 'expira')

    def has_add_permission(self, request):
        return False  # Los tokens se generan solos, no se agregan a mano


@admin.register(ConfiguracionSMTP)
class ConfiguracionSMTPAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'host', 'usuario', 'puerto', 'activo')
    list_filter = ('activo', 'host')

    fieldsets = (
        ('General', {
            'fields': ('nombre', 'activo')
        }),
        ('Servidor', {
            'fields': ('host', 'host_custom', 'puerto'),
            'description': 'Seleccione un proveedor o elija "Otro" para configurar uno personalizado.'
        }),
        ('Autenticación', {
            'fields': ('usuario', 'password', 'email_from')
        }),
        ('Seguridad', {
            'fields': ('usar_tls', 'usar_ssl')
        }),
    )