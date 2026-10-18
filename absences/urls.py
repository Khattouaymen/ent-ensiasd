from django.urls import path

from . import views

app_name = "absences"

urlpatterns = [
    # Enseignant / administrateur
    path("appel/", views.choisir_seance, name="choisir_seance"),
    path("appel/<int:seance_id>/", views.appel, name="appel"),
    path("suivi/", views.suivi, name="suivi"),
    # Étudiant
    path("mes-absences/", views.mes_absences, name="mes_absences"),
    path("mes-absences/releve.pdf", views.mon_releve, name="mon_releve"),
    path("<int:absence_id>/justifier/", views.justifier, name="justifier"),
    # Scolarité / administrateur
    path("justifications/", views.justifications, name="justifications"),
    path("justifications/<int:pk>/", views.traiter_justification, name="traiter_justification"),
    path("justifications/<int:pk>/piece-jointe/", views.piece_jointe, name="piece_jointe"),
    path("classes/", views.par_classe, name="par_classe"),
    path("classes/<int:classe_id>/export.csv", views.exporter, name="exporter"),
    path("etudiants/<int:etudiant_id>/releve.pdf", views.releve_etudiant, name="releve_etudiant"),
]
