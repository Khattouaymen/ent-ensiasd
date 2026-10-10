from django.urls import path

from . import views

app_name = "ressources"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("deposer/", views.deposer, name="deposer"),
    path("<int:pk>/telecharger/", views.telecharger, name="telecharger"),
    path("<int:pk>/supprimer/", views.supprimer, name="supprimer"),
]
