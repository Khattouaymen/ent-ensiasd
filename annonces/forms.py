from django import forms
from django.utils import timezone

from config.formulaires import FormulaireBootstrap
from structure.models import Classe, Filiere

from .models import Annonce

TOUT_L_ETABLISSEMENT = "tous"


class AnnonceForm(FormulaireBootstrap, forms.ModelForm):
    """Le personnel administratif cible tout l'établissement, une filière ou une classe ;
    un enseignant, l'une des classes où il enseigne."""

    destinataires = forms.ChoiceField(label="Destinataires")

    class Meta:
        model = Annonce
        fields = ["titre", "destinataires", "contenu", "importante", "date_fin"]
        widgets = {
            "contenu": forms.Textarea(attrs={"rows": 6}),
            "date_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, auteur, **kwargs):
        super().__init__(*args, **kwargs)
        if auteur.est_enseignant:
            classes = Classe.objects.filter(enseignements__enseignant=auteur).distinct()
            choix = [(f"c-{c.pk}", str(c)) for c in classes]
        else:
            choix = [
                ("Établissement", [(TOUT_L_ETABLISSEMENT, "Tout l'établissement")]),
                ("Filières", [(f"f-{f.pk}", f"Filière {f.code} – {f.nom}") for f in Filiere.objects.all()]),
                ("Classes", [(f"c-{c.pk}", str(c)) for c in Classe.objects.all()]),
            ]
        self.fields["destinataires"].choices = choix

    def clean_date_fin(self):
        date_fin = self.cleaned_data["date_fin"]
        if date_fin and date_fin < timezone.localdate():
            raise forms.ValidationError("La date de fin d'affichage est déjà passée.")
        return date_fin

    def clean(self):
        donnees = super().clean()
        cible = donnees.get("destinataires", "")
        self.instance.filiere = self.instance.classe = None
        if cible.startswith("f-"):
            self.instance.filiere = Filiere.objects.get(pk=cible[2:])
        elif cible.startswith("c-"):
            self.instance.classe = Classe.objects.get(pk=cible[2:])
        return donnees
