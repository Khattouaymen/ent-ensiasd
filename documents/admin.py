from django.contrib import admin

from .models import DemandeDocument


@admin.register(DemandeDocument)
class DemandeDocumentAdmin(admin.ModelAdmin):
    list_display = ("etudiant", "type_document", "statut", "date_demande", "traitee_par")
    list_filter = ("statut", "type_document")
    list_select_related = ("etudiant", "traitee_par")
    search_fields = ("etudiant__last_name", "etudiant__first_name", "etudiant__cne")
