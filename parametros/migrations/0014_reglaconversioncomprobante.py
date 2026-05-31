from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('parametros', '0013_cargamasiva_modo_alter_cargamasiva_entidad'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReglaConversionComprobante',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('etiqueta', models.CharField(blank=True, max_length=60, verbose_name='Etiqueta del botón')),
                ('copia_items', models.BooleanField(default=True, verbose_name='Copiar ítems')),
                ('copia_cliente', models.BooleanField(default=True, verbose_name='Copiar cliente')),
                ('copia_condicion_venta', models.BooleanField(default=True, verbose_name='Copiar condición de venta')),
                ('activo', models.BooleanField(default=True)),
                ('orden', models.PositiveSmallIntegerField(default=0, verbose_name='Orden de aparición')),
                ('tipo_destino', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reglas_como_destino', to='parametros.tipocomprobante', verbose_name='Tipo de comprobante destino')),
                ('tipo_origen', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reglas_como_origen', to='parametros.tipocomprobante', verbose_name='Tipo de comprobante origen')),
            ],
            options={
                'verbose_name': 'Regla de Conversión de Comprobante',
                'verbose_name_plural': 'Reglas de Conversión de Comprobantes',
                'ordering': ['orden', 'tipo_origen__nombre'],
                'unique_together': {('tipo_origen', 'tipo_destino')},
            },
        ),
    ]