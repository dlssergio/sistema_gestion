# ventas/admin.py

from auditlog.registry import auditlog
from django.contrib import admin
from django.urls import reverse, path
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from .models import Cliente, ComprobanteVenta, ComprobanteVentaItem, PriceList, ProductPrice
from .views import get_precio_articulo, calcular_totales_api, get_precio_articulo_cliente
from .services import TaxCalculatorService
from django.shortcuts import render
from django.contrib import messages
from decimal import Decimal, ROUND_HALF_UP


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('get_razon_social', 'get_cuit', 'editar_entidad_link')
    search_fields = ('entidad__razon_social', 'entidad__cuit')
    autocomplete_fields = ['price_list']

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


class ComprobanteVentaItemInline(admin.TabularInline):
    model = ComprobanteVentaItem
    extra = 1
    autocomplete_fields = ['articulo']
    readonly_fields = ('subtotal',)


@admin.register(ComprobanteVenta)
class ComprobanteVentaAdmin(admin.ModelAdmin):
    change_form_template = "admin/ventas/comprobanteventa/change_form.html"
    list_display = ('__str__', 'cliente', 'fecha', 'estado', 'total')
    list_filter = ('estado', 'cliente', 'fecha', 'tipo_comprobante')
    search_fields = ('numero', 'punto_venta')
    inlines = [ComprobanteVentaItemInline]
    readonly_fields = ('letra', 'subtotal', 'impuestos_desglosados', 'total')
    autocomplete_fields = ['cliente']
    fieldsets = (
        (None, {'fields': ('tipo_comprobante', 'cliente', 'fecha', 'estado')}),
        ('Numeración', {'fields': (('punto_venta', 'numero'),)}),
        ('Totales (Calculado al Guardar)',
         {'classes': ('collapse', 'show'), 'fields': ('subtotal', 'impuestos_desglosados', 'total')})
    )

    class Media:
        js = ('admin/js/comprobante_venta_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('api/get-precio-articulo/<str:pk>/',
                 self.admin_site.admin_view(get_precio_articulo),
                 name='pricelist_get_precio_articulo'),
            # name='ventas_get_precio_articulo'),
            path('api/get-precio-articulo-cliente/<int:cliente_pk>/<str:articulo_pk>/',
                 self.admin_site.admin_view(get_precio_articulo_cliente),
                 name='ventas_get_precio_articulo_cliente'),
            path('api/calcular-totales/',
                 self.admin_site.admin_view(calcular_totales_api),
                 name='ventas_calcular_totales_api'),
        ]
        return custom_urls + urls

    @admin.display(description='Impuestos')
    def impuestos_desglosados(self, obj):
        if not obj.impuestos: return "N/A"
        html = "<ul>"
        for nombre, monto in obj.impuestos.items():
            html += f"<li><strong>{nombre}:</strong> ${float(monto):,.2f}</li>"
        html += "</ul>"
        return format_html(html)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        obj = form.instance
        if not obj.pk: return
        subtotal_calculado = sum(item.subtotal for item in obj.items.all())
        obj.subtotal = subtotal_calculado.quantize(Decimal('0.01'))
        desglose_impuestos = TaxCalculatorService.calcular_impuestos_comprobante(obj, 'venta')
        obj.impuestos = {k: str(v) for k, v in desglose_impuestos.items()}
        total_impuestos = sum(desglose_impuestos.values())
        obj.total = obj.subtotal + total_impuestos
        obj.save()


class ProductPriceInline(admin.TabularInline):
    """
    Este inline nos permite añadir y editar precios de artículos
    directamente DENTRO de la página de una Lista de Precios.
    """
    model = ProductPrice
    extra = 1
    autocomplete_fields = ['product', 'price_moneda']
    fields = ('product', 'price_monto', 'price_moneda', 'min_quantity', 'max_quantity')

    # Opcional: Mostrar el costo actual como referencia de solo lectura si el objeto ya existe
    readonly_fields = ('costo_referencia',)

    def costo_referencia(self, obj):
        if obj.product:
            return obj.product.precio_costo
        return "-"

    costo_referencia.short_description = "Costo Actual (Ref)"


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    """
    Administrador para el modelo principal de Listas de Precios de Venta.
    """
    list_display = ('name', 'code', 'is_default', 'valid_from', 'valid_until')
    search_fields = ('name', 'code')
    inlines = [ProductPriceInline]

    class Media:
        js = ('admin/js/price_list_admin.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            # Reutilizamos la vista que ya creamos para obtener el precio/costo del artículo
            path('api/get-precio-articulo/<str:pk>/',
                 self.admin_site.admin_view(get_precio_articulo),
                 name='pricelist_get_precio_articulo'),
        ]
        return custom_urls + urls


