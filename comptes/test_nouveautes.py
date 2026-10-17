"""Import CSV, changement de mot de passe obligatoire, mot de passe oublié, statistiques et sauvegarde."""

import re
import tempfile
import zipfile
from pathlib import Path

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings

from config.donnees_test import creer_etablissement

from .models import Utilisateur


def csv(contenu, nom="promo.csv"):
    return SimpleUploadedFile(nom, contenu.encode("utf-8"), content_type="text/csv")


class ImportEtudiantsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()

    def setUp(self):
        self.client.force_login(self.d.scolarite)

    def importer(self, contenu):
        return self.client.post("/comptes/importer/", {"classe": self.d.classe.pk, "fichier": csv(contenu)})

    def test_import_cree_les_comptes_et_affiche_les_identifiants(self):
        reponse = self.importer("Nom;Prénom;CNE;E-mail;Groupe\nTazi;Rim;r123;rim@exemple.ma;G2\nAlami;Ali;A456;;\n")
        self.assertEqual(len(reponse.context["comptes"]), 2)
        rim = Utilisateur.objects.get(username="r123")
        self.assertEqual((rim.cne, rim.groupe, rim.classe, rim.role), ("R123", self.d.g2, self.d.classe, "ETUDIANT"))
        self.assertTrue(rim.doit_changer_mot_de_passe)
        # Le mot de passe provisoire affiché fonctionne
        _, mot_de_passe = next(c for c in reponse.context["comptes"] if c[0].username == "r123")
        self.assertTrue(rim.check_password(mot_de_passe))

    def test_import_tout_ou_rien(self):
        reponse = self.importer("nom,prenom,cne,groupe\nTazi,Rim,R123,G1\nAlami,Ali,R123,G9\n")
        self.assertEqual(len(reponse.context["erreurs"]), 1)  # CNE en double (le groupe G9 n'est pas atteint)
        self.assertFalse(Utilisateur.objects.filter(username="r123").exists())

    def test_cne_deja_existant_et_colonnes_manquantes(self):
        self.d.etu1.cne = "D1"
        self.d.etu1.save()
        self.assertEqual(len(self.importer("nom;prenom;cne\nX;Y;D1\n").context["erreurs"]), 1)
        self.assertIn("fichier", self.importer("nom;prenom\nX;Y\n").context["form"].errors)

    def test_import_reserve_au_personnel(self):
        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get("/comptes/importer/").status_code, 403)


class MotDePasseTests(TestCase):
    def setUp(self):
        self.u = Utilisateur.objects.create(username="nouveau", email="nouveau@exemple.ma", doit_changer_mot_de_passe=True)
        self.u.set_password("Provisoire123")
        self.u.save()

    def test_changement_obligatoire_a_la_premiere_connexion(self):
        self.client.force_login(self.u)
        self.assertRedirects(self.client.get("/"), "/mon-compte/mot-de-passe/")
        self.client.post(
            "/mon-compte/mot-de-passe/",
            {"old_password": "Provisoire123", "new_password1": "MonSecret#2026", "new_password2": "MonSecret#2026"},
        )
        self.u.refresh_from_db()
        self.assertFalse(self.u.doit_changer_mot_de_passe)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_mot_de_passe_oublie(self):
        self.client.post("/mot-de-passe-oublie/", {"email": "nouveau@exemple.ma"})
        self.assertEqual(len(mail.outbox), 1)
        lien = re.search(r"http://testserver(/reinitialiser/\S+)", mail.outbox[0].body).group(1)
        reponse = self.client.get(lien, follow=True)
        self.client.post(reponse.redirect_chain[-1][0], {"new_password1": "Retrouve#2026", "new_password2": "Retrouve#2026"})
        self.u.refresh_from_db()
        self.assertTrue(self.u.check_password("Retrouve#2026"))

    def test_adresse_inconnue_sans_indice(self):
        reponse = self.client.post("/mot-de-passe-oublie/", {"email": "inconnu@exemple.ma"})
        self.assertRedirects(reponse, "/mot-de-passe-oublie/envoye/")
        self.assertEqual(len(mail.outbox), 0)

    def test_trois_e_mails_au_plus_par_heure_et_par_adresse(self):
        for _ in range(5):
            reponse = self.client.post("/mot-de-passe-oublie/", {"email": "Nouveau@exemple.ma"})
            # Même page qu'habituellement : la limite ne révèle rien sur l'adresse
            self.assertRedirects(reponse, "/mot-de-passe-oublie/envoye/")
        self.assertEqual(len(mail.outbox), 3)


class StatistiquesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()

    def test_acces(self):
        self.client.force_login(self.d.admin)
        reponse = self.client.get(f"/statistiques/?classe={self.d.classe.pk}")
        self.assertEqual(reponse.status_code, 200)
        semaines = reponse.context["par_semaine"]
        self.assertTrue(1 <= len(semaines) <= 12)
        # Aucune semaine entièrement avant la rentrée (1er septembre)
        self.assertGreaterEqual(semaines[0]["semaine"], "2026-08-26")
        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get("/statistiques/").status_code, 403)


class SauvegardeTests(TransactionTestCase):
    # Hors transaction, comme la commande lancée depuis une console : une transaction ouverte
    # détiendrait le verrou d'écriture de SQLite et empêcherait la copie de la base.

    def test_sauvegarde_et_rotation(self):
        with tempfile.TemporaryDirectory() as dossier, override_settings(
            DOSSIER_SAUVEGARDES=Path(dossier), NB_SAUVEGARDES_CONSERVEES=2, MEDIA_ROOT=Path(dossier) / "media"
        ):
            for _ in range(3):
                call_command("sauvegarder", stdout=open(Path(dossier) / "sortie.txt", "w", encoding="utf-8"))
            archives = sorted(Path(dossier).glob("sauvegarde_ent_*.zip"))
            self.assertEqual(len(archives), 2)
            with zipfile.ZipFile(archives[-1]) as zf:
                self.assertIn("db.sqlite3", zf.namelist())

    def test_refusee_dans_une_transaction_au_lieu_de_bloquer(self):
        with transaction.atomic(), self.assertRaisesMessage(CommandError, "transaction"):
            call_command("sauvegarder")
