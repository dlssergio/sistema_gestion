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
    list_display = ('codigo', 'nombre')
    search_fields = ('codigo', 'nombre')


class EntidadDomicilioInline(admin.TabularInline):
    model = EntidadDomicilio
    extra = 1
    autocomplete_fields = ['localidad']


class EntidadTelefonoInline(admin.TabularInline):
    model = EntidadTelefono
    extra = 1


class EntidadEmailInline(admin.TabularInline):
    model = EntidadEmail
    extra = 1


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
    # <<< CAMBIO CLAVE: Eliminamos la referencia a la plantilla personalizada >>>
    # change_form_template = "admin/entidades/entidad/change_form.html"

    list_display = ('id', 'razon_social', 'cuit', 'situacion_iva')
    search_fields = ('razon_social', 'cuit', 'dni')
    autocomplete_fields = ['situacion_iva']
    fieldsets = (
        (None, {'fields': ('razon_social', 'sexo', 'dni', 'cuit', 'situacion_iva')}),
    )

    base_inlines = [EntidadDomicilioInline, EntidadTelefonoInline, EntidadEmailInline]

    # <<< CAMBIO CLAVE: Modificamos la clase Media para cargar SOLO el script del CUIL >>>
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

    # <<< CORRECCIÓN DE LÓGICA: El método 'save_model' se asegura de crear el rol >>>
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