from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


class Filiere(models.Model):
    code = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=200)

    class Meta:
        verbose_name = "filière"
        verbose_name_plural = "filières"
        ordering = ["code"]

    def __str__(self):
        return self.code


class Niveau(models.Model):
    nom = models.CharField(max_length=50, unique=True, help_text="Ex. : 1ère année, Semestre 3…")
    ordre = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = "niveau"
        verbose_name_plural = "niveaux"
        ordering = ["ordre"]

    def __str__(self):
        return self.nom


class ClasseManager(models.Manager):
    def get_queryset(self):
        # La filière et le niveau servent à l'affichage de chaque classe : on les charge d'office.
        return super().get_queryset().select_related("filiere", "niveau")


class Classe(models.Model):
    # Mois de la rentrée : l'année universitaire va du 1er septembre au 31 août
    MOIS_RENTREE = 9

    filiere = models.ForeignKey(Filiere, verbose_name="filière", on_delete=models.PROTECT, related_name="classes")
    niveau = models.ForeignKey(Niveau, on_delete=models.PROTECT, related_name="classes")
    annee_universitaire = models.CharField(
        "année universitaire",
        max_length=9,
        help_text="Ex. : 2026/2027",
        validators=[RegexValidator(r"^\d{4}/\d{4}$", "Format attendu : 2026/2027.")],
    )

    objects = ClasseManager()

    class Meta:
        verbose_name = "classe"
        verbose_name_plural = "classes"
        ordering = ["filiere__code", "niveau__ordre"]
        constraints = [
            models.UniqueConstraint(
                fields=["filiere", "niveau", "annee_universitaire"], name="classe_unique_par_annee"
            )
        ]

    def __str__(self):
        return f"{self.filiere.code} – {self.niveau} ({self.annee_universitaire})"

    def clean(self):
        annees = self.annee_universitaire.split("/")
        if len(annees) == 2 and all(a.isdigit() for a in annees) and int(annees[1]) != int(annees[0]) + 1:
            raise ValidationError({"annee_universitaire": "Les deux années doivent se suivre (ex. : 2026/2027)."})

    def periode(self):
        """Premier et dernier jour de l'année universitaire de la classe."""
        annee = int(self.annee_universitaire[:4])
        rentree_suivante = date(annee + 1, self.MOIS_RENTREE, 1)
        return date(annee, self.MOIS_RENTREE, 1), rentree_suivante - timedelta(days=1)


class GroupeManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("classe__filiere", "classe__niveau")


class Groupe(models.Model):
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="groupes")
    nom = models.CharField(max_length=30, help_text="Ex. : G1, G2…")

    objects = GroupeManager()

    class Meta:
        verbose_name = "groupe"
        verbose_name_plural = "groupes"
        ordering = ["classe", "nom"]
        constraints = [models.UniqueConstraint(fields=["classe", "nom"], name="groupe_unique_par_classe")]

    def __str__(self):
        return f"{self.classe.filiere.code} {self.classe.niveau} – {self.nom}"


class Matiere(models.Model):
    code = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=200)
    filiere = models.ForeignKey(Filiere, verbose_name="filière", on_delete=models.PROTECT, related_name="matieres")
    niveau = models.ForeignKey(Niveau, on_delete=models.PROTECT, related_name="matieres")
    volume_horaire = models.PositiveSmallIntegerField("volume horaire (h)", default=0)

    class Meta:
        verbose_name = "matière"
        verbose_name_plural = "matières"
        ordering = ["filiere__code", "niveau__ordre", "nom"]

    def __str__(self):
        return self.nom


class Salle(models.Model):
    class Type(models.TextChoices):
        AMPHI = "AMPHI", "Amphithéâtre"
        SALLE = "SALLE", "Salle de cours"
        LABO = "LABO", "Salle informatique / TP"

    nom = models.CharField(max_length=50, unique=True)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.SALLE)
    capacite = models.PositiveSmallIntegerField("capacité", default=30)

    class Meta:
        verbose_name = "salle"
        verbose_name_plural = "salles"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Enseignement(models.Model):
    """Affectation d'un enseignant à une matière pour une classe (BF12)."""

    enseignant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enseignements",
        limit_choices_to={"role": "ENSEIGNANT"},
    )
    matiere = models.ForeignKey(Matiere, verbose_name="matière", on_delete=models.CASCADE, related_name="enseignements")
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="enseignements")

    class Meta:
        verbose_name = "affectation enseignant"
        verbose_name_plural = "affectations enseignants"
        constraints = [
            models.UniqueConstraint(fields=["enseignant", "matiere", "classe"], name="enseignement_unique")
        ]

    def __str__(self):
        return f"{self.enseignant} – {self.matiere} ({self.classe})"

    def clean(self):
        if self.enseignant_id and self.enseignant.role != "ENSEIGNANT":
            raise ValidationError({"enseignant": "L'utilisateur choisi n'est pas un enseignant."})
        if self.matiere_id and self.classe_id and (
            self.matiere.filiere_id != self.classe.filiere_id or self.matiere.niveau_id != self.classe.niveau_id
        ):
            raise ValidationError({"matiere": "Cette matière n'appartient pas à la filière et au niveau de la classe."})
