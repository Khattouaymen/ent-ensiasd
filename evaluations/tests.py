import io
import shutil
import tempfile
import zipfile
from datetime import time, timedelta

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from config.donnees_test import creer_etablissement
from notifications.models import Notification
from structure.models import Enseignement

from .models import Devoir, Examen, Rendu, envoyer_rappels

MEDIA_TEST = tempfile.mkdtemp()


def tearDownModule():
    shutil.rmtree(MEDIA_TEST, ignore_errors=True)


def pdf(nom="travail.pdf"):
    return SimpleUploadedFile(nom, b"%PDF-1.4 rendu", content_type="application/pdf")


def destinataires(lien_ou_debut):
    notifications = Notification.objects.filter(message__startswith=lien_ou_debut)
    return set(notifications.values_list("destinataire__username", flat=True))


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class ExamensTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()
        cls.affectation = Enseignement.objects.get(enseignant=cls.d.prof)
        cls.dans_cinq_jours = timezone.localdate() + timedelta(days=5)

    def examen(self, **champs):
        valeurs = {"classe": self.d.classe, "matiere": self.d.bd, "date": self.dans_cinq_jours, "heure_debut": time(9)}
        return Examen.objects.create(**{**valeurs, **champs})

    def test_un_enseignant_programme_un_examen_pour_un_groupe(self):
        self.client.force_login(self.d.prof)
        reponse = self.client.post("/evaluations/examens/nouveau/", {
            "affectation": self.affectation.pk, "groupe": self.d.g1.pk, "type": "CONTROLE",
            "date": self.dans_cinq_jours.isoformat(), "heure_debut": "09:00", "heure_fin": "10:30",
        })
        self.assertRedirects(reponse, "/evaluations/")
        examen = Examen.objects.get()
        self.assertEqual((examen.classe, examen.matiere, examen.cree_par), (self.d.classe, self.d.bd, self.d.prof))
        self.assertEqual(destinataires("Nouvel examen"), {"etu1"})

    def test_un_enseignant_ne_programme_pas_hors_de_ses_affectations(self):
        self.client.force_login(self.d.autre_prof)
        self.client.post("/evaluations/examens/nouveau/", {
            "affectation": self.affectation.pk, "type": "EXAMEN",
            "date": self.dans_cinq_jours.isoformat(), "heure_debut": "09:00",
        })
        self.assertFalse(Examen.objects.exists())

    def test_la_scolarite_choisit_une_matiere_de_la_classe(self):
        self.client.force_login(self.d.scolarite)
        donnees = {"classe": self.d.classe.pk, "type": "EXAMEN", "date": self.dans_cinq_jours.isoformat(), "heure_debut": "14:00"}
        self.client.post("/evaluations/examens/nouveau/", {**donnees, "matiere": self.d.ml.pk})
        self.assertFalse(Examen.objects.exists())
        self.client.post("/evaluations/examens/nouveau/", {**donnees, "matiere": self.d.bd.pk})
        self.assertEqual(Examen.objects.get().cree_par, self.d.scolarite)
        self.assertEqual(destinataires("Nouvel examen"), {"etu1", "etu2"})

    def test_pas_d_examen_a_une_date_passee(self):
        self.client.force_login(self.d.scolarite)
        hier = timezone.localdate() - timedelta(days=1)
        self.client.post("/evaluations/examens/nouveau/", {
            "classe": self.d.classe.pk, "matiere": self.d.bd.pk, "type": "EXAMEN",
            "date": hier.isoformat(), "heure_debut": "09:00",
        })
        self.assertFalse(Examen.objects.exists())

    def test_calendrier_d_un_etudiant(self):
        pour_la_classe = self.examen(titre="Partiel")
        self.examen(titre="Contrôle G2", groupe=self.d.g2)
        self.examen(titre="Classe IA", classe=self.d.classe_ia, matiere=self.d.ml)
        self.client.force_login(self.d.etu1)
        elements = self.client.get("/evaluations/").context["elements"]
        self.assertEqual([e["objet"] for e in elements], [pour_la_classe])
        self.assertEqual(elements[0]["dans_jours"], 5)

    def test_examen_affiche_dans_l_emploi_du_temps(self):
        self.examen(titre="Partiel de BD")
        self.client.force_login(self.d.etu1)
        reponse = self.client.get(f"/emploi-du-temps/?semaine={self.dans_cinq_jours.isoformat()}")
        self.assertContains(reponse, "Partiel de BD")

    def test_rappel_envoye_une_seule_fois_deux_jours_avant(self):
        self.examen(date=timezone.localdate() + timedelta(days=1))
        self.examen(titre="Plus tard")
        self.assertEqual(envoyer_rappels(), 1)
        self.assertEqual(envoyer_rappels(), 0)
        self.assertEqual(destinataires("Rappel"), {"etu1", "etu2"})
        self.assertEqual(Notification.objects.filter(message__startswith="Rappel").count(), 2)

    def test_les_rappels_partent_a_l_ouverture_du_tableau_de_bord(self):
        self.examen(date=timezone.localdate() + timedelta(days=2))
        self.client.force_login(self.d.etu1)
        self.assertContains(self.client.get("/"), "À venir")
        self.assertEqual(destinataires("Rappel"), {"etu1", "etu2"})

    def test_suppression_par_son_auteur_ou_la_scolarite(self):
        examen = self.examen(cree_par=self.d.scolarite)
        self.client.force_login(self.d.prof)  # voit l'examen (sa matière) mais ne l'a pas créé
        self.assertEqual(self.client.post(f"/evaluations/examens/{examen.pk}/supprimer/").status_code, 403)
        self.client.force_login(self.d.scolarite)
        self.client.post(f"/evaluations/examens/{examen.pk}/supprimer/")
        self.assertFalse(Examen.objects.exists())


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class DevoirsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()
        cls.affectation = Enseignement.objects.get(enseignant=cls.d.prof)

    def setUp(self):
        self.devoir = Devoir.objects.create(
            classe=self.d.classe, matiere=self.d.bd, enseignant=self.d.prof, titre="TP 2 – Index",
            consignes="Rendre le script SQL.", date_limite=timezone.now() + timedelta(days=3),
        )
        self.url = f"/evaluations/devoirs/{self.devoir.pk}/"

    def rendre(self, etudiant, nom="travail.pdf"):
        self.client.force_login(etudiant)
        return self.client.post(self.url, {"fichier": pdf(nom), "commentaire": "Voici mon travail"})

    def test_publication_par_l_enseignant_previent_la_classe(self):
        self.client.force_login(self.d.prof)
        limite = timezone.localtime() + timedelta(days=7)
        reponse = self.client.post("/evaluations/devoirs/nouveau/", {
            "affectation": self.affectation.pk, "titre": "Projet", "consignes": "…",
            "date_limite": limite.strftime("%Y-%m-%dT%H:%M"),
        })
        devoir = Devoir.objects.get(titre="Projet")
        self.assertRedirects(reponse, f"/evaluations/devoirs/{devoir.pk}/")
        self.assertEqual(devoir.enseignant, self.d.prof)
        self.assertEqual(destinataires("Nouveau devoir"), {"etu1", "etu2"})

    def test_depot_puis_remplacement_du_fichier(self):
        self.assertRedirects(self.rendre(self.d.etu1, "version1.pdf"), self.url)
        rendu = Rendu.objects.get()
        premier = rendu.fichier.name
        self.assertFalse(rendu.en_retard)
        self.rendre(self.d.etu1, "version2.pdf")
        rendu.refresh_from_db()
        self.assertEqual(Rendu.objects.count(), 1)
        self.assertIn("version2", rendu.fichier.name)
        self.assertFalse(default_storage.exists(premier))

    def test_apres_la_date_limite(self):
        Devoir.objects.filter(pk=self.devoir.pk).update(date_limite=timezone.now() - timedelta(hours=1))
        self.rendre(self.d.etu1)
        self.assertFalse(Rendu.objects.exists())
        Devoir.objects.filter(pk=self.devoir.pk).update(accepte_retard=True)
        self.rendre(self.d.etu1)
        self.assertTrue(Rendu.objects.get().en_retard)

    def test_un_etudiant_d_une_autre_classe_ne_voit_pas_le_devoir(self):
        self.client.force_login(self.d.etu_ia)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_acces_aux_fichiers_rendus(self):
        self.rendre(self.d.etu1)
        url = f"/evaluations/rendus/{Rendu.objects.get().pk}/fichier/"
        attendus = {self.d.etu1: 200, self.d.etu2: 404, self.d.prof: 200, self.d.autre_prof: 404, self.d.scolarite: 200}
        for compte, code in attendus.items():
            self.client.force_login(compte)
            with self.subTest(compte=compte.username):
                self.assertEqual(self.client.get(url).status_code, code)

    def test_archive_zip_des_rendus(self):
        self.rendre(self.d.etu1)
        self.rendre(self.d.etu2)
        self.client.force_login(self.d.prof)
        reponse = self.client.get(f"{self.url}rendus.zip")
        noms = zipfile.ZipFile(io.BytesIO(b"".join(reponse.streaming_content))).namelist()
        self.assertEqual(sorted(n.split("_")[0] for n in noms), ["AMRANI", "BENNANI"])
        self.client.force_login(self.d.autre_prof)
        self.assertEqual(self.client.get(f"{self.url}rendus.zip").status_code, 404)

    def test_rappel_seulement_aux_etudiants_sans_rendu(self):
        self.rendre(self.d.etu1)
        Devoir.objects.filter(pk=self.devoir.pk).update(date_limite=timezone.now() + timedelta(days=1))
        self.assertEqual(envoyer_rappels(), 1)
        self.assertEqual(destinataires("Rappel"), {"etu2"})

    def test_liste_de_l_enseignant(self):
        self.rendre(self.d.etu1)
        self.client.force_login(self.d.prof)
        ligne = self.client.get("/evaluations/devoirs/").context["lignes"][0]
        self.assertEqual((ligne["devoir"].nb_rendus, ligne["attendus"]), (1, 2))

    def test_suppression_du_devoir_et_de_ses_fichiers(self):
        self.rendre(self.d.etu1)
        fichier = Rendu.objects.get().fichier.name
        self.client.force_login(self.d.prof)
        self.client.post(f"{self.url}supprimer/")
        self.assertFalse(Devoir.objects.exists())
        self.assertFalse(default_storage.exists(fichier))
