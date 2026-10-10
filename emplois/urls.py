from django.urls import path

from . import views

app_name = "emplois"

urlpatterns = [
    path("", views.mon_emploi_du_temps, name="mon_emploi_du_temps"),
    path("classes/", views.emploi_du_temps_classe, name="emploi_du_temps_classe"),
]
