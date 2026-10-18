from django.urls import path

from . import views

app_name = "evaluations"

urlpatterns = [
    path("", views.calendrier, name="calendrier"),
    path("examens/nouveau/", views.nouvel_examen, name="nouvel_examen"),
    path("examens/<int:pk>/supprimer/", views.supprimer_examen, name="supprimer_examen"),
    path("devoirs/", views.devoirs, name="devoirs"),
    path("devoirs/nouveau/", views.nouveau_devoir, name="nouveau_devoir"),
    path("devoirs/<int:pk>/", views.devoir, name="devoir"),
    path("devoirs/<int:pk>/sujet/", views.sujet, name="sujet"),
    path("devoirs/<int:pk>/rendus.zip", views.rendus_zip, name="rendus_zip"),
    path("devoirs/<int:pk>/supprimer/", views.supprimer_devoir, name="supprimer_devoir"),
    path("rendus/<int:pk>/fichier/", views.fichier_rendu, name="fichier_rendu"),
]
