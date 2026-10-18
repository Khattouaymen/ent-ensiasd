"""Import en masse des étudiants d'une classe à partir d'un fichier CSV.

Colonnes attendues (la première ligne contient les en-têtes, l'ordre est libre) :
    nom ; prenom ; cne ; email (facultatif) ; groupe (facultatif)
Le séparateur peut être « ; » (Excel en français) ou « , ».
"""

import csv
import io
import secrets
import string
import unicodedata

from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from .models import Utilisateur

COLONNES_OBLIGATOIRES = ["nom", "prenom", "cne"]
COLONNES_FACULTATIVES = ["email", "groupe"]

# Les mots de passe provisoires sont longs et aléatoires, et doivent être changés à la
# première connexion : un hachage plus léger (Django le renforce automatiquement à la
# connexion) permet d'importer une promotion entière en quelques secondes.
ITERATIONS_MOT_DE_PASSE_PROVISOIRE = 60_000


def _normaliser(entete):
    """« Prénom » → « prenom », « E-mail » → « email »."""
    sans_accents = unicodedata.normalize("NFKD", entete).encode("ascii", "ignore").decode()
    return sans_accents.strip().lower().replace("-", "").replace(" ", "").replace("_", "")


def _lire_texte(fichier):
    contenu = fichier.read()
    for encodage in ("utf-8-sig", "cp1252"):
        try:
            return contenu.decode(encodage)
        except UnicodeDecodeError:
            continue
    raise ValidationError("Encodage du fichier non reconnu : enregistrez-le en « CSV UTF-8 ».")


def mot_de_passe_provisoire(longueur=10):
    # Sans caractères ambigus (0/O, 1/l/I) pour faciliter la saisie.
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    return "".join(secrets.choice(alphabet) for _ in range(longueur))


class ResultatImport:
    def __init__(self):
        self.erreurs = []  # (numéro de ligne, message)
        self.comptes = []  # (utilisateur, mot de passe provisoire)


def analyser(fichier, classe):
    """Lit et vérifie le fichier sans rien enregistrer. Renvoie (lignes valides, erreurs)."""
    texte = _lire_texte(fichier)
    separateur = ";" if texte.split("\n", 1)[0].count(";") >= texte.split("\n", 1)[0].count(",") else ","
    lecteur = csv.reader(io.StringIO(texte), delimiter=separateur)
    try:
        entetes = [_normaliser(e) for e in next(lecteur)]
    except StopIteration:
        raise ValidationError("Le fichier est vide.") from None
    manquantes = [c for c in COLONNES_OBLIGATOIRES if c not in entetes]
    if manquantes:
        raise ValidationError(f"Colonne(s) manquante(s) : {', '.join(manquantes)}. Colonnes trouvées : {', '.join(entetes)}.")

    groupes = {g.nom.lower(): g for g in classe.groupes.all()}
    cne_existants = set(Utilisateur.objects.exclude(cne="").values_list("cne", flat=True))
    identifiants_existants = set(Utilisateur.objects.values_list("username", flat=True))
    vus = set()
    lignes, erreurs = [], []

    for numero, valeurs in enumerate(lecteur, start=2):
        if not any(v.strip() for v in valeurs):
            continue  # ligne vide
        ligne = {e: (valeurs[i].strip() if i < len(valeurs) else "") for i, e in enumerate(entetes)}
        nom, prenom, cne = ligne["nom"], ligne["prenom"], ligne["cne"].upper()
        email = ligne.get("email", "")
        if not (nom and prenom and cne):
            erreurs.append((numero, "Nom, prénom et CNE sont obligatoires."))
            continue
        if cne in cne_existants or cne.lower() in identifiants_existants:
            erreurs.append((numero, f"Le CNE {cne} correspond déjà à un compte."))
            continue
        if cne in vus:
            erreurs.append((numero, f"Le CNE {cne} apparaît plusieurs fois dans le fichier."))
            continue
        if email:
            try:
                validate_email(email)
            except ValidationError:
                erreurs.append((numero, f"Adresse e-mail invalide : {email}."))
                continue
        groupe = None
        if ligne.get("groupe"):
            groupe = groupes.get(ligne["groupe"].lower())
            if groupe is None:
                erreurs.append((numero, f"Le groupe « {ligne['groupe']} » n'existe pas dans la classe {classe}."))
                continue
        vus.add(cne)
        lignes.append({"nom": nom, "prenom": prenom, "cne": cne, "email": email, "groupe": groupe})
    if not lignes and not erreurs:
        raise ValidationError("Le fichier ne contient aucun étudiant.")
    return lignes, erreurs


@transaction.atomic
def importer(fichier, classe):
    """Crée les comptes si le fichier ne contient aucune erreur (tout ou rien)."""
    resultat = ResultatImport()
    lignes, resultat.erreurs = analyser(fichier, classe)
    if resultat.erreurs:
        return resultat

    hacheur = PBKDF2PasswordHasher()
    nouveaux = []
    for ligne in lignes:
        mot_de_passe = mot_de_passe_provisoire()
        etudiant = Utilisateur(
            username=ligne["cne"].lower(),
            last_name=ligne["nom"],
            first_name=ligne["prenom"],
            cne=ligne["cne"],
            email=ligne["email"],
            role=Utilisateur.Role.ETUDIANT,
            classe=classe,
            groupe=ligne["groupe"],
            doit_changer_mot_de_passe=True,
            password=hacheur.encode(mot_de_passe, hacheur.salt(), iterations=ITERATIONS_MOT_DE_PASSE_PROVISOIRE),
        )
        nouveaux.append(etudiant)
        resultat.comptes.append((etudiant, mot_de_passe))
    Utilisateur.objects.bulk_create(nouveaux)
    return resultat
