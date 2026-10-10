from collections import defaultdict

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from config.validateurs import VALIDATEURS_JUSTIFICATIF


class Absence(models.Model):
    """Absence ou retard d'un étudiant à une séance, à une date donnée (BF02)."""

    class Nature(models.TextChoices):
        ABSENCE = "ABSENCE", "Absence"
        RETARD = "RETARD", "Retard"

    class Statut(models.TextChoices):
        NON_JUSTIFIEE = "NON_JUSTIFIEE", "Non justifiée"
        JUSTIFIEE = "JUSTIFIEE", "Justifiée"

    etudiant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="étudiant",
        on_delete=models.CASCADE,
        related_name="absences",
        limit_choices_to={"role": "ETUDIANT"},
    )
    seance = models.ForeignKey("emplois.Seance", verbose_name="séance", on_delete=models.PROTECT, related_name="absences")
    date = models.DateField()
    nature = models.CharField(max_length=10, choices=Nature.choices, default=Nature.ABSENCE)
    duree_heures = models.FloatField(
        "durée (h)",
        default=0,
        editable=False,
        help_text="Durée de la séance au moment de l'appel : une modification ultérieure "
        "de l'emploi du temps ne change pas les heures d'absence déjà enregistrées. "
        "Un retard ne compte pas d'heures d'absence.",
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.NON_JUSTIFIEE)
    saisie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="saisie par",
        on_delete=models.SET_NULL,
        null=True,
        related_name="absences_saisies",
    )
    date_saisie = models.DateTimeField("date de saisie", auto_now_add=True)

    class Meta:
        verbose_name = "absence"
        verbose_name_plural = "absences"
        ordering = ["-date", "seance__heure_debut"]
        constraints = [
            models.UniqueConstraint(fields=["etudiant", "seance", "date"], name="absence_unique_par_seance")
        ]

    def __str__(self):
        return f"{self.get_nature_display()} – {self.etudiant} – {self.seance.matiere} le {self.date:%d/%m/%Y}"

    def save(self, *args, **kwargs):
        if self.nature == self.Nature.RETARD:
            self.duree_heures = 0
        elif not self.duree_heures:
            self.duree_heures = self.seance.duree_heures
        super().save(*args, **kwargs)

    def clean(self):
        if self.date and self.seance_id:
            erreur = self.seance.empechement(self.date)
            if erreur:
                raise ValidationError({"date": erreur})
        if self.etudiant_id and self.seance_id:
            e, s = self.etudiant, self.seance
            if e.classe_id != s.classe_id or (s.groupe_id and e.groupe_id != s.groupe_id):
                raise ValidationError({"etudiant": "Cet étudiant ne fait pas partie du public de cette séance."})

    @property
    def est_retard(self):
        return self.nature == self.Nature.RETARD

    @property
    def derniere_justification(self):
        """Justification la plus récente (utilise le préchargement « justifications » s'il existe)."""
        justifications = list(self.justifications.all())
        return max(justifications, key=lambda j: j.date_depot) if justifications else None

    @property
    def peut_etre_justifiee(self):
        """Une absence peut être justifiée s'il n'y a pas de justification, ou si la dernière a été refusée."""
        if self.est_retard:
            return False
        derniere = self.derniere_justification
        return derniere is None or derniere.statut == Justification.Statut.REFUSEE

    @staticmethod
    def heures_par_matiere(etudiant):
        """Total des heures d'absence de l'étudiant, par matière (BF03), et niveau d'alerte.

        Renvoie une liste de dictionnaires triée par matière :
        {"matiere", "total", "justifiees", "non_justifiees", "retards", "taux", "alerte"}.
        « taux » est la part des heures non justifiées dans le volume horaire de la matière (en %).
        """
        totaux = defaultdict(lambda: {"total": 0.0, "justifiees": 0.0, "non_justifiees": 0.0, "retards": 0})
        for absence in etudiant.absences.select_related("seance__matiere"):
            ligne = totaux[absence.seance.matiere]
            if absence.est_retard:
                ligne["retards"] += 1
                continue
            ligne["total"] += absence.duree_heures
            if absence.statut == Absence.Statut.JUSTIFIEE:
                ligne["justifiees"] += absence.duree_heures
            else:
                ligne["non_justifiees"] += absence.duree_heures

        lignes = []
        for matiere, valeurs in sorted(totaux.items(), key=lambda kv: kv[0].nom):
            taux = 100 * valeurs["non_justifiees"] / matiere.volume_horaire if matiere.volume_horaire else 0
            lignes.append({"matiere": matiere, **valeurs, "taux": taux, "alerte": AlerteAbsence.niveau_pour(taux)})
        return lignes


