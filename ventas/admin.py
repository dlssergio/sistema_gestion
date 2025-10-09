# en ventas/admin.py (Versión Corregida)
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from .models import Cliente, ComprobanteVenta, ComprobanteVentaItem

class ClienteInline(admin.StackedInline):
    model = Cliente
    can_delete = False
    verbose_name_plural = 'Datos del Cliente'

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('get_razon_social', 'get_cuit', 'editar_entidad_link')
    search_fields = ('entidad__razon_social', 'entidad__cuit')
    def get_razon_social(self, obj): return obj.entidad.razon_social
    get_razon_social.short_description = 'Razón Social'
    def get_cuit(self, obj): return obj.entidad.cuit
    get_cuit.short_description = 'CUIT'
    def editar_entidad_link(self, obj):
        url = reverse('admin:entidades_entidad_change', args=[obj.entidad.pk])
        return format_html('<a href="{}">Editar Ficha Completa</a>', url)
    editar_entidad_link.short_description = 'Acciones'
    def add_view(self, request, form_url='', extra_context=None):
        url = reverse('admin:entidades_entidad_add') + '?rol=cliente'
        return HttpResponseRedirect(url)
    def has_change_permission(self, request, obj=None): return False

class ComprobanteVentaItemInline(admin.TabularInline):
    model = ComprobanteVentaItem
    extra = 1
    autocomplete_fields = ['articulo']

@admin.register(ComprobanteVenta)
class ComprobanteVentaAdmin(admin.ModelAdmin):
    #change_form_template = "admin/ventas/comprobanteventa/change_form.html"
    list_display = ('__str__', 'cliente', 'fecha', 'estado', 'total')
    list_filter = ('estado', 'cliente', 'fecha', 'tipo_comprobante')
    search_fields = ('numero', 'punto_venta')
    inlines = [ComprobanteVentaItemInline]
    readonly_fields = ('total', 'letra')
    autocomplete_fields = ['cliente']
    fieldsets = (
        (None, { 'fields': ('tipo_comprobante', 'cliente', 'fecha', 'estado') }),
        ('Numeración', { 'fields': (('punto_venta', 'numero'),) }),
    )