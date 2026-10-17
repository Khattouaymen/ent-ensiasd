from unittest import mock

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from structure.models import Classe, Filiere, Groupe, Niveau

from .models import Utilisateur


class AuthentificationTests(TestCase):
    """BF01 / BNF01 : authentification obligatoire et accès par rôle."""

    def test_page_protegee_redirige_vers_connexion(self):
        reponse = self.client.get("/")
        self.assertRedirects(reponse, "/connexion/?next=/")

    def test_connexion_puis_tableau_de_bord(self):
        u = Utilisateur.objects.create(username="etu", role=Utilisateur.Role.ETUDIANT)
        u.set_password("MotDePasse!2026")
        u.save()
        reponse = self.client.post("/connexion/", {"username": "etu", "password": "MotDePasse!2026"}, follow=True)
        self.assertContains(reponse, "Bonjour")

    def test_mot_de_passe_stocke_chiffre(self):
        u = Utilisateur.objects.create(username="etu")
        u.set_password("MotDePasse!2026")
        self.assertNotIn("MotDePasse", u.password)

    def test_tableau_de_bord_pour_chaque_role(self):
        for role in Utilisateur.Role.values:
            with self.subTest(role=role):
                u = Utilisateur.objects.create(username=f"u_{role}", role=role)
                self.client.force_login(u)
                self.assertEqual(self.client.get("/").status_code, 200)

    def test_seul_l_admin_accede_a_l_administration(self):
        for role, attendu in [("ETUDIANT", 302), ("ENSEIGNANT", 302), ("SCOLARITE", 302), ("ADMIN", 200)]:
            with self.subTest(role=role):
                self.client.force_login(Utilisateur.objects.create(username=f"a_{role}", role=role))
                self.assertEqual(self.client.get("/admin/").status_code, attendu)


class UtilisateurTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        filiere = Filiere.objects.create(code="MGSI", nom="MGSI")
        niveau = Niveau.objects.create(nom="2A")
        cls.classe = Classe.objects.create(filiere=filiere, niveau=niveau, annee_universitaire="2026/2027")
        autre = Classe.objects.create(filiere=filiere, niveau=niveau, annee_universitaire="2027/2028")
        cls.groupe_autre_classe = Groupe.objects.create(classe=autre, nom="G1")

    def test_enseignant_ne_peut_pas_etre_affecte_a_une_classe(self):
        u = Utilisateur(username="prof", role=Utilisateur.Role.ENSEIGNANT, classe=self.classe)
        with self.assertRaises(ValidationError):
            u.full_clean()

    def test_groupe_doit_appartenir_a_la_classe(self):
        u = Utilisateur(username="etu", classe=self.classe, groupe=self.groupe_autre_classe)
        with self.assertRaises(ValidationError):
            u.full_clean()


class DroitsAdministrateurTests(TestCase):
    """Les droits d'administration découlent uniquement du rôle (audit, points 1 et 2)."""

    def test_un_admin_qui_change_de_role_perd_ses_droits(self):
        u = Utilisateur.objects.create(username="ex_admin", role=Utilisateur.Role.ADMIN)
        self.assertTrue(u.is_superuser)
        u.role = Utilisateur.Role.ENSEIGNANT
        u.save()
        u.refresh_from_db()
        self.assertFalse(u.is_superuser)
        self.assertFalse(u.is_staff)
        self.assertFalse(u.est_admin)
        self.client.force_login(u)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_superutilisateur_impossible_sans_le_role_admin(self):
        u = Utilisateur.objects.create(username="intrus", is_superuser=True, is_staff=True)
        u.refresh_from_db()
        self.assertFalse(u.is_superuser)

    def test_createsuperuser_cree_un_administrateur(self):
        u = Utilisateur.objects.create_superuser("chef", "chef@ensiasd.test", "MotDePasse!2026")
        self.assertEqual(u.role, Utilisateur.Role.ADMIN)
        self.assertTrue(u.is_superuser)
        self.assertFalse(u.est_etudiant)


