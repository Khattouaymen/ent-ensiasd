from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

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


class EnvoiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.u = Utilisateur.objects.create(username="etu")
        Utilisateur.objects.create(username="sco1", role=Utilisateur.Role.SCOLARITE)
        Utilisateur.objects.create(username="sco2", role=Utilisateur.Role.SCOLARITE)
        Utilisateur.objects.create(username="ancien", role=Utilisateur.Role.SCOLARITE, is_active=False)

    def test_message_trop_long_tronque_a_la_taille_du_champ(self):
        n = Notification.envoyer(self.u, "Séance annulée : " + "x" * 400)
        n.refresh_from_db()
        self.assertEqual(len(n.message), 300)
        self.assertTrue(n.message.endswith("…"))

    def test_envoi_au_role_seulement_aux_comptes_actifs(self):
        Notification.envoyer_au_role("SCOLARITE", "Nouvelle demande")
        self.assertEqual(
            sorted(Notification.objects.values_list("destinataire__username", flat=True)), ["sco1", "sco2"]
        )


class PurgeTests(TestCase):
    def test_supprime_seulement_les_anciennes_notifications(self):
        u = Utilisateur.objects.create(username="etu")
        ancienne = Notification.envoyer(u, "Ancienne")
        Notification.objects.filter(pk=ancienne.pk).update(date_creation=timezone.now() - timedelta(days=200))
        recente = Notification.envoyer(u, "Récente")
        sortie = StringIO()
        call_command("purger_notifications", stdout=sortie)
        self.assertEqual(list(Notification.objects.all()), [recente])
        self.assertIn("1 notification(s)", sortie.getvalue())
