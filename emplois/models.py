from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format


class Seance(models.Model):
    """Séance de l'emploi du temps d'une classe (ou d'un de ses groupes).

    Une séance est soit hebdomadaire (elle revient chaque semaine le jour indiqué),
    soit ponctuelle (séance de rattrapage à une date unique).
    """

    class Jour(models.IntegerChoices):
        LUNDI = 1, "Lundi"
        MARDI = 2, "Mardi"
        MERCREDI = 3, "Mercredi"
        JEUDI = 4, "Jeudi"
        VENDREDI = 5, "Vendredi"
        SAMEDI = 6, "Samedi"

    class Type(models.TextChoices):
        COURS = "COURS", "Cours"
        TD = "TD", "TD"
        TP = "TP", "TP"

    classe = models.ForeignKey("structure.Classe", on_delete=models.CASCADE, related_name="seances")
    groupe = models.ForeignKey(
        "structure.Groupe",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="seances",
        help_text="Laisser vide si la séance concerne toute la classe.",
    )
    matiere = models.ForeignKey("structure.Matiere", verbose_name="matière", on_delete=models.PROTECT, related_name="seances")
    enseignant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="seances",
        limit_choices_to={"role": "ENSEIGNANT"},
    )
    salle = models.ForeignKey("structure.Salle", on_delete=models.PROTECT, related_name="seances")
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.COURS)
    jour = models.PositiveSmallIntegerField(
        choices=Jour.choices, null=True, blank=True, help_text="Pour une séance hebdomadaire."
    )
    date_unique = models.DateField(
        "date (rattrapage)",
        null=True,
        blank=True,
        help_text="Pour une séance ponctuelle (rattrapage) : laisser le jour vide, il est déduit de la date.",
    )
    heure_debut = models.TimeField("heure de début")
    heure_fin = models.TimeField("heure de fin")

    class Meta:
        verbose_name = "séance"
        verbose_name_plural = "séances"
        ordering = ["jour", "heure_debut"]

    def __str__(self):
        cible = self.groupe.nom if self.groupe_id else self.classe
        quand = f"Rattrapage {self.date_unique:%d/%m/%Y}" if self.date_unique else self.get_jour_display()
        return (
            f"{quand} {self.heure_debut:%H:%M}-{self.heure_fin:%H:%M} · "
            f"{self.matiere} ({self.get_type_display()}) · {cible}"
        )

    @property
    def est_rattrapage(self):
        return self.date_unique is not None

    @property
    def duree_heures(self):
        debut = datetime.combine(datetime.min, self.heure_debut)
        fin = datetime.combine(datetime.min, self.heure_fin)
        return (fin - debut).total_seconds() / 3600

    def derniere_date(self, au_plus_tard=None):
        """Date de la dernière occurrence de cette séance, aujourd'hui compris."""
        if self.date_unique:
            return self.date_unique
        date = au_plus_tard or timezone.localdate()
        return date - timedelta(days=(date.isoweekday() - self.jour) % 7)

    def empechement(self, date):
        """Raison pour laquelle la séance n'a pas lieu à cette date, ou None si elle a bien lieu."""
        if self.date_unique and date != self.date_unique:
            return f"Cette séance de rattrapage a lieu le {self.date_unique:%d/%m/%Y}."
        if not self.date_unique and date.isoweekday() != self.jour:
            return f"Cette séance a lieu le {self.get_jour_display().lower()}."
        debut, fin = self.classe.periode()
        if not debut <= date <= fin:
            return f"Cette date est en dehors de l'année universitaire {self.classe.annee_universitaire}."
        fermeture = JourNonTravaille.couvrant(date)
        if fermeture:
            return f"Le {date:%d/%m/%Y} est un jour non travaillé ({fermeture.nom})."
        annulation = self.annulations.filter(date=date).first()
        if annulation:
            return f"Cette séance a été annulée le {date:%d/%m/%Y}" + (f" ({annulation.motif})." if annulation.motif else ".")
        return None

    def conflits(self):
        """Liste des messages décrivant les conflits avec les autres séances (BF14).

        Deux séances sont en conflit si elles ont lieu le même jour, que leurs
        horaires se chevauchent et qu'elles partagent la même salle, le même
        enseignant, ou le même public (classe entière ou même groupe).
        Une séance de rattrapage n'est comparée qu'aux séances qui ont réellement
        lieu à sa date (une séance hebdomadaire annulée ce jour-là libère le créneau).
        """
        if not (self.jour and self.heure_debut and self.heure_fin):
            return []

        chevauchantes = Seance.objects.filter(
            jour=self.jour,
            heure_debut__lt=self.heure_fin,
            heure_fin__gt=self.heure_debut,
        ).select_related("classe__filiere", "classe__niveau", "groupe", "matiere", "enseignant", "salle")
        if self.pk:
            chevauchantes = chevauchantes.exclude(pk=self.pk)
        if self.date_unique:
            chevauchantes = chevauchantes.filter(
                Q(date_unique__isnull=True) | Q(date_unique=self.date_unique)
            ).exclude(annulations__date=self.date_unique)
        else:
            # Les rattrapages déjà passés ne bloquent pas un créneau hebdomadaire.
            chevauchantes = chevauchantes.filter(Q(date_unique__isnull=True) | Q(date_unique__gte=timezone.localdate()))

        messages = []
        if self.salle_id:
            for s in chevauchantes.filter(salle_id=self.salle_id):
                messages.append(f"La salle {s.salle} est déjà occupée : {s}.")
        if self.enseignant_id:
            for s in chevauchantes.filter(enseignant_id=self.enseignant_id):
                messages.append(f"L'enseignant {s.enseignant} a déjà une séance : {s}.")
        if self.classe_id:
            meme_public = chevauchantes.filter(classe_id=self.classe_id)
            if self.groupe_id:
                # Un groupe est en conflit avec les séances de toute la classe ou de ce même groupe.
                meme_public = meme_public.filter(Q(groupe__isnull=True) | Q(groupe_id=self.groupe_id))
            for s in meme_public:
                messages.append(f"La classe ou le groupe a déjà une séance : {s}.")
        return messages

    def clean(self):
        from structure.models import Enseignement

        if self.date_unique:
            if self.date_unique.isoweekday() == 7:
                raise ValidationError({"date_unique": "Aucune séance n'est programmée le dimanche."})
            self.jour = self.date_unique.isoweekday()
        elif not self.jour:
            raise ValidationError({"jour": "Indiquez le jour (séance hebdomadaire) ou une date (rattrapage)."})
        if self.heure_debut and self.heure_fin and self.heure_fin <= self.heure_debut:
            raise ValidationError({"heure_fin": "L'heure de fin doit être après l'heure de début."})
        if self.groupe_id and self.classe_id and self.groupe.classe_id != self.classe_id:
            raise ValidationError({"groupe": "Ce groupe n'appartient pas à la classe choisie."})
        if self.matiere_id and self.classe_id and (
            self.matiere.filiere_id != self.classe.filiere_id or self.matiere.niveau_id != self.classe.niveau_id
        ):
            raise ValidationError({"matiere": "Cette matière n'appartient pas à la filière et au niveau de la classe."})
        if self.enseignant_id and self.enseignant.role != "ENSEIGNANT":
            raise ValidationError({"enseignant": "L'utilisateur choisi n'est pas un enseignant."})
        if (
            self.enseignant_id
            and self.matiere_id
            and self.classe_id
            and not Enseignement.objects.filter(
                enseignant_id=self.enseignant_id, matiere_id=self.matiere_id, classe_id=self.classe_id
            ).exists()
        ):
            raise ValidationError(
                {
                    "enseignant": f"{self.enseignant} n'est pas affecté(e) à « {self.matiere} » pour cette classe. "
                    "Créez d'abord l'affectation (Filières, classes et matières › Affectations enseignants)."
                }
            )
        conflits = self.conflits()
        if conflits:
            raise ValidationError(conflits)

    def save(self, *args, **kwargs):
        if self.date_unique:
            self.jour = self.date_unique.isoweekday()
        super().save(*args, **kwargs)

    def public(self):
        """Étudiants concernés par la séance."""
        from comptes.models import Utilisateur

        etudiants = Utilisateur.objects.filter(role=Utilisateur.Role.ETUDIANT, classe_id=self.classe_id, is_active=True)
        if self.groupe_id:
            etudiants = etudiants.filter(groupe_id=self.groupe_id)
        return etudiants


