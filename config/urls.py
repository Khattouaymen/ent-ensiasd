from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse_lazy

from comptes.forms import ConnexionForm, DemandeReinitialisationForm, NouveauMotDePasseForm
from comptes.views import ChangerMotDePasse, importer_etudiants, modele_import, mon_compte, statistiques, tableau_de_bord

urlpatterns = [
    path("", tableau_de_bord, name="tableau_de_bord"),
    path(
        "connexion/",
        auth_views.LoginView.as_view(
            template_name="comptes/connexion.html",
            authentication_form=ConnexionForm,
            redirect_authenticated_user=True,
        ),
        name="connexion",
    ),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),
    path("mon-compte/", mon_compte, name="mon_compte"),
    path("mon-compte/mot-de-passe/", ChangerMotDePasse.as_view(), name="changer_mot_de_passe"),
    # Mot de passe oublié : lien de réinitialisation envoyé par e-mail
    path(
        "mot-de-passe-oublie/",
        auth_views.PasswordResetView.as_view(
            form_class=DemandeReinitialisationForm,
            template_name="comptes/reinitialisation_demande.html",
            email_template_name="comptes/email_reinitialisation.txt",
            subject_template_name="comptes/email_reinitialisation_sujet.txt",
            success_url=reverse_lazy("reinitialisation_envoyee"),
        ),
        name="mot_de_passe_oublie",
    ),
    path(
        "mot-de-passe-oublie/envoye/",
        auth_views.PasswordResetDoneView.as_view(template_name="comptes/reinitialisation_envoyee.html"),
        name="reinitialisation_envoyee",
    ),
    path(
        "reinitialiser/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            form_class=NouveauMotDePasseForm,
            template_name="comptes/reinitialisation_confirmation.html",
            success_url=reverse_lazy("reinitialisation_terminee"),
        ),
        name="reinitialiser_mot_de_passe",
    ),
    path(
        "reinitialiser/termine/",
        auth_views.PasswordResetCompleteView.as_view(template_name="comptes/reinitialisation_terminee.html"),
        name="reinitialisation_terminee",
    ),
    path("comptes/importer/", importer_etudiants, name="importer_etudiants"),
    path("comptes/importer/modele.csv", modele_import, name="modele_import"),
    path("statistiques/", statistiques, name="statistiques"),
    path("emploi-du-temps/", include("emplois.urls")),
    path("ressources/", include("ressources.urls")),
    path("documents/", include("documents.urls")),
    path("absences/", include("absences.urls")),
    path("notifications/", include("notifications.urls")),
    path("annonces/", include("annonces.urls")),
    path("admin/", admin.site.urls),
]
