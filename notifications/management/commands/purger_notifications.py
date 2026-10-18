"""Suppression des anciennes notifications.

    python manage.py purger_notifications              (plus de 180 jours)
    python manage.py purger_notifications --jours 90

Chaque appel, annulation de séance ou demande crée des notifications, et la table grossit
sans fin. Une notification ancienne n'a plus d'utilité : l'information reste consultable
sur la page concernée (absences, demandes, emploi du temps). À lancer après « sauvegarder ».
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notifications.models import Notification


class Command(BaseCommand):
    help = "Supprime les notifications (lues ou non) plus anciennes que le nombre de jours indiqué."

    def add_arguments(self, parser):
        parser.add_argument("--jours", type=int, default=180, help="Âge minimal des notifications supprimées (180 par défaut).")

    def handle(self, *args, **options):
        jours = options["jours"]
        if jours < 1:
            raise CommandError("Indiquez un nombre de jours supérieur ou égal à 1.")
        limite = timezone.now() - timedelta(days=jours)
        supprimees, _ = Notification.objects.filter(date_creation__lt=limite).delete()
        self.stdout.write(self.style.SUCCESS(f"{supprimees} notification(s) de plus de {jours} jours supprimée(s)."))
