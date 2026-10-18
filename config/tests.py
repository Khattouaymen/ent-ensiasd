"""Fichiers statiques versionnés, tels que servis en production (DJANGO_DEBUG=0)."""

import re
import shutil
import tempfile

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings

from config.donnees_test import creer_etablissement

STATIC_TEST = tempfile.mkdtemp()


@override_settings(
    STATIC_ROOT=STATIC_TEST,
    STORAGES={**settings.STORAGES, "staticfiles": {"BACKEND": settings.STOCKAGE_STATIQUES_PRODUCTION}},
)
class FichiersStatiquesVersionnesTests(TestCase):
    """Chaque gabarit ne doit utiliser que des fichiers statiques qui existent : sinon, en production,
    la page entière renvoie une erreur 500 (fichier absent du manifeste de collectstatic)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command("collectstatic", interactive=False, verbosity=0)
        cls.addClassCleanup(shutil.rmtree, STATIC_TEST, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()

    def test_pages_principales_avec_noms_versionnes(self):
        reponse = self.client.get("/connexion/")
        self.assertEqual(reponse.status_code, 200)
        self.assertRegex(reponse.content.decode(), r"/static/css/ent\.[0-9a-f]{12}\.css")
        pages = {
            self.d.etu1: ["/", "/emploi-du-temps/", "/absences/mes-absences/", "/ressources/", "/documents/"],
            self.d.prof: ["/", "/absences/appel/", f"/absences/appel/{self.d.seance.pk}/"],
            self.d.scolarite: ["/statistiques/", "/absences/justifications/", "/absences/classes/"],
            self.d.admin: ["/", "/admin/", "/admin/emplois/seance/add/"],
        }
        for compte, urls in pages.items():
            self.client.force_login(compte)
            for url in urls:
                with self.subTest(compte=compte.username, url=url):
                    reponse = self.client.get(url)
                    self.assertEqual(reponse.status_code, 200)
                    references = re.findall(r"/static/[^\"'\s<>()]+\.\w+", reponse.content.decode())
                    self.assertTrue(references)
                    self.assertEqual([r for r in references if not re.search(r"\.[0-9a-f]{12}\.\w+$", r)], [])