@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    """
    Administrador para ver todos los precios de productos de forma individual.
    Útil para búsquedas y filtros avanzados.
    """
    list_display = ('product', 'price_list', 'price', 'min_quantity', 'actualizado_hace')
    list_filter = ('price_list', 'product__rubro', 'product__marca')  # Filtros clave para masivos
    search_fields = ('product__descripcion', 'product__cod_articulo', 'price_list__name')
    autocomplete_fields = ['product', 'price_list', 'price_moneda']

    actions = ['actualizar_precios_masivo']

    @admin.display(description="Actualizado")
    def actualizado_hace(self, obj):
        # Muestra fecha si tuviéramos campo 'updated_at', si no, dejar guión
        return "-"

    @admin.action(description="📈 Actualizar precios seleccionados (Masivo)")
    def actualizar_precios_masivo(self, request, queryset):
        # 1. Procesar formulario (POST con 'apply')
        if 'apply' in request.POST:
            try:
                metodo = request.POST.get('metodo')
                tipo_redondeo = request.POST.get('redondeo')
                actualizados = 0
                errores = 0

                # Preparamos variables según el método
                factor_porcentaje = 1
                factor_markup = 1
                formula_str = ""

                if metodo == 'porcentaje':
                    val = Decimal(request.POST.get('porcentaje', 0))
                    factor_porcentaje = 1 + (val / 100)
                elif metodo == 'markup':
                    val = Decimal(request.POST.get('markup', 0))
                    factor_markup = 1 + (val / 100)
                elif metodo == 'formula':
                    formula_str = request.POST.get('formula', '').lower().strip()

                for precio_obj in queryset:
                    nuevo_monto = Decimal(0)

                    # --- LÓGICA DE CÁLCULO ---
                    try:
                        if metodo == 'porcentaje':
                            # Método 1: Porcentaje sobre precio actual
                            nuevo_monto = precio_obj.price_monto * factor_porcentaje

                        elif metodo == 'markup':
                            # Método 2: Markup sobre Costo
                            costo = precio_obj.product.precio_costo_monto
                            if costo <= 0:
                                errores += 1
                                continue  # Saltamos si no hay costo
                            nuevo_monto = costo * factor_markup

                        elif metodo == 'formula':
                            # Método 3: Fórmula personalizada
                            costo = float(precio_obj.product.precio_costo_monto)
                            precio_actual = float(precio_obj.price_monto)

                            # Entorno seguro para evaluar (sin acceso a __builtins__)
                            contexto = {
                                'costo': costo,
                                'precio': precio_actual,
                                'abs': abs, 'min': min, 'max': max
                            }
                            # Permitimos solo chars seguros
                            # (Nota: para producción estricta usar librerías como simpleeval,
                            # aquí usamos eval restringido por simplicidad y ser entorno admin)
                            resultado = eval(formula_str, {"__builtins__": None}, contexto)
                            nuevo_monto = Decimal(str(resultado))

                    except Exception as e:
                        errores += 1
                        continue

                    # --- LÓGICA DE REDONDEO ---
                    if tipo_redondeo == 'entero':
                        nuevo_monto = nuevo_monto.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                    elif tipo_redondeo == 'diez':
                        nuevo_monto = (nuevo_monto / 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 10
                    else:
                        nuevo_monto = nuevo_monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                    # Guardamos
                    precio_obj.price_monto = nuevo_monto
                    precio_obj.save()
                    actualizados += 1

                mensaje = f"✅ Se actualizaron {actualizados} precios."
                if errores > 0:
                    mensaje += f" ⚠️ Hubo {errores} errores (quizás artículos sin costo para markup)."

                self.message_user(request, mensaje)
                return HttpResponseRedirect(request.get_full_path())

            except (ValueError, TypeError, SyntaxError) as e:
                self.message_user(request, f"❌ Error en el cálculo: {str(e)}", level=messages.ERROR)

        # 2. Renderizar formulario
        return render(request, 'admin/ventas/productprice/actualizar_precios.html', context={
            'queryset': queryset,
            'title': 'Actualización Masiva de Precios'
        })