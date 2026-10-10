from django.contrib import admin
from django.db.models import Count, Q

from .models import Classe, Enseignement, Filiere, Groupe, Matiere, Niveau, Salle


@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display = ("code", "nom")
    search_fields = ("code", "nom")


@admin.register(Niveau)
class NiveauAdmin(admin.ModelAdmin):
    list_display = ("nom", "ordre")


class GroupeInline(admin.TabularInline):
    model = Groupe
    extra = 1


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ("__str__", "filiere", "niveau", "annee_universitaire", "nb_etudiants")
    list_filter = ("filiere", "niveau", "annee_universitaire")
    search_fields = ("filiere__code", "filiere__nom", "niveau__nom")
    inlines = [GroupeInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _nb_etudiants=Count("etudiants", filter=Q(etudiants__role="ETUDIANT"))
        )

    @admin.display(description="étudiants", ordering="_nb_etudiants")
    def nb_etudiants(self, obj):
        return obj._nb_etudiants


@admin.register(Groupe)
class GroupeAdmin(admin.ModelAdmin):
    list_display = ("__str__", "classe")
    list_select_related = ("classe__filiere", "classe__niveau")
    list_filter = ("classe",)
    search_fields = ("nom", "classe__filiere__code")


@admin.register(Matiere)
class MatiereAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "filiere", "niveau", "volume_horaire")
    list_select_related = ("filiere", "niveau")
    list_filter = ("filiere", "niveau")
    search_fields = ("code", "nom")


@admin.register(Salle)
class SalleAdmin(admin.ModelAdmin):
    list_display = ("nom", "type", "capacite")
    list_filter = ("type",)


@admin.register(Enseignement)
class EnseignementAdmin(admin.ModelAdmin):
    list_display = ("enseignant", "matiere", "classe")
    list_select_related = ("enseignant", "matiere", "classe__filiere", "classe__niveau")
    list_filter = ("classe", "matiere")
    autocomplete_fields = ("enseignant",)
