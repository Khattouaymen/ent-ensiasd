import shutil
import tempfile
from datetime import date, time

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from comptes.models import Utilisateur
from config.donnees_test import creer_etablissement, fichier_pdf
from emplois.models import Seance
from structure.models import Classe, Filiere, Matiere, Niveau, Salle

from .models import Absence, Justification

MEDIA_TEST = tempfile.mkdtemp()

# 6 octobre 2026 : un mardi
MARDI = date(2026, 10, 6)


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class AbsencesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        filiere = Filiere.objects.create(code="MGSI", nom="MGSI")
        niveau = Niveau.objects.create(nom="2A")
        cls.classe = Classe.objects.create(filiere=filiere, niveau=niveau, annee_universitaire="2026/2027")
        cls.bd = Matiere.objects.create(code="BD", nom="Bases de données", filiere=filiere, niveau=niveau)
        cls.web = Matiere.objects.create(code="WEB", nom="Web", filiere=filiere, niveau=niveau)
        prof = Utilisateur.objects.create(username="prof", role=Utilisateur.Role.ENSEIGNANT)
        salle = Salle.objects.create(nom="S1")
        cls.seance_bd = Seance.objects.create(
            classe=cls.classe, matiere=cls.bd, enseignant=prof, salle=salle,
            jour=Seance.Jour.MARDI, heure_debut=time(8, 30), heure_fin=time(10, 30),
        )
        cls.seance_web = Seance.objects.create(
            classe=cls.classe, matiere=cls.web, enseignant=prof, salle=salle,
            jour=Seance.Jour.MARDI, heure_debut=time(10, 30), heure_fin=time(12, 0),
        )
        cls.etudiant = Utilisateur.objects.create(username="etu", classe=cls.classe)
        cls.scolarite = Utilisateur.objects.create(username="sco", role=Utilisateur.Role.SCOLARITE)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def test_total_heures_par_matiere(self):
        Absence.objects.create(etudiant=self.etudiant, seance=self.seance_bd, date=MARDI)
        Absence.objects.create(etudiant=self.etudiant, seance=self.seance_bd, date=date(2026, 10, 13))
        Absence.objects.create(
            etudiant=self.etudiant, seance=self.seance_web, date=MARDI, statut=Absence.Statut.JUSTIFIEE
        )
        lignes = {l["matiere"].code: l for l in Absence.heures_par_matiere(self.etudiant)}
        self.assertEqual(lignes["BD"]["total"], 4)
        self.assertEqual(lignes["WEB"]["total"], 1.5)
        self.assertEqual(lignes["WEB"]["justifiees"], 1.5)
        self.assertEqual(lignes["WEB"]["non_justifiees"], 0)

    def test_date_doit_correspondre_au_jour_de_la_seance(self):
        absence = Absence(etudiant=self.etudiant, seance=self.seance_bd, date=date(2026, 10, 7))
        with self.assertRaises(ValidationError):
            absence.full_clean()

    def test_validation_justification_met_a_jour_absence_et_notifie(self):
        absence = Absence.objects.create(etudiant=self.etudiant, seance=self.seance_bd, date=MARDI)
        justif = Justification(absence=absence, motif="Malade")
        justif.piece_jointe.save("certificat.pdf", ContentFile(b"%PDF-1.4"), save=False)
        justif.save()

        justif.traiter(acceptee=True, agent=self.scolarite)

        absence.refresh_from_db()
        self.assertEqual(absence.statut, Absence.Statut.JUSTIFIEE)
        self.assertEqual(self.etudiant.notifications.count(), 1)
        with self.assertRaises(ValidationError):
            justif.traiter(acceptee=False, agent=self.scolarite)

    def test_piece_jointe_refusee_si_type_interdit(self):
        absence = Absence.objects.create(etudiant=self.etudiant, seance=self.seance_bd, date=MARDI)
        justif = Justification(absence=absence, motif="Malade", piece_jointe=ContentFile(b"MZ", name="virus.exe"))
        with self.assertRaises(ValidationError):
            justif.full_clean()


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class AbsencesVuesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()

    def url_appel(self, date=MARDI):
        return f"/absences/appel/{self.d.seance.pk}/?date={date.isoformat()}"

    @staticmethod
    def appel(choix, date=MARDI.isoformat()):
        """Données POST de la feuille d'appel : {étudiant: "present" | "absent" | "retard"}."""
        return {"date": date, **{f"etudiant_{e.pk}": valeur for e, valeur in choix.items()}}

    def test_appel_enregistre_puis_corrige(self):
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(), self.appel({self.d.etu1: "absent", self.d.etu2: "absent"}))
        self.assertEqual(Absence.objects.filter(seance=self.d.seance, date=MARDI).count(), 2)

        # etu2 était finalement présent : on le décoche
        self.client.post(self.url_appel(), self.appel({self.d.etu1: "absent", self.d.etu2: "present"}))
        self.assertEqual(list(Absence.objects.values_list("etudiant", flat=True)), [self.d.etu1.pk])

    def test_appel_ne_supprime_pas_une_absence_deja_justifiee(self):
        absence = Absence.objects.create(etudiant=self.d.etu1, seance=self.d.seance, date=MARDI)
        Justification.objects.create(absence=absence, motif="Malade", piece_jointe="x.pdf")
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(), self.appel({self.d.etu1: "present"}))
        self.assertTrue(Absence.objects.filter(pk=absence.pk).exists())

    def test_appel_ignore_les_etudiants_hors_seance(self):
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(), self.appel({self.d.etu_ia: "absent"}))
        self.assertFalse(Absence.objects.exists())

    def test_appel_refuse_mauvais_jour_et_date_future(self):
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(), self.appel({self.d.etu1: "absent"}, "2026-10-07"))  # un mercredi
        self.client.post(self.url_appel(), self.appel({self.d.etu1: "absent"}, "2099-01-06"))
        self.assertFalse(Absence.objects.exists())

    def test_un_enseignant_ne_fait_l_appel_que_de_ses_seances(self):
        self.client.force_login(self.d.autre_prof)
        self.assertEqual(self.client.get(self.url_appel()).status_code, 404)
        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get(self.url_appel()).status_code, 403)

    def test_etudiant_justifie_et_scolarite_valide(self):
        absence = Absence.objects.create(etudiant=self.d.etu1, seance=self.d.seance, date=MARDI)
        self.client.force_login(self.d.etu1)
        reponse = self.client.post(
            f"/absences/{absence.pk}/justifier/", {"motif": "Rendez-vous médical", "piece_jointe": fichier_pdf()}
        )
        self.assertRedirects(reponse, "/absences/mes-absences/")
        self.assertEqual(self.d.scolarite.notifications.count(), 1)
        justification = absence.justifications.get()

        # L'étudiant et la scolarité peuvent ouvrir la pièce jointe, pas un autre étudiant
        self.assertEqual(self.client.get(f"/absences/justifications/{justification.pk}/piece-jointe/").status_code, 200)
        self.client.force_login(self.d.etu2)
        self.assertEqual(self.client.get(f"/absences/justifications/{justification.pk}/piece-jointe/").status_code, 404)

        self.client.force_login(self.d.scolarite)
        self.client.post(f"/absences/justifications/{justification.pk}/", {"decision": "accepter"})
        absence.refresh_from_db()
        self.assertEqual(absence.statut, Absence.Statut.JUSTIFIEE)

    def test_etudiant_ne_peut_pas_justifier_l_absence_d_un_autre(self):
        absence = Absence.objects.create(etudiant=self.d.etu1, seance=self.d.seance, date=MARDI)
        self.client.force_login(self.d.etu2)
        self.assertEqual(self.client.get(f"/absences/{absence.pk}/justifier/").status_code, 404)

    def test_mes_absences_affiche_le_total_par_matiere(self):
        Absence.objects.create(etudiant=self.d.etu1, seance=self.d.seance, date=MARDI)
        self.client.force_login(self.d.etu1)
        reponse = self.client.get("/absences/mes-absences/")
        self.assertEqual(reponse.context["total"], 2)
        self.assertContains(reponse, "Bases de données")

    def test_export_csv_des_absences_d_une_classe(self):
        Absence.objects.create(etudiant=self.d.etu1, seance=self.d.seance, date=MARDI)
        self.client.force_login(self.d.scolarite)
        reponse = self.client.get(f"/absences/classes/{self.d.classe.pk}/export.csv")
        self.assertEqual(reponse["Content-Type"], "text/csv; charset=utf-8")
        contenu = reponse.content.decode("utf-8-sig")
        self.assertIn("Amrani;", contenu)
        self.assertIn("06/10/2026", contenu)

    def test_export_reserve_au_personnel(self):
        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get(f"/absences/classes/{self.d.classe.pk}/export.csv").status_code, 403)
        self.client.force_login(self.d.prof)
        self.assertEqual(self.client.get("/absences/classes/").status_code, 403)

    def test_modifier_l_emploi_du_temps_ne_change_pas_les_absences_passees(self):
        """Audit, point 3 : la durée est figée au moment de l'appel."""
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(), self.appel({self.d.etu1: "absent"}))
        self.d.seance.heure_fin = time(12, 30)
        self.d.seance.save()
        self.assertEqual(sum(l["total"] for l in Absence.heures_par_matiere(self.d.etu1)), 2)

    def test_appel_refuse_hors_annee_universitaire(self):
        """Audit, point 5 : la classe est en 2026/2027, un mardi de janvier 2025 est refusé."""
        self.client.force_login(self.d.prof)
        self.client.post(self.url_appel(), self.appel({self.d.etu1: "absent"}, "2025-01-07"))
        self.assertFalse(Absence.objects.exists())

    def test_faux_pdf_refuse(self):
        """Audit, point 4 : un exécutable renommé en .pdf est refusé."""
        absence = Absence.objects.create(etudiant=self.d.etu1, seance=self.d.seance, date=MARDI)
        self.client.force_login(self.d.etu1)
        faux = SimpleUploadedFile("certificat.pdf", b"MZ\x90\x00 programme", content_type="application/pdf")
        reponse = self.client.post(f"/absences/{absence.pk}/justifier/", {"motif": "Malade", "piece_jointe": faux})
        self.assertIn("ne correspond pas", str(reponse.context["form"].errors))
        self.assertFalse(Justification.objects.exists())

    def test_nom_du_fichier_csv_avec_accents(self):
        """Audit, point 8 : le nom de fichier est encodé selon la RFC 6266."""
        self.client.force_login(self.d.scolarite)
        reponse = self.client.get(f"/absences/classes/{self.d.classe.pk}/export.csv")
        self.assertIn("filename*=utf-8''absences_MGSI_2%C3%A8me_ann%C3%A9e", reponse["Content-Disposition"])
