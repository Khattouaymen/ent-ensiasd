from django import forms
from django.db.models import Q

from config.formulaires import FormulaireBootstrap, accepter_extensions
from config.validateurs import EXTENSIONS_RESSOURCE
from structure.models import Matiere

from .models import Ressource


def matieres_enseignees(enseignant):
    """Matières affectées à l'enseignant ou pour lesquelles il a des séances."""
    return Matiere.objects.filter(Q(enseignements__enseignant=enseignant) | Q(seances__enseignant=enseignant)).distinct()


class RessourceForm(FormulaireBootstrap, forms.ModelForm):
    class Meta:
        model = Ressource
        fields = ["titre", "type", "matiere", "description", "fichier"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, enseignant, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["matiere"].queryset = matieres_enseignees(enseignant).select_related("filiere", "niveau")
        self.fields["matiere"].label_from_instance = lambda m: f"{m.nom} ({m.filiere.code} – {m.niveau})"
        accepter_extensions(self.fields["fichier"], EXTENSIONS_RESSOURCE)
        self.fields["fichier"].help_text = "Formats acceptés : " + ", ".join(EXTENSIONS_RESSOURCE) + "."
