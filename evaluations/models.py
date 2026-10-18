import os
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from config.validateurs import VALIDATEURS_RESSOURCE

# Les rappels partent quand l'échéance est à moins de deux jours.
DELAI_RAPPEL = timedelta(days=2)


def etudiants_concernes(classe_id, groupe_id=None):
    """Étudiants actifs d'une classe, ou d'un seul de ses groupes."""
    from comptes.models import Utilisateur

    etudiants = Utilisateur.objects.filter(role=Utilisateur.Role.ETUDIANT, classe_id=classe_id, is_active=True)
    return etudiants.filter(groupe_id=groupe_id) if groupe_id else etudiants


class PourUneClasse(models.Model):
    """Évaluation destinée à une classe entière ou à l'un de ses groupes, dans une matière."""

    classe = models.ForeignKey("structure.Classe", on_delete=models.CASCADE, related_name="%(class)ss")
    groupe = models.ForeignKey(
        "structure.Groupe",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)ss",
        help_text="Laisser vide pour toute la classe.",
    )
    matiere = models.ForeignKey("structure.Matiere", verbose_name="matière", on_delete=models.PROTECT, related_name="%(class)ss")
    rappel_envoye = models.BooleanField("rappel envoyé", default=False, editable=False)

    class Meta:
        abstract = True

    def clean(self):
        if self.groupe_id and self.classe_id and self.groupe.classe_id != self.classe_id:
            raise ValidationError({"groupe": "Ce groupe n'appartient pas à la classe choisie."})
        if self.matiere_id and self.classe_id and (
            self.matiere.filiere_id != self.classe.filiere_id or self.matiere.niveau_id != self.classe.niveau_id
        ):
            raise ValidationError({"matiere": "Cette matière n'appartient pas à la filière et au niveau de la classe."})

    @property
    def public_libelle(self):
        return f"{self.classe} · {self.groupe.nom}" if self.groupe_id else str(self.classe)

    def public(self):
        return etudiants_concernes(self.classe_id, self.groupe_id)

    @classmethod
    def pour_etudiant(cls, etudiant):
        if not etudiant.classe_id:
            return cls.objects.none()
        return cls.objects.filter(Q(groupe__isnull=True) | Q(groupe_id=etudiant.groupe_id), classe_id=etudiant.classe_id)

    @classmethod
    def pour_enseignant(cls, enseignant):
        """Évaluations de ses affectations (matière et classe) ou créées par lui."""
        from structure.models import Enseignement

        affectations = Enseignement.objects.filter(enseignant=enseignant).values_list("matiere_id", "classe_id")
        filtre = Q(**{cls.CHAMP_AUTEUR: enseignant})
        for matiere_id, classe_id in affectations:
            filtre |= Q(matiere_id=matiere_id, classe_id=classe_id)
        return cls.objects.filter(filtre)


class Examen(PourUneClasse):
    """Examen, contrôle continu, rattrapage ou soutenance, à une date et une heure données."""

    CHAMP_AUTEUR = "cree_par"

    class Type(models.TextChoices):
        EXAMEN = "EXAMEN", "Examen"
        CONTROLE = "CONTROLE", "Contrôle continu"
        RATTRAPAGE = "RATTRAPAGE", "Rattrapage"
        SOUTENANCE = "SOUTENANCE", "Soutenance"

    type = models.CharField(max_length=12, choices=Type.choices, default=Type.EXAMEN)
    titre = models.CharField(max_length=200, blank=True, help_text="Facultatif. Ex. : Partiel du semestre 3.")
    date = models.DateField()
    heure_debut = models.TimeField("heure de début")
    heure_fin = models.TimeField("heure de fin", null=True, blank=True)
    salle = models.ForeignKey("structure.Salle", on_delete=models.SET_NULL, null=True, blank=True, related_name="examens")
    consignes = models.TextField(blank=True, help_text="Documents autorisés, matériel à prévoir…")
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="créé par",
        on_delete=models.SET_NULL,
        null=True,
        editable=False,
        related_name="examens_crees",
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "examen"
        verbose_name_plural = "examens"
        ordering = ["date", "heure_debut"]

    def __str__(self):
        return f"{self.intitule} – {self.date:%d/%m/%Y}"

    @property
    def intitule(self):
        return self.titre or f"{self.get_type_display()} – {self.matiere}"

    @property
    def debut(self):
        return timezone.make_aware(datetime.combine(self.date, self.heure_debut))

    @property
    def fin(self):
        return timezone.make_aware(datetime.combine(self.date, self.heure_fin)) if self.heure_fin else None

    def clean(self):
        super().clean()
        if self.heure_debut and self.heure_fin and self.heure_fin <= self.heure_debut:
            raise ValidationError({"heure_fin": "L'heure de fin doit être après l'heure de début."})

    def message(self, prefixe):
        lieu = f", salle {self.salle}" if self.salle_id else ""
        return (
            f"{prefixe} : {self.get_type_display()} de {self.matiere} le "
            f"{date_format(self.date, 'l j F')} à {self.heure_debut:%H:%M}{lieu}."
        )

    def notifier(self):
        from notifications.models import Notification

        Notification.envoyer_a(self.public(), self.message("Nouvel examen"), lien=reverse("evaluations:calendrier"))


