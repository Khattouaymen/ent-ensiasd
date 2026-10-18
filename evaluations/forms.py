from django import forms
from django.utils import timezone

from config.formulaires import FormulaireBootstrap, accepter_extensions
from config.validateurs import EXTENSIONS_RESSOURCE
from structure.models import Enseignement, Groupe, Matiere

from .models import Devoir, Examen, Rendu

FORMAT_DATE_HEURE = "%Y-%m-%dT%H:%M"


class ChoixAffectation(forms.ModelChoiceField):
    def label_from_instance(self, enseignement):
        return f"{enseignement.matiere} – {enseignement.classe}"


class FormulairePourUneClasse(FormulaireBootstrap, forms.ModelForm):
    """Un enseignant choisit l'une de ses affectations (matière et classe) ; la scolarité et
    l'administration choisissent librement la matière et la classe (leur cohérence est vérifiée)."""

    def __init__(self, *args, auteur, **kwargs):
        super().__init__(*args, **kwargs)
        self.par_affectation = auteur.est_enseignant
        if self.par_affectation:
            affectations = Enseignement.objects.filter(enseignant=auteur).select_related(
                "matiere", "classe__filiere", "classe__niveau"
            )
            del self.fields["matiere"], self.fields["classe"]
            self.fields["affectation"] = ChoixAffectation(affectations, label="Matière et classe")
            self.order_fields(["affectation"])
            self.fields["groupe"].queryset = Groupe.objects.filter(classe__in=affectations.values("classe"))
        else:
            self.fields["matiere"].queryset = Matiere.objects.select_related("filiere", "niveau")
            self.fields["matiere"].label_from_instance = lambda m: f"{m.nom} ({m.filiere.code} – {m.niveau})"

    def clean(self):
        donnees = super().clean()
        if self.par_affectation and donnees.get("affectation"):
            self.instance.matiere = donnees["affectation"].matiere
            self.instance.classe = donnees["affectation"].classe
        return donnees


class ExamenForm(FormulairePourUneClasse):
    class Meta:
        model = Examen
        fields = ["matiere", "classe", "groupe", "type", "titre", "date", "heure_debut", "heure_fin", "salle", "consignes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "heure_debut": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "heure_fin": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "consignes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise forms.ValidationError("Cette date est déjà passée.")
        return date


class DevoirForm(FormulairePourUneClasse):
    class Meta:
        model = Devoir
        fields = ["matiere", "classe", "groupe", "titre", "consignes", "fichier_consignes", "date_limite", "accepte_retard"]
        widgets = {
            "consignes": forms.Textarea(attrs={"rows": 5}),
            "date_limite": forms.DateTimeInput(attrs={"type": "datetime-local"}, format=FORMAT_DATE_HEURE),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_limite"].input_formats = [FORMAT_DATE_HEURE]
        accepter_extensions(self.fields["fichier_consignes"], EXTENSIONS_RESSOURCE)

    def clean_date_limite(self):
        date_limite = self.cleaned_data["date_limite"]
        if date_limite <= timezone.now():
            raise forms.ValidationError("La date limite doit être dans le futur.")
        return date_limite


class RenduForm(FormulaireBootstrap, forms.ModelForm):
    class Meta:
        model = Rendu
        fields = ["fichier", "commentaire"]
        widgets = {"commentaire": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accepter_extensions(self.fields["fichier"], EXTENSIONS_RESSOURCE)
        self.fields["fichier"].help_text = "Formats acceptés : " + ", ".join(EXTENSIONS_RESSOURCE) + "."
