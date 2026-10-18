"""Suivi des absences par l'enseignant, dans chacune de ses matières."""

from datetime import time, timedelta

from django.test import TestCase, override_settings

from config.donnees_test import MARDI, creer_etablissement
from emplois.models import Seance
from structure.models import Enseignement, Matiere

from .models import Absence


@override_settings(SEUILS_ABSENCE={"AVERTISSEMENT": 10, "CRITIQUE": 25})
class SuiviEnseignantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()
        cls.d.bd.volume_horaire = 16  # une absence de 2 h = 12,5 % ; deux = 25 %
        cls.d.bd.save()
        cls.affectation = Enseignement.objects.get(enseignant=cls.d.prof)

    def absence(self, etudiant, semaine=0, seance=None, **champs):
        seance = seance or self.d.seance
        return Absence.objects.create(etudiant=etudiant, seance=seance, date=MARDI + timedelta(weeks=semaine), **champs)

    def suivi(self, compte=None, **parametres):
        self.client.force_login(compte or self.d.prof)
        return self.client.get("/absences/suivi/", parametres)

    def test_les_etudiants_en_alerte_en_tete(self):
        self.absence(self.d.etu2)
        self.absence(self.d.etu2, semaine=1)
        reponse = self.suivi()
        lignes = reponse.context["lignes"]
        self.assertEqual([l["etudiant"] for l in lignes], [self.d.etu2, self.d.etu1])
        self.assertEqual((lignes[0]["total"], lignes[0]["taux"], lignes[0]["alerte"]), (4, 25, "CRITIQUE"))
        self.assertEqual((reponse.context["nb_alertes"], reponse.context["nb_critiques"]), (1, 1))
        self.assertContains(reponse, "Seuil critique")

    def test_absences_justifiees_et_retards(self):
        self.absence(self.d.etu1, statut=Absence.Statut.JUSTIFIEE)
        self.absence(self.d.etu1, semaine=1, nature=Absence.Nature.RETARD)
        ligne = next(l for l in self.suivi().context["lignes"] if l["etudiant"] == self.d.etu1)
        self.assertEqual((ligne["total"], ligne["non_justifiees"], ligne["retards"]), (2, 0, 1))
        self.assertEqual((ligne["alerte"], ligne["dates"]), (None, [(MARDI, True)]))

    def test_seule_la_matiere_choisie_compte(self):
        reseaux = Matiere.objects.create(code="RES", nom="Réseaux", filiere=self.d.mgsi, niveau=self.d.a2, volume_horaire=8)
        Enseignement.objects.create(enseignant=self.d.autre_prof, matiere=reseaux, classe=self.d.classe)
        seance_reseaux = Seance.objects.create(
            classe=self.d.classe, matiere=reseaux, enseignant=self.d.autre_prof, salle=self.d.salle,
            jour=Seance.Jour.JEUDI, heure_debut=time(14), heure_fin=time(16),
        )
        self.absence(self.d.etu1, seance=seance_reseaux)
        self.assertEqual(sum(l["total"] for l in self.suivi().context["lignes"]), 0)
        self.assertEqual(Absence.etudiants_en_alerte(self.d.prof), 0)
        self.assertEqual(Absence.etudiants_en_alerte(self.d.autre_prof), 1)  # 2 h sur 8 h = 25 %

    def test_filtre_des_etudiants_en_alerte(self):
        self.absence(self.d.etu2)
        lignes = self.suivi(filtre="alertes").context["lignes"]
        self.assertEqual([(l["etudiant"], l["alerte"]) for l in lignes], [(self.d.etu2, "AVERTISSEMENT")])

    def test_les_etudiants_d_une_autre_classe_n_apparaissent_pas(self):
        etudiants = {l["etudiant"] for l in self.suivi().context["lignes"]}
        self.assertEqual(etudiants, {self.d.etu1, self.d.etu2})

    def test_acces_limite_a_ses_affectations(self):
        self.assertEqual(self.suivi(self.d.autre_prof, affectation=self.affectation.pk).status_code, 404)
        self.assertContains(self.suivi(self.d.autre_prof), "aucune matière")
        for compte in (self.d.etu1, self.d.scolarite):
            with self.subTest(compte=compte.username):
                self.assertEqual(self.suivi(compte).status_code, 403)

    def test_indicateur_du_tableau_de_bord(self):
        self.absence(self.d.etu1)
        self.client.force_login(self.d.prof)
        stats = dict((libelle, valeur) for libelle, valeur, *_ in self.client.get("/").context["stats"])
        self.assertEqual(stats["Étudiants en alerte"], 1)
