from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0022_cliente_admin_enterprise'),
    ]

    operations = [
        migrations.AddField(
            model_name='comprobanteventa',
            name='descuento_global_pct',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Descuento Global (%)'),
        ),
    ]