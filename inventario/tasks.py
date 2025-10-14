from celery import shared_task
import time

@shared_task
def sumar_numeros(x, y):
    # Simulamos una tarea que tarda 5 segundos
    time.sleep(5)
    return x + y