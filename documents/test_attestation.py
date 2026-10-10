"""Attestation générée automatiquement et ajout du document après le passage à « Prête »."""

import shutil
import tempfile

from django.test import TestCase, override_settings

from config.donnees_test import creer_etablissement, fichier_pdf

from .models import DemandeDocument

MEDIA_TEST = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class AttestationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def demande(self, type_document=DemandeDocument.TypeDocument.ATTESTATION_SCOLARITE, statut="ACCEPTEE", etudiant=None):
        return DemandeDocument.objects.create(etudiant=etudiant or self.d.etu1, type_document=type_document, statut=statut)

    def test_attestation_generee_au_passage_a_prete(self):
        demande = self.demande()
        self.client.force_login(self.d.scolarite)
        self.client.post(f"/documents/{demande.pk}/traiter/", {"statut": "PRETE"})
        demande.refresh_from_db()
        self.assertEqual(demande.statut, DemandeDocument.Statut.PRETE)
        with demande.document.open("rb") as f:
            self.assertTrue(f.read(4) == b"%PDF")

        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get(f"/documents/{demande.pk}/telecharger/").status_code, 200)

    def test_pas_d_attestation_sans_classe(self):
        sans_classe = self.d.etu1.__class__.objects.create(username="sans_classe")
        demande = self.demande(etudiant=sans_classe)
        self.client.force_login(self.d.scolarite)
        self.client.post(f"/documents/{demande.pk}/traiter/", {"statut": "PRETE"})
        demande.refresh_from_db()
        self.assertEqual(demande.statut, DemandeDocument.Statut.PRETE)
        self.assertFalse(demande.document)

    def test_joindre_le_document_apres_coup(self):
        demande = self.demande(type_document=DemandeDocument.TypeDocument.RELEVE_NOTES, statut="PRETE")
        self.client.force_login(self.d.scolarite)
        reponse = self.client.post(
            f"/documents/{demande.pk}/traiter/", {"action": "joindre", "document": fichier_pdf("releve.pdf")}
        )
        self.assertRedirects(reponse, f"/documents/{demande.pk}/traiter/")
        demande.refresh_from_db()
        self.assertTrue(demande.document)
        self.assertEqual(self.d.etu1.notifications.count(), 1)

    def test_generer_l_attestation_apres_coup(self):
        demande = self.demande(statut="PRETE")
        self.client.force_login(self.d.scolarite)
        self.client.post(f"/documents/{demande.pk}/traiter/", {"action": "generer"})
        demande.refresh_from_db()
        self.assertTrue(demande.document.name.endswith(".pdf"))
