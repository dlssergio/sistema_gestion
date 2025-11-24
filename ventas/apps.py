# ventas/apps.py

from django.apps import AppConfig

class VentasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ventas'

    # --- INICIO DE LA MODIFICACIÓN ---
    def ready(self):
        """
        Este método se ejecuta cuando Django carga la aplicación.
        Es el lugar canónico para importar y conectar los signals.
        """
        import ventas.signals
    # --- FIN DE LA MODIFICACIÓN ---