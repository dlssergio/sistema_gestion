# en entidades/admin.py (VERSIÓN FINAL CON INDENTACIÓN CORREGIDA)
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from .models import SituacionIVA, Entidad, EntidadDomicilio, EntidadTelefono, EntidadEmail
from compras.admin import ProveedorInline
from ventas.admin import ClienteInline


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


@admin.register(Entidad)
class EntidadAdmin(admin.ModelAdmin):
    # Todo lo que está aquí adentro debe tener al menos 4 espacios de indentación
    class Media:
        # css = {'all': ('admin/css/tabs.css',)}
        # js = ('admin/js/entidad_tabs.js', 'admin/js/entidad_form.js',)
        pass  # Usamos 'pass' si la clase está vacía para evitar errores

    list_display = ('id', 'razon_social', 'get_nombre_fantasia', 'cuit', 'situacion_iva')
    list_display_links = ('id', 'razon_social')
    search_fields = ('razon_social', 'cuit', 'dni')
    autocomplete_fields = ['situacion_iva']
    fieldsets = (
        ('Datos Principales', {'fields': ('razon_social', 'sexo', 'dni', 'cuit', 'situacion_iva'), }),
    )
    inlines = [
        ClienteInline,
        ProveedorInline,
        EntidadDomicilioInline,
        EntidadTelefonoInline,
        EntidadEmailInline,
    ]

    def save_model(self, request, obj, form, change):
        # Este método también está indentado para pertenecer a EntidadAdmin
        from ventas.models import Cliente
        from compras.models import Proveedor

        super().save_model(request, obj, form, change)

        if not change:
            rol = request.GET.get('rol')
            if rol == 'cliente':
                Cliente.objects.create(entidad=obj)
            elif rol == 'proveedor':
                Proveedor.objects.create(entidad=obj)

    def get_inlines(self, request, obj=None):
        rol = request.GET.get('rol')
        if rol == 'cliente': return [ClienteInline, EntidadDomicilioInline, EntidadTelefonoInline, EntidadEmailInline]
        if rol == 'proveedor': return [ProveedorInline, EntidadDomicilioInline, EntidadTelefonoInline,
                                       EntidadEmailInline]
        return self.inlines

    def add_view(self, request, form_url='', extra_context=None):
        rol = request.GET.get('rol')
        extra_context = extra_context or {}
        if rol == 'cliente':
            extra_context['title'] = 'Agregar Nuevo Cliente'
        elif rol == 'proveedor':
            extra_context['title'] = 'Agregar Nuevo Proveedor'
        return super().add_view(request, form_url, extra_context=extra_context)

    def get_nombre_fantasia(self, obj):
        if hasattr(obj, 'proveedor') and obj.proveedor.nombre_fantasia:
            return obj.proveedor.nombre_fantasia
        return '-'

    get_nombre_fantasia.short_description = 'Nombre de Fantasía'