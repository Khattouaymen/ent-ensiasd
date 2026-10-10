"""Retards, nouvelle justification après refus, seuils d'alerte et calendrier dans l'appel."""

import shutil
import tempfile
from datetime import date, time

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from config.donnees_test import MARDI, creer_etablissement, fichier_pdf
from emplois.models import AnnulationSeance, JourNonTravaille, Seance

from .models import Absence, AlerteAbsence, Justification

MEDIA_TEST = tempfile.mkdtemp()


def appel(choix, jour=MARDI):
    return {"date": jour.isoformat(), **{f"etudiant_{e.pk}": valeur for e, valeur in choix.items()}}


@override_settings(MEDIA_ROOT=MEDIA_TEST, SEUILS_ABSENCE={"AVERTISSEMENT": 10, "CRITIQUE": 25})
class NouveautesAbsencesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()
        cls.d.bd.volume_horaire = 16  # une absence de 2 h = 12,5 % ; deux = 25 %
        cls.d.bd.save()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def url_appel(self, seance=None):
        return f"/absences/appel/{(seance or self.d.seance).pk}/"

    # --- Retards ---------------------------------------------------------------------------

    def test_un_retard_est_enregistre_sans_heures_d_absence(self):
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(), appel({self.d.etu1: "retard", self.d.etu2: "absent"}))
        retard = Absence.objects.get(etudiant=self.d.etu1)
        self.assertEqual(retard.nature, Absence.Nature.RETARD)
        self.assertEqual(retard.duree_heures, 0)
        ligne = Absence.heures_par_matiere(self.d.etu1)[0]
        self.assertEqual((ligne["total"], ligne["retards"]), (0, 1))
        self.assertFalse(retard.peut_etre_justifiee)

    def test_passer_d_absent_a_retard(self):
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(), appel({self.d.etu1: "absent"}))
        self.client.post(self.url_appel(), appel({self.d.etu1: "retard"}))
        absence = Absence.objects.get()
        self.assertEqual((absence.nature, absence.duree_heures), (Absence.Nature.RETARD, 0))

    # --- Nouvelle justification après un refus ---------------------------------------------

    def creer_justification(self, absence, statut=Justification.Statut.EN_ATTENTE):
        j = Justification(absence=absence, motif="Malade", statut=statut)
        j.piece_jointe.save("certificat.pdf", ContentFile(b"%PDF-1.4"), save=False)
        j.save()
        return j

    def test_nouvelle_justification_possible_apres_un_refus(self):
        absence = Absence.objects.create(etudiant=self.d.etu1, seance=self.d.seance, date=MARDI)
        self.creer_justification(absence).traiter(False, self.d.scolarite, "Illisible")
        self.client.force_login(self.d.etu1)
        reponse = self.client.post(f"/absences/{absence.pk}/justifier/", {"motif": "Scan lisible", "piece_jointe": fichier_pdf()})
        self.assertRedirects(reponse, "/absences/mes-absences/")
        self.assertEqual(absence.justifications.count(), 2)
        self.assertEqual(absence.derniere_justification.statut, Justification.Statut.EN_ATTENTE)

    def test_pas_de_seconde_justification_pendant_l_examen(self):
        absence = Absence.objects.create(etudiant=self.d.etu1, seance=self.d.seance, date=MARDI)
        self.creer_justification(absence)
        self.client.force_login(self.d.etu1)
        self.client.post(f"/absences/{absence.pk}/justifier/", {"motif": "Encore", "piece_jointe": fichier_pdf()})
        self.assertEqual(absence.justifications.count(), 1)

    # --- Seuils d'alerte -------------------------------------------------------------------

    def test_avertissement_puis_seuil_critique_notifies_une_seule_fois(self):
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(), appel({self.d.etu1: "absent"}, MARDI))
        self.assertEqual(
            list(AlerteAbsence.objects.values_list("niveau", flat=True)), [AlerteAbsence.Niveau.AVERTISSEMENT]
        )
        self.assertEqual(self.d.etu1.notifications.count(), 1)
        self.assertEqual(self.d.scolarite.notifications.count(), 1)

        # Refaire le même appel ne crée pas de doublon
        self.client.post(self.url_appel(), appel({self.d.etu1: "absent"}, MARDI))
        self.assertEqual(AlerteAbsence.objects.count(), 1)

        self.client.post(self.url_appel(), appel({self.d.etu1: "absent"}, date(2026, 9, 29)))  # mardi précédent
        self.assertTrue(AlerteAbsence.objects.filter(niveau=AlerteAbsence.Niveau.CRITIQUE).exists())
        self.assertEqual(self.d.etu1.notifications.count(), 2)

    def test_les_heures_justifiees_ne_comptent_pas_pour_les_seuils(self):
        Absence.objects.create(
            etudiant=self.d.etu1, seance=self.d.seance, date=MARDI, statut=Absence.Statut.JUSTIFIEE
        )
        AlerteAbsence.verifier(self.d.etu1)
        self.assertFalse(AlerteAbsence.objects.exists())

    # --- Calendrier ------------------------------------------------------------------------

    def test_appel_impossible_un_jour_ferie(self):
        JourNonTravaille.objects.create(nom="Jour férié de test", date_debut=MARDI, date_fin=MARDI)
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(), appel({self.d.etu1: "absent"}))
        self.assertFalse(Absence.objects.exists())

    def test_appel_impossible_pour_une_seance_annulee(self):
        AnnulationSeance.objects.create(seance=self.d.seance, date=MARDI, motif="Grève")
        self.client.force_login(self.d.prof)
        reponse = self.client.get(f"{self.url_appel()}?date={MARDI.isoformat()}")
        self.assertContains(reponse, "a été annulée")
        self.client.post(self.url_appel(), appel({self.d.etu1: "absent"}))
        self.assertFalse(Absence.objects.exists())

    def test_appel_d_un_rattrapage_seulement_a_sa_date(self):
        rattrapage = Seance.objects.create(
            classe=self.d.classe, matiere=self.d.bd, enseignant=self.d.prof, salle=self.d.salle,
            date_unique=date(2026, 10, 3), heure_debut=time(8, 30), heure_fin=time(10, 30),
        )
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(rattrapage), appel({self.d.etu1: "absent"}, date(2026, 10, 10)))
        self.assertFalse(Absence.objects.exists())
        self.client.post(self.url_appel(rattrapage), appel({self.d.etu1: "absent"}, date(2026, 10, 3)))
        self.assertEqual(Absence.objects.get().seance, rattrapage)
