from django.contrib import admin

from .models import Absence, AlerteAbsence, Justification


@admin.register(Absence)
class AbsenceAdmin(admin.ModelAdmin):
    list_display = ("etudiant", "seance", "date", "nature", "statut", "saisie_par")
    list_filter = ("nature", "statut", "seance__classe", "seance__matiere")
    search_fields = ("etudiant__last_name", "etudiant__first_name", "etudiant__cne")
    date_hierarchy = "date"
    list_select_related = (
        "etudiant", "seance__classe__filiere", "seance__classe__niveau", "seance__groupe", "seance__matiere", "saisie_par"
    )


@admin.register(Justification)
class JustificationAdmin(admin.ModelAdmin):
    list_display = ("absence", "statut", "date_depot", "traitee_par")
    list_select_related = (
        "absence__etudiant", "absence__seance__classe__filiere", "absence__seance__classe__niveau",
        "absence__seance__groupe", "absence__seance__matiere", "traitee_par",
    )
    list_filter = ("statut",)


@admin.register(AlerteAbsence)
class AlerteAbsenceAdmin(admin.ModelAdmin):
    list_display = ("etudiant", "matiere", "niveau", "heures_non_justifiees", "taux", "date_creation")
    list_filter = ("niveau", "matiere")
    list_select_related = ("etudiant", "matiere")
    search_fields = ("etudiant__last_name", "etudiant__first_name", "etudiant__cne")
