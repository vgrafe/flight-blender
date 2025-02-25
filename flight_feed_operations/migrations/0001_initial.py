# Generated by Django 4.2 on 2023-04-18 14:45

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SignedTelmetryPublicKey",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("key_id", models.TextField(help_text="Specify the Key ID")),
                (
                    "url",
                    models.URLField(
                        help_text="Enter the JWK / JWKS URL of the public key"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Specify if the key is active, only active keys will be validated against in the signed telemetry feeds",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
