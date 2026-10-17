from django.conf import settings
from django.db import models
from django.utils.text import Truncator


class Notification(models.Model):
    """Notification interne affichée à l'utilisateur (justification traitée, document prêt…)."""

    destinataire = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=300)
    lien = models.CharField(max_length=200, blank=True)
    lue = models.BooleanField(default=False)
    date_creation = models.DateTimeField("date", auto_now_add=True)

    class Meta:
        verbose_name = "notification"
        verbose_name_plural = "notifications"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.destinataire} : {self.message}"

    @classmethod
    def preparer(cls, destinataire, message, lien=""):
        """Notification non enregistrée (pour bulk_create).

        Le message est tronqué à la taille du champ : il contient des noms de matière ou des
        motifs saisis librement, et une base comme PostgreSQL refuserait un texte trop long.
        """
        longueur = cls._meta.get_field("message").max_length
        return cls(destinataire=destinataire, message=Truncator(message).chars(longueur), lien=lien)

    @classmethod
    def envoyer(cls, destinataire, message, lien=""):
        notification = cls.preparer(destinataire, message, lien)
        notification.save()
        return notification

    @classmethod
    def envoyer_a(cls, destinataires, message, lien=""):
        """Envoie la même notification à plusieurs comptes, en une seule requête."""
        cls.objects.bulk_create([cls.preparer(u, message, lien) for u in destinataires])

    @classmethod
    def envoyer_au_role(cls, role, message, lien=""):
        """Notifie tous les comptes actifs ayant ce rôle (ex. : toute la scolarité)."""
        cls.envoyer_a(cls.comptes_du_role(role), message, lien)

    @staticmethod
    def comptes_du_role(role):
        from comptes.models import Utilisateur

        return Utilisateur.objects.filter(role=role, is_active=True)
