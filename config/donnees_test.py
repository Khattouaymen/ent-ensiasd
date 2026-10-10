"""Jeu de données minimal partagé par les tests des vues."""

from datetime import date, time
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile

from comptes.models import Utilisateur
from emplois.models import Seance
from structure.models import Classe, Enseignement, Filiere, Groupe, Matiere, Niveau, Salle

# 6 octobre 2026 : un mardi (passé par rapport à la date des tests)
MARDI = date(2026, 10, 6)


def fichier_pdf(nom="document.pdf"):
    return SimpleUploadedFile(nom, b"%PDF-1.4 test", content_type="application/pdf")


def creer_etablissement():
    """Deux filières ; la classe MGSI 2A (groupes G1/G2) a une séance de BD le mardi."""
    d = SimpleNamespace()
    d.mgsi = Filiere.objects.create(code="MGSI", nom="MGSI")
    d.ia = Filiere.objects.create(code="IA", nom="IA")
    d.a2 = Niveau.objects.create(nom="2ème année", ordre=2)
    d.classe = Classe.objects.create(filiere=d.mgsi, niveau=d.a2, annee_universitaire="2026/2027")
    d.classe_ia = Classe.objects.create(filiere=d.ia, niveau=d.a2, annee_universitaire="2026/2027")
    d.g1 = Groupe.objects.create(classe=d.classe, nom="G1")
    d.g2 = Groupe.objects.create(classe=d.classe, nom="G2")
    d.bd = Matiere.objects.create(code="BD", nom="Bases de données", filiere=d.mgsi, niveau=d.a2)
    d.ml = Matiere.objects.create(code="ML", nom="Machine learning", filiere=d.ia, niveau=d.a2)
    d.salle = Salle.objects.create(nom="S1")

    d.prof = Utilisateur.objects.create(username="prof", role=Utilisateur.Role.ENSEIGNANT, last_name="Prof")
    d.autre_prof = Utilisateur.objects.create(username="prof2", role=Utilisateur.Role.ENSEIGNANT)
    d.scolarite = Utilisateur.objects.create(username="sco", role=Utilisateur.Role.SCOLARITE)
    d.admin = Utilisateur.objects.create(username="adm", role=Utilisateur.Role.ADMIN)
    d.etu1 = Utilisateur.objects.create(username="etu1", last_name="Amrani", classe=d.classe, groupe=d.g1)
    d.etu2 = Utilisateur.objects.create(username="etu2", last_name="Bennani", classe=d.classe, groupe=d.g2)
    d.etu_ia = Utilisateur.objects.create(username="etu_ia", classe=d.classe_ia)

    Enseignement.objects.create(enseignant=d.prof, matiere=d.bd, classe=d.classe)
    d.seance = Seance.objects.create(
        classe=d.classe, matiere=d.bd, enseignant=d.prof, salle=d.salle,
        jour=Seance.Jour.MARDI, heure_debut=time(8, 30), heure_fin=time(10, 30),
    )
    return d
