from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from config.validateurs import VALIDATEURS_DOCUMENT


class DemandeDocument(models.Model):
    """Demande d'un document administratif par un étudiant (BF08 à BF10)."""

    class TypeDocument(models.TextChoices):
        ATTESTATION_SCOLARITE = "ATTESTATION_SCOLARITE", "Attestation de scolarité"
        RELEVE_NOTES = "RELEVE_NOTES", "Relevé de notes"
        ATTESTATION_REUSSITE = "ATTESTATION_REUSSITE", "Attestation de réussite"
        CONVENTION_STAGE = "CONVENTION_STAGE", "Convention de stage"

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        ACCEPTEE = "ACCEPTEE", "Acceptée"
        PRETE = "PRETE", "Prête"
        REFUSEE = "REFUSEE", "Refusée"

    # Changements de statut autorisés pour la scolarité
    TRANSITIONS = {
        Statut.EN_ATTENTE: {Statut.ACCEPTEE, Statut.REFUSEE},
        Statut.ACCEPTEE: {Statut.PRETE, Statut.REFUSEE},
        Statut.PRETE: set(),
        Statut.REFUSEE: set(),
    }

    etudiant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="étudiant",
        on_delete=models.CASCADE,
        related_name="demandes_documents",
        limit_choices_to={"role": "ETUDIANT"},
    )
    type_document = models.CharField("type de document", max_length=30, choices=TypeDocument.choices)
    motif = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    commentaire = models.TextField("commentaire de la scolarité", blank=True)
    document = models.FileField(
        "document délivré",
        upload_to="documents/%Y/%m/",
        blank=True,
        validators=VALIDATEURS_DOCUMENT,
    )
    traitee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="traitée par",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_traitees",
    )
    date_demande = models.DateTimeField("date de la demande", auto_now_add=True)
    date_traitement = models.DateTimeField("date de traitement", null=True, blank=True)

    class Meta:
        verbose_name = "demande de document"
        verbose_name_plural = "demandes de documents"
        ordering = ["-date_demande"]

    def __str__(self):
        return f"{self.get_type_document_display()} – {self.etudiant} ({self.get_statut_display()})"

    @transaction.atomic
    def changer_statut(self, nouveau_statut, agent, commentaire=""):
        """Fait évoluer la demande en respectant le cycle de vie et notifie l'étudiant.

        Le changement est conditionné au statut lu : si deux agents traitent la même demande
        en même temps, la seconde décision est refusée au lieu d'écraser la première.
        """
        from notifications.models import Notification

        if nouveau_statut not in self.TRANSITIONS[self.statut]:
            raise ValidationError(
                f"Impossible de passer de « {self.get_statut_display()} » "
                f"à « {self.Statut(nouveau_statut).label} »."
            )
        if not DemandeDocument.objects.filter(pk=self.pk, statut=self.statut).update(statut=nouveau_statut):
            raise ValidationError("Cette demande vient d'être traitée par un autre agent : rechargez la page.")
        self.statut = nouveau_statut
        self.traitee_par = agent
        self.date_traitement = timezone.now()
        if commentaire:
            self.commentaire = commentaire
        self.save()
        Notification.envoyer(
            self.etudiant,
            f"Votre demande « {self.get_type_document_display()} » est maintenant : {self.get_statut_display()}.",
            lien=reverse("documents:liste"),
        )
