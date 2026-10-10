import shutil
import tempfile

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from config.donnees_test import creer_etablissement, fichier_pdf

from .models import Ressource

MEDIA_TEST = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class RessourcesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()
        cls.r_bd = Ressource(titre="Cours BD", matiere=cls.d.bd, deposee_par=cls.d.prof)
        cls.r_bd.fichier.save("bd.pdf", ContentFile(b"%PDF"), save=True)
        cls.r_ml = Ressource(titre="Cours ML", matiere=cls.d.ml, deposee_par=cls.d.autre_prof)
        cls.r_ml.fichier.save("ml.pdf", ContentFile(b"%PDF"), save=True)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def test_etudiant_ne_voit_que_sa_filiere_et_son_niveau(self):
        self.client.force_login(self.d.etu1)
        reponse = self.client.get("/ressources/")
        self.assertEqual(list(reponse.context["page"]), [self.r_bd])

    def test_etudiant_ne_peut_pas_telecharger_une_ressource_d_une_autre_filiere(self):
        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get(f"/ressources/{self.r_bd.pk}/telecharger/").status_code, 200)
        self.assertEqual(self.client.get(f"/ressources/{self.r_ml.pk}/telecharger/").status_code, 404)

    def test_enseignant_depose_un_support(self):
        self.client.force_login(self.d.prof)
        reponse = self.client.post(
            "/ressources/deposer/",
            {"titre": "TD 1", "type": "TD", "matiere": self.d.bd.pk, "fichier": fichier_pdf("td1.pdf")},
        )
        self.assertRedirects(reponse, "/ressources/")
        self.assertTrue(Ressource.objects.filter(titre="TD 1", deposee_par=self.d.prof).exists())

    def test_enseignant_ne_peut_deposer_que_pour_ses_matieres(self):
        self.client.force_login(self.d.prof)
        reponse = self.client.post(
            "/ressources/deposer/",
            {"titre": "Intrus", "type": "COURS", "matiere": self.d.ml.pk, "fichier": fichier_pdf()},
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("matiere", reponse.context["form"].errors)

    def test_type_de_fichier_interdit(self):
        self.client.force_login(self.d.prof)
        reponse = self.client.post(
            "/ressources/deposer/",
            {"titre": "Exe", "type": "COURS", "matiere": self.d.bd.pk, "fichier": fichier_pdf("programme.exe")},
        )
        self.assertIn("fichier", reponse.context["form"].errors)

    def test_etudiant_ne_peut_pas_deposer(self):
        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get("/ressources/deposer/").status_code, 403)

    def test_enseignant_ne_peut_pas_supprimer_le_support_d_un_collegue(self):
        self.client.force_login(self.d.prof)
        self.assertEqual(self.client.post(f"/ressources/{self.r_ml.pk}/supprimer/").status_code, 403)

        a_supprimer = Ressource(titre="Brouillon", matiere=self.d.bd, deposee_par=self.d.prof)
        a_supprimer.fichier.save("brouillon.pdf", ContentFile(b"%PDF"), save=True)
        self.client.post(f"/ressources/{a_supprimer.pk}/supprimer/")
        self.assertFalse(Ressource.objects.filter(pk=a_supprimer.pk).exists())
        self.assertFalse(a_supprimer.fichier.storage.exists(a_supprimer.fichier.name))
