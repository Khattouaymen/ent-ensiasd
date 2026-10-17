"""Appel enregistré d'un bloc et en requêtes groupées, doubles envois et traitements simultanés."""

import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from comptes.models import Utilisateur
from config.donnees_test import MARDI, creer_etablissement, fichier_pdf

from .models import Absence, AlerteAbsence, Justification

MEDIA_TEST = tempfile.mkdtemp()


def tearDownModule():
    shutil.rmtree(MEDIA_TEST, ignore_errors=True)


def appel(choix, jour=MARDI):
    return {"date": jour.isoformat(), **{f"etudiant_{e.pk}": valeur for e, valeur in choix.items()}}


@override_settings(MEDIA_ROOT=MEDIA_TEST, SEUILS_ABSENCE={"AVERTISSEMENT": 10, "CRITIQUE": 25})
class AppelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()
        cls.d.bd.volume_horaire = 16  # une absence de 2 h = 12,5 % : avertissement
        cls.d.bd.save()

    def setUp(self):
        self.client.force_login(self.d.prof)
        self.url = f"/absences/appel/{self.d.seance.pk}/"

    def ajouter_etudiants(self, nombre):
        return [
            Utilisateur.objects.create(username=f"promo{i}", last_name=f"Promo{i:02}", classe=self.d.classe, groupe=self.d.g1)
            for i in range(nombre)
        ]

    def requetes_appel(self, etudiants):
        with CaptureQueriesContext(connection) as requetes:
            self.client.post(self.url, appel({e: "absent" for e in etudiants}))
        return len(requetes)

    def test_le_nombre_de_requetes_ne_depend_pas_de_l_effectif(self):
        petite = self.requetes_appel([self.d.etu1, self.d.etu2])
        Absence.objects.all().delete()
        grande = self.requetes_appel([self.d.etu1, self.d.etu2, *self.ajouter_etudiants(15)])
        self.assertEqual(Absence.objects.count(), 17)
        self.assertEqual(AlerteAbsence.objects.count(), 17)
        self.assertEqual(petite, grande)

    def test_une_erreur_n_enregistre_pas_l_appel_a_moitie(self):
        with mock.patch.object(AlerteAbsence, "verifier_apres_appel", side_effect=RuntimeError("panne")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, appel({self.d.etu1: "absent", self.d.etu2: "retard"}))
        self.assertFalse(Absence.objects.exists())

    def test_double_envoi_sans_erreur(self):
        self.client.post(self.url, appel({self.d.etu1: "absent"}))
        # Second envoi qui a lu les absences avant que le premier soit enregistré
        with mock.patch("absences.views.absences_existantes", return_value={}):
            reponse = self.client.post(self.url, appel({self.d.etu1: "absent"}))
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(Absence.objects.count(), 1)

    def test_passer_de_retard_a_absent_compte_la_duree_de_la_seance(self):
        self.client.post(self.url, appel({self.d.etu1: "retard"}))
        self.client.post(self.url, appel({self.d.etu1: "absent"}))
        absence = Absence.objects.get()
        self.assertEqual((absence.nature, absence.duree_heures), (Absence.Nature.ABSENCE, 2))
        self.assertTrue(AlerteAbsence.objects.filter(etudiant=self.d.etu1).exists())

    def test_marquer_present_supprime_l_absence(self):
        self.client.post(self.url, appel({self.d.etu1: "absent", self.d.etu2: "absent"}))
        self.client.post(self.url, appel({self.d.etu1: "present", self.d.etu2: "absent"}))
        self.assertEqual(list(Absence.objects.values_list("etudiant", flat=True)), [self.d.etu2.pk])


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class TraitementsSimultanesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()

    def setUp(self):
        self.absence = Absence.objects.create(etudiant=self.d.etu1, seance=self.d.seance, date=MARDI)

    def creer_justification(self):
        j = Justification(absence=self.absence, motif="Malade")
        j.piece_jointe.save("certificat.pdf", ContentFile(b"%PDF-1.4"), save=False)
        j.save()
        return j

    def test_double_envoi_d_une_justification(self):
        self.creer_justification()
        self.client.force_login(self.d.etu1)
        # Second envoi qui a passé la vérification avant que le premier soit enregistré
        with mock.patch.object(Absence, "peut_etre_justifiee", new_callable=mock.PropertyMock, return_value=True):
            reponse = self.client.post(
                f"/absences/{self.absence.pk}/justifier/", {"motif": "Encore", "piece_jointe": fichier_pdf("doublon.pdf")}
            )
        self.assertRedirects(reponse, "/absences/mes-absences/")
        self.assertEqual(self.absence.justifications.count(), 1)
        self.assertFalse(list(Path(MEDIA_TEST).rglob("doublon*.pdf")))  # pas de fichier orphelin

    def test_deux_agents_traitent_la_meme_justification(self):
        j = self.creer_justification()
        vue_par_a, vue_par_b = Justification.objects.get(pk=j.pk), Justification.objects.get(pk=j.pk)
        vue_par_a.traiter(True, self.d.scolarite)
        with self.assertRaisesMessage(ValidationError, "déjà été traitée"):
            vue_par_b.traiter(False, self.d.admin, "Refus")
        j.refresh_from_db()
        self.absence.refresh_from_db()
        self.assertEqual((j.statut, j.traitee_par), (Justification.Statut.ACCEPTEE, self.d.scolarite))
        self.assertEqual(self.absence.statut, Absence.Statut.JUSTIFIEE)
        self.assertEqual(self.d.etu1.notifications.count(), 1)
