from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("<int:pk>/", views.ouvrir, name="ouvrir"),
    path("tout-marquer-lu/", views.tout_marquer_lu, name="tout_marquer_lu"),
]
