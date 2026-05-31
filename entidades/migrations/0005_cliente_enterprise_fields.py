
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('entidades', '0004_alter_entidademail_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='entidad',
            name='tipo_persona',
            field=models.CharField(choices=[('F', 'Persona Física'), ('J', 'Persona Jurídica')], default='J', max_length=1, verbose_name='Tipo de Persona'),
        ),
        migrations.AddField(
            model_name='entidad',
            name='tipo_documento',
            field=models.CharField(blank=True, choices=[('DNI', 'DNI'), ('CUIT', 'CUIT'), ('CUIL', 'CUIL'), ('PAS', 'Pasaporte'), ('OTR', 'Otro')], max_length=4, null=True, verbose_name='Tipo de Documento'),
        ),
        migrations.AddField(
            model_name='entidad',
            name='numero_documento',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Número de Documento'),
        ),
        migrations.AddField(
            model_name='entidad',
            name='nombre_fantasia',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Nombre de Fantasía'),
        ),
        migrations.AddField(
            model_name='entidad',
            name='situacion_iibb',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Situación IIBB'),
        ),
        migrations.AddField(
            model_name='entidad',
            name='numero_iibb',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Número IIBB'),
        ),
        migrations.AddField(
            model_name='entidad',
            name='web',
            field=models.URLField(blank=True, max_length=255, null=True, verbose_name='Sitio Web'),
        ),
        migrations.AddField(
            model_name='entidaddomicilio',
            name='tipo_direccion',
            field=models.CharField(choices=[('FISCAL', 'Fiscal'), ('ENTREGA', 'Entrega'), ('COMERCIAL', 'Comercial'), ('OTRA', 'Otra')], default='COMERCIAL', max_length=20),
        ),
        migrations.AddField(
            model_name='entidaddomicilio',
            name='es_principal',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='entidaddomicilio',
            name='es_fiscal',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='entidaddomicilio',
            name='es_entrega',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='entidaddomicilio',
            name='referencia',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
