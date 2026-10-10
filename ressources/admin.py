from django.contrib import admin

from .models import Ressource


@admin.register(Ressource)
class RessourceAdmin(admin.ModelAdmin):
    list_display = ("titre", "type", "matiere", "deposee_par", "date_depot")
    list_filter = ("type", "matiere__filiere", "matiere__niveau")
    list_select_related = ("matiere", "deposee_par")
    search_fields = ("titre", "description")
