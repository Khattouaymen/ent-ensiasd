from django import forms

from config.formulaires import FormulaireBootstrap, accepter_extensions
from config.validateurs import EXTENSIONS_DOCUMENT, VALIDATEURS_DOCUMENT

from .models import DemandeDocument

STATUTS_EN_COURS = [DemandeDocument.Statut.EN_ATTENTE, DemandeDocument.Statut.ACCEPTEE]


class DemandeForm(FormulaireBootstrap, forms.ModelForm):
    class Meta:
        model = DemandeDocument
        fields = ["type_document", "motif"]
        widgets = {"motif": forms.Textarea(attrs={"rows": 3, "placeholder": "Ex. : dossier de bourse, stage…"})}

    def __init__(self, *args, etudiant, **kwargs):
        super().__init__(*args, **kwargs)
        self.etudiant = etudiant

    def clean_type_document(self):
        type_document = self.cleaned_data["type_document"]
        if self.etudiant.demandes_documents.filter(type_document=type_document, statut__in=STATUTS_EN_COURS).exists():
            raise forms.ValidationError("Vous avez déjà une demande en cours pour ce document.")
        return type_document


class TraitementDemandeForm(FormulaireBootstrap, forms.Form):
    statut = forms.ChoiceField(label="Nouveau statut")
    commentaire = forms.CharField(label="Commentaire pour l'étudiant", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    document = forms.FileField(
        label="Document délivré (PDF)",
        required=False,
        validators=VALIDATEURS_DOCUMENT,
        help_text="Facultatif : si aucun fichier n'est joint, l'étudiant viendra retirer le document au guichet.",
    )

    def __init__(self, *args, demande, **kwargs):
        super().__init__(*args, **kwargs)
        possibles = demande.TRANSITIONS[demande.statut]
        self.fields["statut"].choices = [(s.value, s.label) for s in DemandeDocument.Statut if s in possibles]
        accepter_extensions(self.fields["document"], EXTENSIONS_DOCUMENT)
        if demande.type_document == DemandeDocument.TypeDocument.ATTESTATION_SCOLARITE:
            self.fields["document"].help_text = (
                "Facultatif : sans fichier joint, l'attestation de scolarité est générée automatiquement en PDF."
            )

    def clean(self):
        donnees = super().clean()
        if donnees.get("document") and donnees.get("statut") != DemandeDocument.Statut.PRETE:
            self.add_error("document", "Le document ne peut être joint que lorsque la demande passe à « Prête ».")
        return donnees


class AjoutDocumentForm(FormulaireBootstrap, forms.Form):
    """Ajout (ou remplacement) du fichier d'une demande déjà « Prête »."""

    document = forms.FileField(label="Document délivré (PDF)", validators=VALIDATEURS_DOCUMENT)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accepter_extensions(self.fields["document"], EXTENSIONS_DOCUMENT)
