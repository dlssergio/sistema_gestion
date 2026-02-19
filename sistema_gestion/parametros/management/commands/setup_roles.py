from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from ventas.models import Cliente, ComprobanteVenta, Recibo
from compras.models import Proveedor, ComprobanteCompra, OrdenPago
from inventario.models import Articulo, MovimientoStock
from finanzas.models import Cheque, MovimientoFondo, CuentaFondo

class Command(BaseCommand):
    help = 'Configura los grupos y permisos iniciales del ERP'

    def handle(self, *args, **kwargs):
        self.stdout.write("Iniciando configuración de roles...")

        # DEFINICIÓN DE ROLES
        ROLES = {
            'Vendedores': {
                'descripcion': 'Solo pueden vender y consultar stock.',
                'permisos': [
                    # App Ventas
                    ('view_cliente', Cliente), ('add_cliente', Cliente), ('change_cliente', Cliente),
                    ('view_comprobanteventa', ComprobanteVenta), ('add_comprobanteventa', ComprobanteVenta),
                    ('view_recibo', Recibo), ('add_recibo', Recibo),
                    # App Inventario (Solo lectura)
                    ('view_articulo', Articulo),
                ]
            },
            'Tesoreria': {
                'descripcion': 'Manejan pagos, cobros y bancos.',
                'permisos': [
                    # App Compras
                    ('view_proveedor', Proveedor), ('add_proveedor', Proveedor),
                    ('view_comprobantecompra', ComprobanteCompra), ('add_comprobantecompra', ComprobanteCompra),
                    ('view_ordenpago', OrdenPago), ('add_ordenpago', OrdenPago), ('change_ordenpago', OrdenPago),
                    # App Finanzas
                    ('view_cheque', Cheque), ('change_cheque', Cheque), # Para depositar/entregar
                    ('view_movimientofondo', MovimientoFondo), ('add_movimientofondo', MovimientoFondo),
                    ('view_cuentafondo', CuentaFondo),
                    # App Ventas (Para ver recibos y validarlos)
                    ('view_recibo', Recibo), ('change_recibo', Recibo),
                ]
            },
            'Gerencia': {
                'descripcion': 'Acceso total de lectura y reportes estratégicos.',
                'permisos': [
                    # Acceso total de lectura a todo
                    ('view_cliente', Cliente), ('view_comprobanteventa', ComprobanteVenta),
                    ('view_proveedor', Proveedor), ('view_comprobantecompra', ComprobanteCompra),
                    ('view_ordenpago', OrdenPago), ('view_articulo', Articulo),
                    ('view_movimientostock', MovimientoStock), ('view_cheque', Cheque),
                    ('view_movimientofondo', MovimientoFondo),
                ]
            }
        }

        for nombre_grupo, data in ROLES.items():
            grupo, created = Group.objects.get_or_create(name=nombre_grupo)
            if created:
                self.stdout.write(f"✅ Grupo creado: {nombre_grupo}")
            else:
                self.stdout.write(f"ℹ️ Actualizando grupo: {nombre_grupo}")

            # Limpiamos permisos anteriores para evitar duplicados/basura
            grupo.permissions.clear()

            count = 0
            for cod_permiso, modelo in data['permisos']:
                try:
                    ct = ContentType.objects.get_for_model(modelo)
                    permiso = Permission.objects.get(codename=cod_permiso, content_type=ct)
                    grupo.permissions.add(permiso)
                    count += 1
                except Permission.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"   ⚠️ Permiso no encontrado: {cod_permiso}"))

            self.stdout.write(f"   -> Asignados {count} permisos.")

        self.stdout.write(self.style.SUCCESS("¡Roles configurados correctamente! 🚀"))