from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class Company(TenantMixin):
    """
    Este es el modelo que define a cada cliente (Tenant) de nuestro sistema.
    Hereda de TenantMixin para obtener toda la funcionalidad de django-tenants.
    """
    name = models.CharField(max_length=100, unique=True)
    created_on = models.DateField(auto_now_add=True)

    # auto_create_schema le dice a django-tenants que cree un nuevo esquema
    # en la base de datos (ej: 'tenant_cliente_a') cada vez que se guarde
    # una nueva instancia de Company. Esta es la magia principal.
    auto_create_schema = True

    def __str__(self):
        return self.name

class Domain(DomainMixin):
    """
    Este modelo asocia un dominio de internet (ej: 'cliente-a.faroerp.com')
    con un Tenant (una Company). Así es como el middleware sabe qué
    esquema activar para cada petición.
    """
    # No necesita campos adicionales, DomainMixin se encarga de todo.
    def __str__(self):
        return f"{self.domain} (Tenant: {self.tenant.name})"