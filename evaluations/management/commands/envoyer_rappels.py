"""Rappels des examens et des dates limites de devoirs qui approchent (deux jours avant).

    python manage.py envoyer_rappels

Les rappels partent aussi d'eux-mêmes à l'ouverture du tableau de bord ; la commande sert
quand une tâche planifiée est disponible (formule payante de PythonAnywhere, crontab…).
"""

from django.core.management.base import BaseCommand

from evaluations.models import envoyer_rappels


class Command(BaseCommand):
    help = "Envoie les rappels des examens et des devoirs à rendre dans les deux jours."

    def handle(self, *args, **options):
        nombre = envoyer_rappels()
        self.stdout.write(self.style.SUCCESS(f"{nombre} rappel(s) envoyé(s)."))
