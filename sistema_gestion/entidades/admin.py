# entidades/admin.py

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from django.shortcuts import redirect

from .models import SituacionIVA, Entidad, EntidadDomicilio, EntidadTelefono, EntidadEmail
from compras.models import Proveedor
from ventas.models import Cliente


@admin.register(SituacionIVA)
class SituacionIVAAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'codigo_afip')
    list_editable = ('codigo_afip',)
    search_fields = ('codigo', 'nombre')


class EntidadDomicilioInline(admin.TabularInline):
    model = EntidadDomicilio
    extra = 1
    autocomplete_fields = ['localidad']
    # Como cambiamos el modelo a calle/numero, TabularInline mostrará todas las columnas.
    # Si queda muy ancho, puedes cambiarlo a admin.StackedInline


class EntidadTelefonoInline(admin.TabularInline):
    model = EntidadTelefono
    extra = 1


class EntidadEmailInline(admin.TabularInline):
    model = EntidadEmail
    extra = 0
    verbose_name = "Email Adicional"
    verbose_name_plural = "Emails Adicionales (Secundarios)"


class ProveedorInline(admin.StackedInline):
    model = Proveedor
    can_delete = False
    verbose_name_plural = 'Datos del Rol Proveedor'
    fields = ('codigo_proveedor', 'nombre_fantasia', 'limite_credito')


class ClienteInline(admin.StackedInline):
    model = Cliente
    can_delete = False
    verbose_name_plural = 'Datos del Rol Cliente'


@admin.register(Entidad)
class EntidadAdmin(admin.ModelAdmin):
    # change_form_template = "admin/entidades/entidad/change_form.html"

    # 1. VISUALIZACIÓN EN LISTA
    list_display = ('id', 'razon_social', 'cuit', 'situacion_iva', 'email')
    search_fields = ('razon_social', 'cuit', 'dni', 'email')
    autocomplete_fields = ['situacion_iva']

    # 2. FORMULARIO DE EDICIÓN (Aquí estaba el faltante)
    fieldsets = (
        ('Datos Principales', {
            'fields': ('razon_social', 'cuit', 'situacion_iva', 'email')  # <--- ¡AGREGADO AQUÍ!
        }),
        ('Datos Persona Física (Opcional)', {
            'fields': ('sexo', 'dni'),
            'classes': ('collapse',),  # Esto permite ocultar la sección si no se usa
        }),
    )

    base_inlines = [EntidadDomicilioInline, EntidadTelefonoInline, EntidadEmailInline]

    class Media:
        js = ('admin/js/entidad_form.js',)

    def get_inlines(self, request, obj=None):
        inlines = list(self.base_inlines)
        rol = request.GET.get('rol')
        if rol == 'proveedor' or (obj and hasattr(obj, 'proveedor')): inlines.insert(0, ProveedorInline)
        if rol == 'cliente' or (obj and hasattr(obj, 'cliente')): inlines.insert(0, ClienteInline)
        return inlines

    def add_view(self, request, form_url='', extra_context=None):
        self.inlines = self.get_inlines(request)
        rol = request.GET.get('rol')
        extra_context = extra_context or {}
        if rol == 'cliente':
            extra_context['title'] = 'Agregar Nuevo Cliente'
        elif rol == 'proveedor':
            extra_context['title'] = 'Agregar Nuevo Proveedor'
        return super().add_view(request, form_url, extra_context=extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.get_object(request, object_id)
        self.inlines = self.get_inlines(request, obj)
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            rol = request.GET.get('rol')
            if rol == 'cliente':
                Cliente.objects.create(entidad=obj)
            elif rol == 'proveedor':
                Proveedor.objects.create(entidad=obj)

    def response_add(self, request, obj, post_url_continue=None):
        if "_continue" not in request.POST:
            rol = request.GET.get('rol')
            if rol == 'proveedor':
                return redirect('admin:compras_proveedor_changelist')
            elif rol == 'cliente':
                return redirect('admin:ventas_cliente_changelist')
        return super().response_add(request, obj, post_url_continue)