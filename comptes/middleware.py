from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

# Pages accessibles même quand le mot de passe doit être changé
CHEMINS_AUTORISES = ("changer_mot_de_passe", "deconnexion")


class ChangementMotDePasseObligatoire:
    """Oblige un compte créé avec un mot de passe provisoire à le changer avant d'utiliser l'ENT."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.doit_changer_mot_de_passe:
            autorises = [reverse(nom) for nom in CHEMINS_AUTORISES]
            if request.path not in autorises and not request.path.startswith("/static/"):
                messages.info(request, "Pour sécuriser votre compte, choisissez un nouveau mot de passe.")
                return redirect("changer_mot_de_passe")
        return self.get_response(request)