class Justification(models.Model):
    """Justificatif déposé par l'étudiant pour une absence (BF04), traité par la scolarité (BF05).

    Une absence peut recevoir plusieurs justifications successives (par exemple après un
    refus pour mauvais fichier), mais une seule peut être en attente ou acceptée.
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        ACCEPTEE = "ACCEPTEE", "Acceptée"
        REFUSEE = "REFUSEE", "Refusée"

    absence = models.ForeignKey(Absence, on_delete=models.CASCADE, related_name="justifications")
    motif = models.TextField()
    piece_jointe = models.FileField("pièce jointe", upload_to="justificatifs/%Y/%m/", validators=VALIDATEURS_JUSTIFICATIF)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    commentaire = models.TextField("commentaire de la scolarité", blank=True)
    traitee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="traitée par",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="justifications_traitees",
    )
    date_depot = models.DateTimeField("date de dépôt", auto_now_add=True)
    date_traitement = models.DateTimeField("date de traitement", null=True, blank=True)

    class Meta:
        verbose_name = "justification"
        verbose_name_plural = "justifications"
        ordering = ["-date_depot"]
        constraints = [
            models.UniqueConstraint(
                fields=["absence"],
                condition=Q(statut__in=["EN_ATTENTE", "ACCEPTEE"]),
                name="une_justification_active_par_absence",
            )
        ]

    def __str__(self):
        return f"Justification – {self.absence} ({self.get_statut_display()})"

    def traiter(self, acceptee, agent, commentaire=""):
        """Accepte ou refuse la justification et met à jour le statut de l'absence."""
        from notifications.models import Notification

        if self.statut != self.Statut.EN_ATTENTE:
            raise ValidationError("Cette justification a déjà été traitée.")
        self.statut = self.Statut.ACCEPTEE if acceptee else self.Statut.REFUSEE
        self.traitee_par = agent
        self.date_traitement = timezone.now()
        self.commentaire = commentaire
        self.save()

        self.absence.statut = Absence.Statut.JUSTIFIEE if acceptee else Absence.Statut.NON_JUSTIFIEE
        self.absence.save(update_fields=["statut"])

        message = (
            f"Votre justification pour l'absence du {self.absence.date:%d/%m/%Y} "
            f"({self.absence.seance.matiere}) a été {self.get_statut_display().lower()}."
        )
        if not acceptee:
            message += " Vous pouvez déposer une nouvelle justification."
        Notification.envoyer(self.absence.etudiant, message, lien=reverse("absences:mes_absences"))


class AlerteAbsence(models.Model):
    """Franchissement d'un seuil d'heures d'absence non justifiées dans une matière.

    Les seuils sont exprimés en pourcentage du volume horaire de la matière
    (paramètre SEUILS_ABSENCE). Chaque seuil n'est signalé qu'une fois par étudiant et par matière.
    """

    class Niveau(models.TextChoices):
        AVERTISSEMENT = "AVERTISSEMENT", "Avertissement"
        CRITIQUE = "CRITIQUE", "Seuil critique"

    etudiant = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="étudiant", on_delete=models.CASCADE, related_name="alertes_absence"
    )
    matiere = models.ForeignKey("structure.Matiere", verbose_name="matière", on_delete=models.CASCADE, related_name="alertes_absence")
    niveau = models.CharField(max_length=20, choices=Niveau.choices)
    heures_non_justifiees = models.FloatField("heures non justifiées")
    taux = models.FloatField("part du volume horaire (%)")
    date_creation = models.DateTimeField("date", auto_now_add=True)

    class Meta:
        verbose_name = "alerte d'absence"
        verbose_name_plural = "alertes d'absence"
        ordering = ["-date_creation"]
        constraints = [
            models.UniqueConstraint(fields=["etudiant", "matiere", "niveau"], name="alerte_unique_par_niveau")
        ]

    def __str__(self):
        return f"{self.get_niveau_display()} – {self.etudiant} – {self.matiere} ({self.taux:.0f} %)"

    @classmethod
    def seuils(cls):
        """Seuils triés du plus bas au plus haut : [(niveau, pourcentage), …]."""
        return sorted(settings.SEUILS_ABSENCE.items(), key=lambda kv: kv[1])

    @classmethod
    def niveau_pour(cls, taux):
        """Niveau d'alerte le plus élevé atteint pour ce taux, ou None."""
        atteint = None
        for niveau, seuil in cls.seuils():
            if taux >= seuil:
                atteint = niveau
        return atteint

    @classmethod
    def verifier(cls, etudiant):
        """Crée les alertes nouvellement atteintes et prévient l'étudiant et la scolarité."""
        from notifications.models import Notification

        nouvelles = []
        for ligne in Absence.heures_par_matiere(etudiant):
            for niveau, seuil in cls.seuils():
                if ligne["taux"] < seuil:
                    continue
                alerte, creee = cls.objects.get_or_create(
                    etudiant=etudiant,
                    matiere=ligne["matiere"],
                    niveau=niveau,
                    defaults={"heures_non_justifiees": ligne["non_justifiees"], "taux": ligne["taux"]},
                )
                if not creee:
                    continue
                nouvelles.append(alerte)
                libelle = cls.Niveau(niveau).label.lower()
                Notification.envoyer(
                    etudiant,
                    f"{cls.Niveau(niveau).label} : {ligne['non_justifiees']:g} h d'absence non justifiées en "
                    f"{ligne['matiere']} ({ligne['taux']:.0f} % du volume horaire, seuil {seuil} %).",
                    lien=reverse("absences:mes_absences"),
                )
                Notification.envoyer_au_role(
                    "SCOLARITE",
                    f"{etudiant} a atteint le {libelle} ({seuil} %) en {ligne['matiere']}.",
                    lien=f"{reverse('absences:par_classe')}?classe={etudiant.classe_id or ''}",
                )
        return nouvelles
