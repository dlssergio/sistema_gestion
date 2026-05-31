from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('parametros', '0014_reglaconversioncomprobante'),
    ]

    operations = [
        migrations.AddField(
            model_name='reglaconversioncomprobante',
            name='confirmar_automaticamente',
            field=models.BooleanField(
                default=False,
                help_text='Si está activo, el comprobante destino se confirma al crear. Si no, queda en Borrador.',
                verbose_name='Confirmar automáticamente'
            ),
        ),
    ]