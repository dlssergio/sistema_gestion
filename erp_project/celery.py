import os
from celery import Celery

# Establece el módulo de settings de Django para el programa 'celery'.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_project.settings')

app = Celery('erp_project')

# Usar un string aquí significa que el worker no necesita serializar
# el objeto de configuración. El namespace='CELERY' significa que
# todas las claves de configuración de Celery deben tener el prefijo `CELERY_`.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Carga automáticamente los módulos de tareas de todas las apps registradas.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')