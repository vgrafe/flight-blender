# Generated by Django 3.1.7 on 2021-03-20 20:23

import datetime
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='FlightOperation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('gutma_flight_declaration', models.TextField()),
                ('type_of_operation', models.IntegerField(choices=[(0, 'VLOS'), (1, 'BVLOS')], default=0, help_text='At the moment, only VLOS and BVLOS operations are supported, for other types of operations, please issue a pull-request')),
                ('bounds', models.CharField(max_length=140)),
                ('start_datetime', models.DateTimeField(default=datetime.datetime.now)),
                ('end_datetime', models.DateTimeField(default=datetime.datetime.now)),
                ('is_approved', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
