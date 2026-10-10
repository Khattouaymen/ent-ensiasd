"""Validation des fichiers déposés : extension, contenu réel et taille (BNF09)."""

import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.deconstruct import deconstructible

EXTENSIONS_JUSTIFICATIF = ["pdf", "jpg", "jpeg", "png"]
EXTENSIONS_RESSOURCE = ["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "zip", "txt", "jpg", "jpeg", "png"]
EXTENSIONS_DOCUMENT = ["pdf"]

# Premiers octets (« signature ») attendus pour chaque type de fichier
_ZIP = [b"PK\x03\x04", b"PK\x05\x06"]  # aussi utilisé par les formats Office récents
_OFFICE_ANCIEN = [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"]
SIGNATURES = {
    "pdf": [b"%PDF"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "zip": _ZIP,
    "docx": _ZIP,
    "pptx": _ZIP,
    "xlsx": _ZIP,
    "doc": _OFFICE_ANCIEN,
    "ppt": _OFFICE_ANCIEN,
    "xls": _OFFICE_ANCIEN,
}


@deconstructible
class ContenuConforme:
    """Vérifie que le contenu du fichier correspond à son extension.

    Empêche par exemple de déposer un exécutable renommé en « certificat.pdf ».
    """

    def __call__(self, fichier):
        if getattr(fichier, "_committed", False):
            return  # fichier déjà enregistré : il a été contrôlé lors de son dépôt
        extension = os.path.splitext(fichier.name)[1].lower().lstrip(".")
        fichier.seek(0)
        debut = fichier.read(2048)
        fichier.seek(0)

        if extension == "txt":
            conforme = b"\x00" not in debut
        else:
            signatures = SIGNATURES.get(extension)
            conforme = signatures is None or any(debut.startswith(s) for s in signatures)
        if not conforme:
            raise ValidationError(f"Le contenu du fichier ne correspond pas à un fichier .{extension}.")

    def __eq__(self, autre):
        return isinstance(autre, ContenuConforme)


@deconstructible
class TailleMaximale:
    """Refuse les fichiers plus gros que la limite (en Mo) lue dans le paramètre Django indiqué."""

    def __init__(self, parametre):
        self.parametre = parametre

    def __call__(self, fichier):
        limite_mo = getattr(settings, self.parametre)
        if fichier.size > limite_mo * 1024 * 1024:
            raise ValidationError(f"Le fichier dépasse la taille maximale autorisée ({limite_mo} Mo).")

    def __eq__(self, autre):
        return isinstance(autre, TailleMaximale) and self.parametre == autre.parametre


VALIDATEURS_JUSTIFICATIF = [
    FileExtensionValidator(EXTENSIONS_JUSTIFICATIF),
    ContenuConforme(),
    TailleMaximale("TAILLE_MAX_JUSTIFICATIF_MO"),
]
VALIDATEURS_RESSOURCE = [
    FileExtensionValidator(EXTENSIONS_RESSOURCE),
    ContenuConforme(),
    TailleMaximale("TAILLE_MAX_RESSOURCE_MO"),
]
VALIDATEURS_DOCUMENT = [
    FileExtensionValidator(EXTENSIONS_DOCUMENT),
    ContenuConforme(),
    TailleMaximale("TAILLE_MAX_RESSOURCE_MO"),
]
