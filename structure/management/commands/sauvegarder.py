"""Sauvegarde de la base SQLite et des fichiers déposés (BNF07).

    python manage.py sauvegarder

Crée dans le dossier « sauvegardes/ » une archive horodatée contenant une copie
cohérente de la base (API de sauvegarde SQLite : sûre même pendant que le site
tourne) et le dossier « media/ ». Seules les N dernières archives sont conservées
(paramètre NB_SAUVEGARDES_CONSERVEES). À planifier chaque nuit (voir le README).
"""

import sqlite3
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

PREFIXE = "sauvegarde_ent_"


class Command(BaseCommand):
    help = "Sauvegarde la base de données et les fichiers déposés dans une archive ZIP horodatée."

    def handle(self, *args, **options):
        if connection.vendor != "sqlite":
            raise CommandError("Cette commande sauvegarde une base SQLite. Pour un autre moteur, utilisez son outil (pg_dump…).")
        if connection.in_atomic_block:
            # La transaction tiendrait le verrou d'écriture (mode IMMEDIATE) : la copie attendrait indéfiniment.
            raise CommandError("La sauvegarde ne peut pas être lancée à l'intérieur d'une transaction.")

        dossier = Path(settings.DOSSIER_SAUVEGARDES)
        dossier.mkdir(parents=True, exist_ok=True)
        horodatage = timezone.localtime().strftime("%Y-%m-%d_%H%M%S_%f")
        archive = dossier / f"{PREFIXE}{horodatage}.zip"

        with tempfile.TemporaryDirectory() as temporaire:
            copie = Path(temporaire) / "db.sqlite3"
            connection.ensure_connection()
            destination = sqlite3.connect(copie)
            with destination:
                connection.connection.backup(destination)
            destination.close()

            nb_fichiers = 0
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(copie, "db.sqlite3")
                media = Path(settings.MEDIA_ROOT)
                if media.exists():
                    for fichier in media.rglob("*"):
                        if fichier.is_file():
                            zf.write(fichier, Path("media") / fichier.relative_to(media))
                            nb_fichiers += 1

        supprimees = self.rotation(dossier)
        taille_mo = archive.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f"Sauvegarde créée : {archive.name} ({taille_mo:.1f} Mo, base + {nb_fichiers} fichier(s) déposé(s))."
        ))
        if supprimees:
            self.stdout.write(f"{supprimees} ancienne(s) sauvegarde(s) supprimée(s).")

    def rotation(self, dossier):
        """Ne garde que les sauvegardes les plus récentes."""
        archives = sorted(dossier.glob(f"{PREFIXE}*.zip"))
        anciennes = archives[: max(0, len(archives) - settings.NB_SAUVEGARDES_CONSERVEES)]
        for ancienne in anciennes:
            ancienne.unlink()
        return len(anciennes)
