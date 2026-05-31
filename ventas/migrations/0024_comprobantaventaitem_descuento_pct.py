from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0023_descuento_global_pct'),
    ]

    operations = [
        migrations.AddField(
            model_name='comprobanteventaitem',
            name='descuento_pct',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Descuento (%)'),
        ),
    ]