class Devoir(PourUneClasse):
    """Devoir ou compte rendu de TP à déposer en ligne avant une date limite."""

    CHAMP_AUTEUR = "enseignant"

    titre = models.CharField(max_length=200)
    consignes = models.TextField()
    fichier_consignes = models.FileField(
        "sujet (fichier)", upload_to="devoirs/sujets/%Y/%m/", blank=True, validators=VALIDATEURS_RESSOURCE
    )
    date_limite = models.DateTimeField("date limite")
    accepte_retard = models.BooleanField(
        "accepter les rendus en retard",
        default=False,
        help_text="Les rendus déposés après la date limite seront marqués « en retard ».",
    )
    enseignant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False, related_name="devoirs_crees"
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "devoir"
        verbose_name_plural = "devoirs"
        ordering = ["date_limite"]

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse("evaluations:devoir", args=[self.pk])

    @property
    def est_depasse(self):
        return timezone.now() > self.date_limite

    @property
    def accepte_les_rendus(self):
        return not self.est_depasse or self.accepte_retard

    def notifier(self):
        from notifications.models import Notification

        message = (
            f"Nouveau devoir : « {self.titre} » ({self.matiere}), à rendre avant le "
            f"{date_format(timezone.localtime(self.date_limite), 'l j F à H:i')}."
        )
        Notification.envoyer_a(self.public(), message, lien=self.get_absolute_url())

    def supprimer_fichiers(self):
        if self.fichier_consignes:
            self.fichier_consignes.delete(save=False)
        for rendu in self.rendus.all():
            rendu.fichier.delete(save=False)


class Rendu(models.Model):
    """Fichier déposé par un étudiant pour un devoir ; un nouveau dépôt remplace le précédent."""

    devoir = models.ForeignKey(Devoir, on_delete=models.CASCADE, related_name="rendus")
    etudiant = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="étudiant", on_delete=models.CASCADE, related_name="rendus"
    )
    fichier = models.FileField(upload_to="rendus/%Y/%m/", validators=VALIDATEURS_RESSOURCE)
    commentaire = models.TextField("message pour l'enseignant", blank=True)
    date_depot = models.DateTimeField("déposé le")
    en_retard = models.BooleanField("en retard", default=False)

    class Meta:
        verbose_name = "rendu"
        verbose_name_plural = "rendus"
        ordering = ["etudiant__last_name", "etudiant__first_name"]
        constraints = [models.UniqueConstraint(fields=["devoir", "etudiant"], name="un_rendu_par_etudiant")]

    def __str__(self):
        return f"{self.devoir} – {self.etudiant}"

    @property
    def nom_fichier(self):
        return os.path.basename(self.fichier.name)


def envoyer_rappels(maintenant=None):
    """Rappelle les examens et les dates limites des devoirs qui approchent (une seule fois chacun).

    Pour un devoir, seuls les étudiants qui n'ont encore rien déposé sont prévenus. Appelée par la
    commande « envoyer_rappels » et, à défaut de tâche planifiée, à l'ouverture du tableau de bord.
    Renvoie le nombre d'examens et de devoirs rappelés.
    """
    from notifications.models import Notification

    maintenant = maintenant or timezone.now()
    aujourdhui = timezone.localdate(maintenant)
    rappeles = 0
    examens = Examen.objects.filter(rappel_envoye=False, date__gte=aujourdhui, date__lte=aujourdhui + DELAI_RAPPEL)
    for examen in examens.select_related("matiere", "salle"):
        # Mise à jour conditionnelle : deux appels simultanés n'envoient pas deux rappels.
        if Examen.objects.filter(pk=examen.pk, rappel_envoye=False).update(rappel_envoye=True):
            Notification.envoyer_a(examen.public(), examen.message("Rappel"), lien=reverse("evaluations:calendrier"))
            rappeles += 1
    devoirs = Devoir.objects.filter(rappel_envoye=False, date_limite__gt=maintenant, date_limite__lte=maintenant + DELAI_RAPPEL)
    for devoir in devoirs.select_related("matiere"):
        if Devoir.objects.filter(pk=devoir.pk, rappel_envoye=False).update(rappel_envoye=True):
            sans_rendu = devoir.public().exclude(rendus__devoir=devoir)
            message = (
                f"Rappel : « {devoir.titre} » ({devoir.matiere}) est à rendre avant le "
                f"{date_format(timezone.localtime(devoir.date_limite), 'l j F à H:i')}."
            )
            Notification.envoyer_a(sans_rendu, message, lien=devoir.get_absolute_url())
            rappeles += 1
    return rappeles
