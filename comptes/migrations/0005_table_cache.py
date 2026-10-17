from django.core.management import call_command
from django.db import migrations


def creer_table_cache(apps, schema_editor):
    # Sans effet si la table existe déjà.
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    """Table du cache en base (paramètre CACHES) : créée par « migrate », elle ne peut pas être oubliée au déploiement."""

    dependencies = [
        ("comptes", "0004_utilisateur_doit_changer_mot_de_passe"),
    ]

    operations = [
        migrations.RunPython(creer_table_cache, migrations.RunPython.noop),
    ]
