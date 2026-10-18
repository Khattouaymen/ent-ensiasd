"""Outils communs aux formulaires et aux téléchargements."""

import os

from django import forms
from django.core.paginator import Paginator
from django.http import FileResponse, Http404


class FormulaireBootstrap:
    """Ajoute les classes CSS Bootstrap aux champs d'un formulaire Django."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            widget = champ.widget
            if isinstance(widget, forms.CheckboxInput):
                classe = "form-check-input"
            elif isinstance(widget, forms.Select):
                classe = "form-select"
            else:
                classe = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {classe}".strip()


def accepter_extensions(champ, extensions):
    """Limite le sélecteur de fichiers du navigateur aux extensions autorisées."""
    champ.widget.attrs["accept"] = ",".join(f".{e}" for e in extensions)


def telecharger(fichier):
    """Envoie un fichier déposé. À n'appeler qu'après avoir vérifié les droits de l'utilisateur."""
    if not fichier:
        raise Http404("Aucun fichier.")
    try:
        contenu = fichier.open("rb")
    except FileNotFoundError:
        raise Http404("Fichier introuvable.") from None
    return FileResponse(contenu, as_attachment=True, filename=os.path.basename(fichier.name))


def paginer(request, elements, par_page=20):
    """Page demandée (?page=…) d'une liste ; les numéros invalides renvoient la première ou la dernière page."""
    return Paginator(elements, par_page).get_page(request.GET.get("page"))
