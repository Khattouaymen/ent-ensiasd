from django import forms
from django.conf import settings

from config.formulaires import FormulaireBootstrap, accepter_extensions
from config.validateurs import EXTENSIONS_JUSTIFICATIF

from .models import Justification


class JustificationForm(FormulaireBootstrap, forms.ModelForm):
    class Meta:
        model = Justification
        fields = ["motif", "piece_jointe"]
        widgets = {"motif": forms.Textarea(attrs={"rows": 3, "placeholder": "Ex. : rendez-vous médical, convocation…"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accepter_extensions(self.fields["piece_jointe"], EXTENSIONS_JUSTIFICATIF)
        self.fields["piece_jointe"].help_text = f"PDF ou image (JPG, PNG), {settings.TAILLE_MAX_JUSTIFICATIF_MO} Mo maximum."
