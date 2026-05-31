
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0021_comprobanteventa_cliente_cuit_override_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ClienteCanal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
                ('activo', models.BooleanField(default=True)),
            ],
            options={'ordering': ['nombre'], 'verbose_name': 'Canal de Cliente', 'verbose_name_plural': 'Canales de Clientes'},
        ),
        migrations.CreateModel(
            name='ClienteGrupo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=20, unique=True)),
                ('nombre', models.CharField(max_length=100, unique=True)),
                ('activo', models.BooleanField(default=True)),
            ],
            options={'ordering': ['nombre'], 'verbose_name': 'Grupo de Cliente', 'verbose_name_plural': 'Grupos de Clientes'},
        ),
        migrations.CreateModel(
            name='ClienteSegmento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
                ('activo', models.BooleanField(default=True)),
            ],
            options={'ordering': ['nombre'], 'verbose_name': 'Segmento de Cliente', 'verbose_name_plural': 'Segmentos de Clientes'},
        ),
        migrations.CreateModel(
            name='CondicionPagoVenta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=20, unique=True)),
                ('nombre', models.CharField(max_length=100)),
                ('dias', models.PositiveIntegerField(default=0)),
                ('permite_cta_cte', models.BooleanField(default=False)),
                ('activo', models.BooleanField(default=True)),
            ],
            options={'ordering': ['nombre'], 'verbose_name': 'Condición de Pago de Venta', 'verbose_name_plural': 'Condiciones de Pago de Venta'},
        ),
        migrations.AddField(
            model_name='cliente', name='canal', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clientes', to='ventas.clientecanal'),
        ),
        migrations.AddField(
            model_name='cliente', name='grupo', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clientes', to='ventas.clientegrupo'),
        ),
        migrations.AddField(
            model_name='cliente', name='segmento', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clientes', to='ventas.clientesegmento'),
        ),
        migrations.AddField(
            model_name='cliente', name='condicion_pago', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clientes', to='ventas.condicionpagoventa', verbose_name='Condición de Pago'),
        ),
        migrations.AddField(
            model_name='cliente', name='estado', field=models.CharField(choices=[('ACT', 'Activo'), ('INA', 'Inactivo'), ('BLQ', 'Bloqueado')], default='ACT', max_length=3, verbose_name='Estado'),
        ),
        migrations.AddField(
            model_name='cliente', name='motivo_bloqueo', field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Motivo de Bloqueo'),
        ),
        migrations.AddField(
            model_name='cliente', name='fecha_baja', field=models.DateField(blank=True, null=True, verbose_name='Fecha de Baja'),
        ),
        migrations.CreateModel(
            name='ClienteContacto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('apellido', models.CharField(blank=True, max_length=100, null=True)),
                ('cargo', models.CharField(blank=True, max_length=100, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('telefono', models.CharField(blank=True, max_length=50, null=True)),
                ('celular', models.CharField(blank=True, max_length=50, null=True)),
                ('es_principal', models.BooleanField(default=False)),
                ('recibe_facturacion', models.BooleanField(default=False)),
                ('recibe_cobranzas', models.BooleanField(default=False)),
                ('activo', models.BooleanField(default=True)),
                ('observaciones', models.TextField(blank=True, null=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contactos', to='ventas.cliente')),
            ],
            options={'ordering': ['-es_principal', 'nombre', 'apellido'], 'verbose_name': 'Contacto de Cliente', 'verbose_name_plural': 'Contactos de Clientes'},
        ),
    ]
