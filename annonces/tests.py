from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from config.donnees_test import creer_etablissement
from notifications.models import Notification

from .models import Annonce


class AnnoncesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()
        cls.pour_tous = Annonce.objects.create(titre="Rentrée", contenu="Bienvenue", auteur=cls.d.scolarite)
        cls.pour_mgsi = Annonce.objects.create(titre="Réunion MGSI", contenu="…", filiere=cls.d.mgsi, auteur=cls.d.scolarite)
        cls.pour_classe = Annonce.objects.create(titre="TP déplacé", contenu="…", classe=cls.d.classe, auteur=cls.d.prof)
        cls.pour_ia = Annonce.objects.create(titre="Classe IA", contenu="…", classe=cls.d.classe_ia, auteur=cls.d.scolarite)
        cls.expiree = Annonce.objects.create(
            titre="Ancienne", contenu="…", auteur=cls.d.scolarite, date_fin=timezone.localdate() - timedelta(days=1)
        )

    def titres_visibles(self, utilisateur):
        return set(Annonce.visibles_par(utilisateur).values_list("titre", flat=True))

    def test_un_etudiant_ne_voit_que_ses_annonces(self):
        self.assertEqual(self.titres_visibles(self.d.etu1), {"Rentrée", "Réunion MGSI", "TP déplacé"})
        self.assertEqual(self.titres_visibles(self.d.etu_ia), {"Rentrée", "Classe IA"})

    def test_un_enseignant_voit_les_annonces_de_ses_classes(self):
        self.assertEqual(self.titres_visibles(self.d.prof), {"Rentrée", "Réunion MGSI", "TP déplacé"})
        self.assertEqual(self.titres_visibles(self.d.autre_prof), {"Rentrée"})

    def test_la_scolarite_voit_tout_sauf_les_annonces_expirees(self):
        self.assertEqual(len(self.titres_visibles(self.d.scolarite)), 4)
        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get(f"/annonces/{self.pour_ia.pk}/").status_code, 404)

    def test_publication_pour_une_classe_notifie_ses_etudiants(self):
        self.client.force_login(self.d.scolarite)
        reponse = self.client.post(
            "/annonces/nouvelle/", {"titre": "Examen avancé", "destinataires": f"c-{self.d.classe.pk}", "contenu": "Lundi 9 h"}
        )
        annonce = Annonce.objects.get(titre="Examen avancé")
        self.assertRedirects(reponse, f"/annonces/{annonce.pk}/")
        self.assertEqual(annonce.classe, self.d.classe)
        destinataires = set(Notification.objects.filter(lien=f"/annonces/{annonce.pk}/").values_list("destinataire", flat=True))
        self.assertEqual(destinataires, {self.d.etu1.pk, self.d.etu2.pk})

    def test_un_enseignant_ne_peut_cibler_que_ses_classes(self):
        self.client.force_login(self.d.prof)
        for cible in (f"c-{self.d.classe_ia.pk}", "tous", f"f-{self.d.mgsi.pk}"):
            self.client.post("/annonces/nouvelle/", {"titre": "Hors classe", "destinataires": cible, "contenu": "…"})
        self.assertFalse(Annonce.objects.filter(titre="Hors classe").exists())
        self.client.post("/annonces/nouvelle/", {"titre": "Ma classe", "destinataires": f"c-{self.d.classe.pk}", "contenu": "…"})
        self.assertTrue(Annonce.objects.filter(titre="Ma classe", auteur=self.d.prof).exists())

    def test_un_etudiant_ne_publie_pas(self):
        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get("/annonces/nouvelle/").status_code, 403)

    def test_suppression_par_l_auteur_ou_la_scolarite_seulement(self):
        self.client.force_login(self.d.autre_prof)
        self.assertEqual(self.client.post(f"/annonces/{self.pour_classe.pk}/supprimer/").status_code, 403)
        self.client.force_login(self.d.prof)
        self.client.post(f"/annonces/{self.pour_classe.pk}/supprimer/")
        self.assertFalse(Annonce.objects.filter(pk=self.pour_classe.pk).exists())
        self.client.force_login(self.d.scolarite)
        self.client.post(f"/annonces/{self.pour_mgsi.pk}/supprimer/")
        self.assertFalse(Annonce.objects.filter(pk=self.pour_mgsi.pk).exists())

    def test_une_seule_cible_par_annonce(self):
        with self.assertRaises(IntegrityError):
            Annonce.objects.create(titre="Double", contenu="…", filiere=self.d.mgsi, classe=self.d.classe)

    def test_annonces_sur_le_tableau_de_bord(self):
        self.client.force_login(self.d.etu1)
        self.assertContains(self.client.get("/"), "TP déplacé")
