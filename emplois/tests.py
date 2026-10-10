from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase

from comptes.models import Utilisateur
from structure.models import Classe, Enseignement, Filiere, Groupe, Matiere, Niveau, Salle

from .models import Seance


class DonneesEmploi:
    """Une classe à deux groupes, avec une séance le lundi de 8h30 à 10h30 en salle S1."""

    @classmethod
    def setUpTestData(cls):
        filiere = Filiere.objects.create(code="MGSI", nom="MGSI")
        niveau = Niveau.objects.create(nom="2ème année", ordre=2)
        cls.classe = Classe.objects.create(filiere=filiere, niveau=niveau, annee_universitaire="2026/2027")
        cls.autre_classe = Classe.objects.create(filiere=filiere, niveau=niveau, annee_universitaire="2027/2028")
        cls.g1 = Groupe.objects.create(classe=cls.classe, nom="G1")
        cls.g2 = Groupe.objects.create(classe=cls.classe, nom="G2")
        cls.matiere = Matiere.objects.create(code="BD", nom="Bases de données", filiere=filiere, niveau=niveau)
        cls.prof1 = Utilisateur.objects.create(username="p1", role=Utilisateur.Role.ENSEIGNANT)
        cls.prof2 = Utilisateur.objects.create(username="p2", role=Utilisateur.Role.ENSEIGNANT)
        cls.salle1 = Salle.objects.create(nom="S1")
        cls.salle2 = Salle.objects.create(nom="S2")
        for prof in (cls.prof1, cls.prof2):
            for classe in (cls.classe, cls.autre_classe):
                Enseignement.objects.create(enseignant=prof, matiere=cls.matiere, classe=classe)
        Seance.objects.create(
            classe=cls.classe, matiere=cls.matiere, enseignant=cls.prof1, salle=cls.salle1,
            jour=Seance.Jour.LUNDI, heure_debut=time(8, 30), heure_fin=time(10, 30),
        )


class DetectionConflitsTests(DonneesEmploi, TestCase):
    """BF14 : détection des conflits de salle, d'enseignant et de classe."""

    def seance(self, **kwargs):
        valeurs = dict(
            classe=self.autre_classe, matiere=self.matiere, enseignant=self.prof2, salle=self.salle2,
            jour=Seance.Jour.LUNDI, heure_debut=time(9, 30), heure_fin=time(11, 30),
        )
        valeurs.update(kwargs)
        return Seance(**valeurs)

    def test_sans_conflit(self):
        self.seance().full_clean()

    def test_conflit_de_salle(self):
        with self.assertRaisesMessage(ValidationError, "La salle S1 est déjà occupée"):
            self.seance(salle=self.salle1).full_clean()

    def test_conflit_enseignant(self):
        with self.assertRaisesMessage(ValidationError, "a déjà une séance"):
            self.seance(enseignant=self.prof1).full_clean()

    def test_conflit_de_classe(self):
        with self.assertRaisesMessage(ValidationError, "La classe ou le groupe"):
            self.seance(classe=self.classe).full_clean()

    def test_groupe_en_conflit_avec_seance_de_toute_la_classe(self):
        with self.assertRaises(ValidationError):
            self.seance(classe=self.classe, groupe=self.g1).full_clean()

    def test_deux_groupes_differents_en_parallele(self):
        Seance.objects.create(
            classe=self.classe, groupe=self.g1, matiere=self.matiere, enseignant=self.prof1, salle=self.salle1,
            jour=Seance.Jour.MARDI, heure_debut=time(8, 30), heure_fin=time(10, 30),
        )
        self.seance(classe=self.classe, groupe=self.g2, jour=Seance.Jour.MARDI).full_clean()

    def test_seances_consecutives_sans_conflit(self):
        self.seance(salle=self.salle1, enseignant=self.prof1, classe=self.classe,
                    heure_debut=time(10, 30), heure_fin=time(12, 30)).full_clean()

    def test_autre_jour_sans_conflit(self):
        self.seance(salle=self.salle1, jour=Seance.Jour.MARDI).full_clean()

    def test_modifier_une_seance_ne_la_met_pas_en_conflit_avec_elle_meme(self):
        existante = Seance.objects.get()
        existante.heure_fin = time(11, 0)
        existante.full_clean()

    def test_heure_de_fin_avant_debut(self):
        with self.assertRaises(ValidationError):
            self.seance(heure_debut=time(12, 0), heure_fin=time(10, 0)).full_clean()

    def test_groupe_d_une_autre_classe(self):
        with self.assertRaisesMessage(ValidationError, "n'appartient pas à la classe"):
            self.seance(groupe=self.g1).full_clean()


class EmploiDuTempsVuesTests(DonneesEmploi, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.etudiant_g1 = Utilisateur.objects.create(username="e1", classe=cls.classe, groupe=cls.g1)
        Seance.objects.create(
            classe=cls.classe, groupe=cls.g2, matiere=cls.matiere, enseignant=cls.prof2, salle=cls.salle2,
            jour=Seance.Jour.MARDI, heure_debut=time(8, 30), heure_fin=time(10, 30),
        )

    def test_etudiant_voit_seances_de_sa_classe_et_de_son_groupe_seulement(self):
        self.client.force_login(self.etudiant_g1)
        reponse = self.client.get("/emploi-du-temps/")
        seances = [s for jour in reponse.context["jours"] for s, _ in jour["seances"]]
        self.assertEqual(len(seances), 1)
        self.assertIsNone(seances[0].groupe)

    def test_enseignant_voit_ses_seances(self):
        self.client.force_login(self.prof2)
        reponse = self.client.get("/emploi-du-temps/")
        seances = [s for jour in reponse.context["jours"] for s, _ in jour["seances"]]
        self.assertEqual([s.enseignant for s in seances], [self.prof2])

    def test_emploi_du_temps_des_classes_interdit_aux_etudiants(self):
        self.client.force_login(self.etudiant_g1)
        self.assertEqual(self.client.get("/emploi-du-temps/classes/").status_code, 403)
