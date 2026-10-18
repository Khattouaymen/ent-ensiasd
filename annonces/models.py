from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone


class Annonce(models.Model):
    """Annonce de la scolarité, de l'administration ou d'un enseignant.

    Sans filière ni classe, elle s'adresse à tout l'établissement ; avec une filière, à toutes
    les classes de la filière ; avec une classe, à cette seule classe.
    """

    titre = models.CharField(max_length=200)
    contenu = models.TextField()
    importante = models.BooleanField(default=False, help_text="Mise en avant en tête de liste et sur le tableau de bord.")
    filiere = models.ForeignKey(
        "structure.Filiere", verbose_name="filière", on_delete=models.CASCADE, null=True, blank=True, related_name="annonces"
    )
    classe = models.ForeignKey("structure.Classe", on_delete=models.CASCADE, null=True, blank=True, related_name="annonces")
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, editable=False, related_name="annonces_publiees"
    )
    date_publication = models.DateTimeField("publiée le", auto_now_add=True)
    date_fin = models.DateField(
        "affichée jusqu'au", null=True, blank=True, help_text="Laisser vide pour une annonce sans date de fin."
    )

    class Meta:
        verbose_name = "annonce"
        verbose_name_plural = "annonces"
        ordering = ["-importante", "-date_publication"]
        constraints = [
            models.CheckConstraint(condition=Q(filiere__isnull=True) | Q(classe__isnull=True), name="annonce_une_seule_cible")
        ]

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse("annonces:detail", args=[self.pk])

    @property
    def destinataires_libelle(self):
        if self.classe_id:
            return str(self.classe)
        if self.filiere_id:
            return f"Filière {self.filiere.code}"
        return "Tout l'établissement"

    @classmethod
    def visibles_par(cls, utilisateur, y_compris_expirees=False):
        """Annonces qui concernent l'utilisateur (le personnel administratif les voit toutes)."""
        annonces = cls.objects.select_related("filiere", "classe__filiere", "classe__niveau", "auteur")
        if not y_compris_expirees:
            annonces = annonces.filter(Q(date_fin__isnull=True) | Q(date_fin__gte=timezone.localdate()))
        if utilisateur.est_scolarite or utilisateur.est_admin:
            return annonces
        pour_tous = Q(filiere__isnull=True, classe__isnull=True)
        if utilisateur.est_etudiant:
            if not utilisateur.classe_id:
                return annonces.filter(pour_tous)
            return annonces.filter(pour_tous | Q(classe_id=utilisateur.classe_id) | Q(filiere_id=utilisateur.classe.filiere_id))
        # Enseignant : annonces de ses classes et de leurs filières, et les siennes
        enseignements = utilisateur.enseignements.values("classe")
        filieres = utilisateur.enseignements.values("classe__filiere")
        return annonces.filter(
            pour_tous | Q(classe__in=enseignements) | Q(filiere__in=filieres) | Q(auteur=utilisateur)
        ).distinct()

    def destinataires(self):
        """Comptes à notifier : les étudiants de la classe ou de la filière, ou tout l'établissement."""
        from comptes.models import Utilisateur

        comptes = Utilisateur.objects.filter(is_active=True)
        if self.classe_id:
            return comptes.filter(role=Utilisateur.Role.ETUDIANT, classe_id=self.classe_id)
        if self.filiere_id:
            return comptes.filter(role=Utilisateur.Role.ETUDIANT, classe__filiere_id=self.filiere_id)
        return comptes.exclude(pk=self.auteur_id)

    def notifier(self):
        from notifications.models import Notification

        prefixe = "Annonce importante" if self.importante else "Annonce"
        Notification.envoyer_a(self.destinataires(), f"{prefixe} : {self.titre}", lien=self.get_absolute_url())

    def peut_etre_supprimee_par(self, utilisateur):
        if utilisateur.est_scolarite or utilisateur.est_admin:
            return True
        return self.auteur_id is not None and self.auteur_id == utilisateur.pk
