from django.conf import settings
from django.db import models


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
    def envoyer(cls, destinataire, message, lien=""):
        return cls.objects.create(destinataire=destinataire, message=message, lien=lien)

    @classmethod
    def envoyer_au_role(cls, role, message, lien=""):
        """Notifie tous les comptes actifs ayant ce rôle (ex. : toute la scolarité)."""
        from comptes.models import Utilisateur

        destinataires = Utilisateur.objects.filter(role=role, is_active=True)
        cls.objects.bulk_create([cls(destinataire=u, message=message, lien=lien) for u in destinataires])
