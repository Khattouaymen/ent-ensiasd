from django.urls import path

from . import views

app_name = "annonces"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("nouvelle/", views.nouvelle, name="nouvelle"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/supprimer/", views.supprimer, name="supprimer"),
]
