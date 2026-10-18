from django.contrib import admin

from .models import Annonce


@admin.register(Annonce)
class AnnonceAdmin(admin.ModelAdmin):
    list_display = ("titre", "destinataires_libelle", "importante", "auteur", "date_publication", "date_fin")
    list_filter = ("importante", "filiere", "classe")
    list_select_related = ("filiere", "classe__filiere", "classe__niveau", "auteur")
    search_fields = ("titre", "contenu")

    @admin.display(description="destinataires")
    def destinataires_libelle(self, annonce):
        return annonce.destinataires_libelle

    def save_model(self, request, annonce, form, change):
        if not change:
            annonce.auteur = request.user
        super().save_model(request, annonce, form, change)
        if not change:
            annonce.notifier()
