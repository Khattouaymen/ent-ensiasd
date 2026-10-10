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
        if cache.get(cle, 0) >= MAX_ECHECS_CONNEXION:
            raise ValidationError(self.error_messages["bloque"], code="bloque")
        try:
            donnees = super().clean()
        except ValidationError:
            # add() ne fait rien si la clé existe déjà : le délai court depuis le premier échec
            cache.add(cle, 0, DUREE_BLOCAGE_SECONDES)
            cache.incr(cle)
            raise
        cache.delete(cle)
        return donnees


class ChangementMotDePasseForm(FormulaireBootstrap, PasswordChangeForm):
    pass


class DemandeReinitialisationForm(FormulaireBootstrap, PasswordResetForm):
    pass


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
