"""Relevé d'absences en PDF : contenu, pages multiples et droits d'accès."""

import re
from datetime import timedelta
from unittest import mock

from django.test import TestCase

from config.donnees_test import MARDI, creer_etablissement

from .models import Absence


def texte_pdf(reponse):
    """Contenu brut du PDF ; la compression est désactivée par les tests pour pouvoir y chercher du texte."""
    return reponse.content.decode("latin-1")


@mock.patch("reportlab.rl_config.pageCompression", 0)
class ReleveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()
        cls.d.bd.volume_horaire = 16
        cls.d.bd.save()

    def absence(self, etudiant, semaine=0, **champs):
        return Absence.objects.create(etudiant=etudiant, seance=self.d.seance, date=MARDI + timedelta(weeks=semaine), **champs)

    def test_l_etudiant_obtient_son_releve(self):
        self.absence(self.d.etu1)
        self.absence(self.d.etu1, semaine=1, nature=Absence.Nature.RETARD)
        self.client.force_login(self.d.etu1)
        reponse = self.client.get("/absences/mes-absences/releve.pdf")
        self.assertEqual(reponse["Content-Type"], "application/pdf")
        self.assertIn("releve_absences_etu1_", reponse["Content-Disposition"])
        contenu = texte_pdf(reponse)
        self.assertTrue(contenu.startswith("%PDF"))
        self.assertIn("AMRANI", contenu)
        self.assertIn("06/10/2026", contenu)
        self.assertIn("Avertissement", contenu)  # 2 h sur 16 h = 12,5 %
        self.assertIn("Retard", contenu)

    def test_releve_sans_absence(self):
        self.client.force_login(self.d.etu2)
        self.assertIn("Aucune absence", texte_pdf(self.client.get("/absences/mes-absences/releve.pdf")))

    def test_un_long_releve_tient_sur_plusieurs_pages(self):
        for semaine in range(70):
            self.absence(self.d.etu1, semaine=semaine)
        self.client.force_login(self.d.etu1)
        contenu = texte_pdf(self.client.get("/absences/mes-absences/releve.pdf"))
        self.assertGreater(len(re.findall(r"/Type /Page\b(?!s)", contenu)), 1)
        self.assertIn("Page 2", contenu)

    def test_la_scolarite_et_l_administrateur_obtiennent_le_releve_d_un_etudiant(self):
        self.absence(self.d.etu2)
        for compte in (self.d.scolarite, self.d.admin):
            self.client.force_login(compte)
            with self.subTest(compte=compte.username):
                self.assertIn("BENNANI", texte_pdf(self.client.get(f"/absences/etudiants/{self.d.etu2.pk}/releve.pdf")))
        self.assertEqual(self.client.get(f"/absences/etudiants/{self.d.prof.pk}/releve.pdf").status_code, 404)

    def test_acces_refuse_aux_autres(self):
        url = f"/absences/etudiants/{self.d.etu2.pk}/releve.pdf"
        for compte in (self.d.etu1, self.d.prof):
            self.client.force_login(compte)
            with self.subTest(compte=compte.username):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.d.prof)
        self.assertEqual(self.client.get("/absences/mes-absences/releve.pdf").status_code, 403)

    def test_liens_vers_les_releves(self):
        self.client.force_login(self.d.etu1)
        self.assertContains(self.client.get("/absences/mes-absences/"), "/absences/mes-absences/releve.pdf")
        self.client.force_login(self.d.scolarite)
        reponse = self.client.get(f"/absences/classes/?classe={self.d.classe.pk}")
        self.assertContains(reponse, f"/absences/etudiants/{self.d.etu1.pk}/releve.pdf")
        self.assertContains(reponse, f"/absences/etudiants/{self.d.etu2.pk}/releve.pdf")
