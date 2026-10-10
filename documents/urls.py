from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("nouvelle/", views.nouvelle, name="nouvelle"),
    path("<int:pk>/traiter/", views.traiter, name="traiter"),
    path("<int:pk>/telecharger/", views.telecharger, name="telecharger"),
]
