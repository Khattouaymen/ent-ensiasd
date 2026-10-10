from django.test import TestCase

from comptes.models import Utilisateur

from .models import Notification


class OuvrirNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.u = Utilisateur.objects.create(username="etu")
        cls.autre = Utilisateur.objects.create(username="autre")

    def setUp(self):
        self.client.force_login(self.u)

    def test_cliquer_marque_comme_lue_et_redirige(self):
        n = Notification.envoyer(self.u, "Document prêt", lien="/documents/")
        reponse = self.client.get(f"/notifications/{n.pk}/")
        self.assertRedirects(reponse, "/documents/", fetch_redirect_response=False)
        n.refresh_from_db()
        self.assertTrue(n.lue)

    def test_notification_d_un_autre_utilisateur_introuvable(self):
        n = Notification.envoyer(self.autre, "Privé", lien="/documents/")
        self.assertEqual(self.client.get(f"/notifications/{n.pk}/").status_code, 404)

    def test_lien_externe_jamais_suivi(self):
        n = Notification.envoyer(self.u, "Piège", lien="https://exemple.com/")
        self.assertRedirects(self.client.get(f"/notifications/{n.pk}/"), "/notifications/")
