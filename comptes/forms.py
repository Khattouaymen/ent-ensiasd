import time

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from config.formulaires import FormulaireBootstrap, accepter_extensions
from config.validateurs import TailleMaximale
from structure.models import Classe

# Protection contre les attaques par force brute (BNF01)
MAX_ECHECS_CONNEXION = 5
DUREE_BLOCAGE_SECONDES = 15 * 60

# Mot de passe oublié : au plus 3 e-mails par adresse et par heure
MAX_EMAILS_REINITIALISATION = 3
DUREE_LIMITE_REINITIALISATION_SECONDES = 60 * 60


def compter_tentative(cle, duree):
    """Ajoute une tentative au compteur « cle » et renvoie le nouveau total.

    Le compteur expire « duree » secondes après la première tentative. cache.incr() ne convient
    pas : avec le cache en base, il remet l'expiration à la valeur par défaut (5 minutes).
    """
    maintenant = time.time()
    nombre, fin = cache.get(cle, (0, maintenant + duree))
    cache.set(cle, (nombre + 1, fin), timeout=max(1, round(fin - maintenant)))
    return nombre + 1


def nombre_tentatives(cle):
    return cache.get(cle, (0, 0))[0]


def cle_tentatives(identifiant, request):
    """Les échecs sont comptés par couple identifiant + adresse IP.

    Bloquer seulement par identifiant permettrait à n'importe qui de verrouiller
    le compte d'un autre ; bloquer seulement par IP bloquerait toute une salle
    derrière la même connexion.
    """
    ip = ""
    if request:
        ip = (settings.ENTETE_IP_CLIENT and request.META.get(settings.ENTETE_IP_CLIENT)) or request.META.get("REMOTE_ADDR", "")
    return f"connexion:{(identifiant or '').strip().lower()}:{ip}"


class ConnexionForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Identifiant ou mot de passe incorrect.",
        "bloque": "Trop de tentatives de connexion. Réessayez dans 15 minutes.",
    }

    def clean(self):
        cle = cle_tentatives(self.cleaned_data.get("username"), self.request)
        if nombre_tentatives(cle) >= MAX_ECHECS_CONNEXION:
            raise ValidationError(self.error_messages["bloque"], code="bloque")
        try:
            donnees = super().clean()
        except ValidationError:
            # Le délai de blocage court depuis le premier échec
            compter_tentative(cle, DUREE_BLOCAGE_SECONDES)
            raise
        cache.delete(cle)
        return donnees


class ChangementMotDePasseForm(FormulaireBootstrap, PasswordChangeForm):
    pass


class DemandeReinitialisationForm(FormulaireBootstrap, PasswordResetForm):
    def get_users(self, email):
        """Limite les e-mails envoyés à une même adresse, pour qu'on ne puisse pas inonder une boîte.

        Au-delà de la limite, aucun e-mail n'est envoyé, mais la page de confirmation habituelle
        s'affiche quand même : elle ne doit pas révéler si l'adresse correspond à un compte.
        """
        cle = f"reinitialisation:{email.strip().lower()}"
        if compter_tentative(cle, DUREE_LIMITE_REINITIALISATION_SECONDES) > MAX_EMAILS_REINITIALISATION:
            return iter(())
        return super().get_users(email)


class NouveauMotDePasseForm(FormulaireBootstrap, SetPasswordForm):
    pass


class ImportEtudiantsForm(FormulaireBootstrap, forms.Form):
    classe = forms.ModelChoiceField(queryset=Classe.objects.all(), label="Classe des étudiants importés")
    fichier = forms.FileField(
        label="Fichier CSV",
        validators=[FileExtensionValidator(["csv"]), TailleMaximale("TAILLE_MAX_JUSTIFICATIF_MO")],
        help_text="Colonnes : nom ; prenom ; cne ; email (facultatif) ; groupe (facultatif). "
        "Depuis Excel : Fichier › Enregistrer sous › « CSV UTF-8 ».",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accepter_extensions(self.fields["fichier"], ["csv"])
