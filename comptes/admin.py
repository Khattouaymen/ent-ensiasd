from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Utilisateur

admin.site.site_header = "ENT ENSIASD – Administration"
admin.site.site_title = "ENT ENSIASD"
admin.site.index_title = "Gestion de l'établissement"


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ("username", "last_name", "first_name", "role", "classe", "groupe", "is_active")
    list_filter = ("role", "classe", "is_active")
    list_select_related = ("classe__filiere", "classe__niveau", "groupe__classe__filiere", "groupe__classe__niveau")
    search_fields = ("username", "first_name", "last_name", "email", "cne")
    autocomplete_fields = ("classe", "groupe")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Identité", {"fields": ("first_name", "last_name", "email", "telephone")}),
        ("Rôle et affectation", {"fields": ("role", "cne", "classe", "groupe")}),
        ("Statut", {"fields": ("is_active", "doit_changer_mot_de_passe", "last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "first_name", "last_name", "email", "role", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("last_login", "date_joined")
