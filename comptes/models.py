from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.db import models


class UtilisateurManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """« manage.py createsuperuser » crée un compte avec le rôle Administrateur."""
        extra_fields.setdefault("role", "ADMIN")
        if extra_fields["role"] != "ADMIN":
            raise ValueError("Un superutilisateur doit avoir le rôle ADMIN.")
        return super().create_superuser(username, email, password, **extra_fields)


class Utilisateur(AbstractUser):
    """Compte de la plateforme. Le rôle détermine les fonctionnalités accessibles."""

    class Role(models.TextChoices):
        ETUDIANT = "ETUDIANT", "Étudiant"
        ENSEIGNANT = "ENSEIGNANT", "Enseignant"
        SCOLARITE = "SCOLARITE", "Scolarité"
        ADMIN = "ADMIN", "Administrateur"

    role = models.CharField("rôle", max_length=20, choices=Role.choices, default=Role.ETUDIANT)
    telephone = models.CharField("téléphone", max_length=20, blank=True)
    doit_changer_mot_de_passe = models.BooleanField(
        "doit changer son mot de passe",
        default=False,
        help_text="Le compte devra choisir un nouveau mot de passe à sa prochaine connexion "
        "(cas des comptes créés par import avec un mot de passe provisoire).",
    )

    # Informations propres aux étudiants
    cne = models.CharField("CNE / code Massar", max_length=20, blank=True)
    classe = models.ForeignKey(
        "structure.Classe",
        verbose_name="classe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etudiants",
    )
    groupe = models.ForeignKey(
        "structure.Groupe",
        verbose_name="groupe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etudiants",
    )

    objects = UtilisateurManager()

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.get_full_name() or self.username

    # Raccourcis utilisés dans les vues et les gabarits
    @property
    def est_etudiant(self):
        return self.role == self.Role.ETUDIANT

    @property
    def est_enseignant(self):
        return self.role == self.Role.ENSEIGNANT

    @property
    def est_scolarite(self):
        return self.role == self.Role.SCOLARITE

    @property
    def est_admin(self):
        return self.role == self.Role.ADMIN

    def clean(self):
        super().clean()
        if self.role != self.Role.ETUDIANT and (self.classe_id or self.groupe_id):
            raise ValidationError("Seul un étudiant peut être affecté à une classe ou à un groupe.")
        if self.groupe_id and self.groupe.classe_id != self.classe_id:
            raise ValidationError({"groupe": "Le groupe doit appartenir à la classe de l'étudiant."})

    def save(self, *args, **kwargs):
        # Les droits d'administration découlent uniquement du rôle : un compte qui
        # quitte le rôle ADMIN perd aussitôt l'accès à l'interface d'administration.
        est_admin = self.role == self.Role.ADMIN
        self.is_staff = est_admin
        self.is_superuser = est_admin
        super().save(*args, **kwargs)
