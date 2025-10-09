# en compras/admin.py (Versión Corregida)
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from .models import Proveedor, ComprobanteCompra, ComprobanteCompraItem

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('get_razon_social', 'codigo_proveedor', 'get_cuit', 'editar_entidad_link')
    search_fields = ('entidad__razon_social', 'entidad__cuit', 'codigo_proveedor', 'nombre_fantasia')
    def get_razon_social(self, obj): return obj.entidad.razon_social
    get_razon_social.short_description = 'Razón Social'
    def get_cuit(self, obj): return obj.entidad.cuit
    get_cuit.short_description = 'CUIT'
    def editar_entidad_link(self, obj):
        url = reverse('admin:entidades_entidad_change', args=[obj.entidad.pk])
        return format_html('<a href="{}">Editar Ficha Completa</a>', url)
    editar_entidad_link.short_description = 'Acciones'
    def add_view(self, request, form_url='', extra_context=None):
        url = reverse('admin:entidades_entidad_add') + '?rol=proveedor'
        return HttpResponseRedirect(url)
    def has_change_permission(self, request, obj=None): return False

class ProveedorInline(admin.StackedInline):
    model = Proveedor
    can_delete = False
    verbose_name_plural = 'Datos del Proveedor'

class ComprobanteCompraItemInline(admin.TabularInline):
    model = ComprobanteCompraItem
    extra = 1
    autocomplete_fields = ['articulo']

@admin.register(ComprobanteCompra)
class ComprobanteCompraAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'proveedor', 'fecha', 'estado', 'total')
    list_filter = ('estado', 'proveedor', 'fecha', 'tipo_comprobante')
    search_fields = ('numero', 'punto_venta')
    inlines = [ComprobanteCompraItemInline]
    readonly_fields = ('total', 'letra')
    autocomplete_fields = ['proveedor']
    fieldsets = (
        (None, { 'fields': ('tipo_comprobante', 'proveedor', 'fecha', 'estado') }),
        ('Numeración', { 'fields': (('punto_venta', 'numero'),) }),
        ('Relaciones', { 'fields': ('comprobante_origen',) })
    )