class AnnulationSeance(models.Model):
    """Annulation d'une séance hebdomadaire à une date précise (absence de l'enseignant, événement…)."""

    seance = models.ForeignKey(Seance, verbose_name="séance", on_delete=models.CASCADE, related_name="annulations")
    date = models.DateField()
    motif = models.CharField(max_length=200, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "annulation de séance"
        verbose_name_plural = "annulations de séances"
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["seance", "date"], name="annulation_unique_par_date")]

    def __str__(self):
        return f"{self.seance} – annulée le {self.date:%d/%m/%Y}"

    def clean(self):
        if not (self.seance_id and self.date):
            return
        if self.seance.date_unique and self.date != self.seance.date_unique:
            raise ValidationError({"date": f"Cette séance de rattrapage a lieu le {self.seance.date_unique:%d/%m/%Y}."})
        if not self.seance.date_unique and self.date.isoweekday() != self.seance.jour:
            raise ValidationError({"date": f"Cette séance a lieu le {self.seance.get_jour_display().lower()}."})
        if self.seance.absences.filter(date=self.date).exists():
            raise ValidationError("L'appel a déjà été fait pour cette séance à cette date : supprimez d'abord les absences.")

    def notifier(self):
        """Prévient l'enseignant et les étudiants concernés."""
        from notifications.models import Notification

        message = (
            f"Séance annulée : {self.seance.matiere} ({self.seance.get_type_display()}) du "
            f"{date_format(self.date, 'l j F')} à {self.seance.heure_debut:%H:%M}"
            + (f" – {self.motif}." if self.motif else ".")
        )
        lien = f"{reverse('emplois:mon_emploi_du_temps')}?semaine={self.date.isoformat()}"
        destinataires = [self.seance.enseignant, *self.seance.public()]
        Notification.objects.bulk_create([Notification(destinataire=u, message=message, lien=lien) for u in destinataires])


class JourNonTravaille(models.Model):
    """Jour férié ou période de vacances : aucune séance n'a lieu et l'appel est impossible."""

    class Type(models.TextChoices):
        FERIE = "FERIE", "Jour férié"
        VACANCES = "VACANCES", "Vacances"
        AUTRE = "AUTRE", "Autre fermeture"

    nom = models.CharField(max_length=100, help_text="Ex. : Fête du Trône, vacances de printemps…")
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.FERIE)
    date_debut = models.DateField("du")
    date_fin = models.DateField("au", help_text="Identique à la date de début pour un seul jour.")

    class Meta:
        verbose_name = "jour non travaillé"
        verbose_name_plural = "calendrier : jours non travaillés"
        ordering = ["date_debut"]

    def __str__(self):
        if self.date_debut == self.date_fin:
            return f"{self.nom} ({self.date_debut:%d/%m/%Y})"
        return f"{self.nom} ({self.date_debut:%d/%m/%Y} → {self.date_fin:%d/%m/%Y})"

    def clean(self):
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La date de fin doit être après la date de début."})

    @classmethod
    def couvrant(cls, date):
        return cls.objects.filter(date_debut__lte=date, date_fin__gte=date).first()