class ProtectionConnexionTests(TestCase):
    """Blocage après 5 échecs de connexion (audit, point 6)."""

    def setUp(self):
        cache.clear()
        self.u = Utilisateur.objects.create(username="cible")
        self.u.set_password("BonMotDePasse!2026")
        self.u.save()

    def connexion(self, mot_de_passe, ip="10.0.0.1"):
        return self.client.post("/connexion/", {"username": "cible", "password": mot_de_passe}, REMOTE_ADDR=ip)

    def test_blocage_apres_cinq_echecs(self):
        for _ in range(5):
            self.assertContains(self.connexion("faux"), "Identifiant ou mot de passe incorrect")
        # Même le bon mot de passe est refusé pendant le blocage
        self.assertContains(self.connexion("BonMotDePasse!2026"), "Trop de tentatives")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_le_blocage_ne_touche_pas_une_autre_adresse_ip(self):
        for _ in range(5):
            self.connexion("faux")
        self.assertEqual(self.connexion("BonMotDePasse!2026", ip="10.0.0.2").status_code, 302)

    def test_le_blocage_court_depuis_le_premier_echec(self):
        # 2e échec 10 minutes après le 1er : le compteur expire 5 minutes plus tard, pas 15
        with mock.patch("comptes.forms.time") as horloge, mock.patch("comptes.forms.cache", wraps=cache) as faux_cache:
            horloge.time.side_effect = [1000.0, 1600.0]
            self.connexion("faux")
            self.connexion("faux")
        self.assertEqual([appel.kwargs["timeout"] for appel in faux_cache.set.call_args_list], [900, 300])

    def test_une_connexion_reussie_remet_le_compteur_a_zero(self):
        for _ in range(4):
            self.connexion("faux")
        self.assertEqual(self.connexion("BonMotDePasse!2026").status_code, 302)
        self.client.logout()
        for _ in range(4):
            self.connexion("faux")
        self.assertEqual(self.connexion("BonMotDePasse!2026").status_code, 302)


class MonCompteTests(TestCase):
    """Changement de mot de passe par l'utilisateur (audit, point 7)."""

    def setUp(self):
        self.u = Utilisateur.objects.create(username="etu")
        self.u.set_password("AncienMotDePasse!1")
        self.u.save()
        self.client.force_login(self.u)

    def changer(self, ancien):
        return self.client.post(
            "/mon-compte/mot-de-passe/",
            {"old_password": ancien, "new_password1": "NouveauSecret#2026", "new_password2": "NouveauSecret#2026"},
        )

    def test_changer_son_mot_de_passe(self):
        self.assertEqual(self.client.get("/mon-compte/").status_code, 200)
        self.assertRedirects(self.changer("AncienMotDePasse!1"), "/mon-compte/")
        self.u.refresh_from_db()
        self.assertTrue(self.u.check_password("NouveauSecret#2026"))

    def test_ancien_mot_de_passe_obligatoire(self):
        self.assertEqual(self.changer("faux").status_code, 200)
        self.u.refresh_from_db()
        self.assertTrue(self.u.check_password("AncienMotDePasse!1"))


class PerformanceAdminTests(TestCase):
    """Le nombre de requêtes de la liste des comptes ne dépend pas du nombre de comptes (audit, point 9)."""

    def compter_requetes(self):
        with CaptureQueriesContext(connection) as requetes:
            self.client.get("/admin/comptes/utilisateur/")
        return len(requetes)

    def test_liste_des_utilisateurs_sans_requetes_en_cascade(self):
        filiere = Filiere.objects.create(code="MGSI", nom="MGSI")
        niveau = Niveau.objects.create(nom="2A")
        classe = Classe.objects.create(filiere=filiere, niveau=niveau, annee_universitaire="2026/2027")
        groupe = Groupe.objects.create(classe=classe, nom="G1")
        self.client.force_login(Utilisateur.objects.create(username="adm", role=Utilisateur.Role.ADMIN))

        Utilisateur.objects.create(username="e0", classe=classe, groupe=groupe)
        avec_un_etudiant = self.compter_requetes()
        for i in range(1, 30):
            Utilisateur.objects.create(username=f"e{i}", classe=classe, groupe=groupe)
        self.assertEqual(self.compter_requetes(), avec_un_etudiant)
