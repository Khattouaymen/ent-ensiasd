from django.contrib import admin

from .models import Devoir, Examen, Rendu


@admin.register(Examen)
class ExamenAdmin(admin.ModelAdmin):
    list_display = ("intitule", "type", "matiere", "classe", "groupe", "date", "heure_debut", "salle")
    list_filter = ("type", "classe", "matiere")
    list_select_related = ("matiere", "classe__filiere", "classe__niveau", "groupe", "salle")
    date_hierarchy = "date"

    def save_model(self, request, examen, form, change):
        if not change:
            examen.cree_par = request.user
        super().save_model(request, examen, form, change)
        if not change:
            examen.notifier()


class RenduInline(admin.TabularInline):
    model = Rendu
    extra = 0
    fields = ("etudiant", "fichier", "date_depot", "en_retard")
    readonly_fields = fields
    can_delete = False


@admin.register(Devoir)
class DevoirAdmin(admin.ModelAdmin):
    """Les devoirs sont créés par les enseignants depuis l'ENT ; l'administration les consulte."""

    list_display = ("titre", "matiere", "classe", "groupe", "enseignant", "date_limite")
    list_filter = ("classe", "matiere")
    list_select_related = ("matiere", "classe__filiere", "classe__niveau", "groupe", "enseignant")
    inlines = [RenduInline]

    def has_add_permission(self, request):
        return False

    def delete_model(self, request, devoir):
        devoir.supprimer_fichiers()
        super().delete_model(request, devoir)

    def delete_queryset(self, request, devoirs):  # action « Supprimer les devoirs sélectionnés »
        for devoir in devoirs:
            devoir.supprimer_fichiers()
        super().delete_queryset(request, devoirs)
