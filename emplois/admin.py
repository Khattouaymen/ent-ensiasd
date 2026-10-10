from django import forms
from django.contrib import admin

from .models import AnnulationSeance, JourNonTravaille, Seance


class SelectGroupe(forms.Select):
    """Liste des groupes dont chaque option porte sa classe (data-classe), pour le filtrage côté navigateur."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        groupe = getattr(value, "instance", None)
        if groupe is not None:
            option["attrs"]["data-classe"] = groupe.classe_id
        return option


class SeanceForm(forms.ModelForm):
    class Meta:
        model = Seance
        fields = "__all__"
        widgets = {"groupe": SelectGroupe}


@admin.register(Seance)
class SeanceAdmin(admin.ModelAdmin):
    """Construction de l'emploi du temps (BF13).

    Les conflits de salle, d'enseignant et de classe sont détectés par
    ``Seance.clean()`` et affichés comme erreurs du formulaire (BF14).
    """

    form = SeanceForm
    list_display = (
        "jour", "date_unique", "heure_debut", "heure_fin", "classe", "groupe", "matiere", "type", "enseignant", "salle"
    )
    list_filter = ("classe", "jour", "type", "salle", "enseignant")
    list_select_related = (
        "classe__filiere", "classe__niveau", "groupe__classe__filiere", "groupe__classe__niveau",
        "matiere", "enseignant", "salle",
    )
    autocomplete_fields = ("enseignant",)
    ordering = ("classe", "date_unique", "jour", "heure_debut")
    fieldsets = (
        ("Public", {"fields": ("classe", "groupe")}),
        ("Enseignement", {"fields": ("matiere", "type", "enseignant", "salle")}),
        (
            "Quand",
            {
                "fields": ("jour", "date_unique", "heure_debut", "heure_fin"),
                "description": "Séance hebdomadaire : indiquez le jour. Rattrapage : indiquez seulement la date.",
            },
        ),
    )

    class Media:
        js = ("admin/js/seance_groupes.js",)


@admin.register(AnnulationSeance)
class AnnulationSeanceAdmin(admin.ModelAdmin):
    list_display = ("seance", "date", "motif")
    list_filter = ("seance__classe",)
    list_select_related = ("seance__classe__filiere", "seance__classe__niveau", "seance__groupe", "seance__matiere")
    date_hierarchy = "date"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            obj.notifier()
            self.message_user(request, "L'enseignant et les étudiants concernés ont été notifiés.")


@admin.register(JourNonTravaille)
class JourNonTravailleAdmin(admin.ModelAdmin):
    list_display = ("nom", "type", "date_debut", "date_fin")
    list_filter = ("type",)
