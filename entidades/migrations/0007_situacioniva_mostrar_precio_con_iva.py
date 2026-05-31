from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('entidades', '0006_alter_entidad_options_alter_entidaddomicilio_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='situacioniva',
            name='mostrar_precio_con_iva',
            field=models.BooleanField(default=False, help_text='Si está activo, el POS muestra precios con IVA incluido para clientes con esta situación (ej: Consumidor Final).', verbose_name='Mostrar precio con IVA en venta'),
        ),
    ]