from django.conf import settings
from django.db import models

from config.validateurs import VALIDATEURS_RESSOURCE


class Ressource(models.Model):
    """Support pédagogique déposé par un enseignant (BF06).

    Un étudiant ne voit que les ressources dont la matière correspond à la
    filière et au niveau de sa classe (BF07).
    """

    class Type(models.TextChoices):
        COURS = "COURS", "Cours"
        TD = "TD", "TD"
        TP = "TP", "TP"

    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.COURS)
    matiere = models.ForeignKey("structure.Matiere", verbose_name="matière", on_delete=models.CASCADE, related_name="ressources")
    fichier = models.FileField(upload_to="ressources/%Y/%m/", validators=VALIDATEURS_RESSOURCE)
    deposee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="déposée par",
        on_delete=models.PROTECT,
        related_name="ressources_deposees",
    )
    date_depot = models.DateTimeField("date de dépôt", auto_now_add=True)

    class Meta:
        verbose_name = "ressource pédagogique"
        verbose_name_plural = "ressources pédagogiques"
        ordering = ["-date_depot"]

    def __str__(self):
        return f"{self.get_type_display()} – {self.titre}"

    @classmethod
    def visibles_par(cls, etudiant):
        """Ressources de la filière et du niveau de la classe de l'étudiant."""
        if not etudiant.classe_id:
            return cls.objects.none()
        return cls.objects.filter(
            matiere__filiere_id=etudiant.classe.filiere_id,
            matiere__niveau_id=etudiant.classe.niveau_id,
        )
