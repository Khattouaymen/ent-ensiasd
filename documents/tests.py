import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from comptes.models import Utilisateur
from config.donnees_test import creer_etablissement, fichier_pdf

from .models import DemandeDocument

MEDIA_TEST = tempfile.mkdtemp()


class CycleDeVieDemandeTests(TestCase):
    """BF09 : statuts en attente → acceptée → prête, ou refusée."""

    @classmethod
    def setUpTestData(cls):
        cls.etudiant = Utilisateur.objects.create(username="etu")
        cls.scolarite = Utilisateur.objects.create(username="sco", role=Utilisateur.Role.SCOLARITE)

    def setUp(self):
        self.demande = DemandeDocument.objects.create(
            etudiant=self.etudiant, type_document=DemandeDocument.TypeDocument.ATTESTATION_SCOLARITE
        )

    def test_parcours_normal_notifie_a_chaque_etape(self):
        self.demande.changer_statut(DemandeDocument.Statut.ACCEPTEE, self.scolarite)
        self.demande.changer_statut(DemandeDocument.Statut.PRETE, self.scolarite)
        self.assertEqual(self.demande.statut, DemandeDocument.Statut.PRETE)
        self.assertEqual(self.demande.traitee_par, self.scolarite)
        self.assertEqual(self.etudiant.notifications.count(), 2)

    def test_transition_interdite(self):
        with self.assertRaises(ValidationError):
            self.demande.changer_statut(DemandeDocument.Statut.PRETE, self.scolarite)

    def test_demande_refusee_est_definitive(self):
        self.demande.changer_statut(DemandeDocument.Statut.REFUSEE, self.scolarite, "Dossier incomplet")
        with self.assertRaises(ValidationError):
            self.demande.changer_statut(DemandeDocument.Statut.ACCEPTEE, self.scolarite)

    def test_deux_agents_traitent_la_meme_demande(self):
        vue_par_a = DemandeDocument.objects.get(pk=self.demande.pk)
        vue_par_b = DemandeDocument.objects.get(pk=self.demande.pk)
        vue_par_a.changer_statut(DemandeDocument.Statut.ACCEPTEE, self.scolarite)
        with self.assertRaisesMessage(ValidationError, "un autre agent"):
            vue_par_b.changer_statut(DemandeDocument.Statut.REFUSEE, self.scolarite, "Refus")
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, DemandeDocument.Statut.ACCEPTEE)
        self.assertEqual(self.etudiant.notifications.count(), 1)


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class DemandesVuesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def test_etudiant_demande_un_document_et_la_scolarite_est_notifiee(self):
        self.client.force_login(self.d.etu1)
        reponse = self.client.post("/documents/nouvelle/", {"type_document": "RELEVE_NOTES", "motif": "Stage"})
        self.assertRedirects(reponse, "/documents/")
        self.assertEqual(self.d.etu1.demandes_documents.count(), 1)
        self.assertEqual(self.d.scolarite.notifications.count(), 1)

    def test_pas_deux_demandes_en_cours_pour_le_meme_document(self):
        self.client.force_login(self.d.etu1)
        self.client.post("/documents/nouvelle/", {"type_document": "RELEVE_NOTES"})
        reponse = self.client.post("/documents/nouvelle/", {"type_document": "RELEVE_NOTES"})
        self.assertIn("type_document", reponse.context["form"].errors)

    def test_traitement_complet_et_telechargement_reserve_a_l_etudiant(self):
        demande = DemandeDocument.objects.create(etudiant=self.d.etu1, type_document="ATTESTATION_SCOLARITE")
        self.client.force_login(self.d.scolarite)
        self.client.post(f"/documents/{demande.pk}/traiter/", {"statut": "ACCEPTEE"})
        reponse = self.client.post(
            f"/documents/{demande.pk}/traiter/", {"statut": "PRETE", "document": fichier_pdf("attestation.pdf")}
        )
        self.assertRedirects(reponse, "/documents/")
        demande.refresh_from_db()
        self.assertEqual(demande.statut, DemandeDocument.Statut.PRETE)

        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get(f"/documents/{demande.pk}/telecharger/").status_code, 200)
        self.client.force_login(self.d.etu2)
        self.assertEqual(self.client.get(f"/documents/{demande.pk}/telecharger/").status_code, 404)

    def test_document_joint_seulement_au_statut_prete(self):
        demande = DemandeDocument.objects.create(etudiant=self.d.etu1, type_document="ATTESTATION_SCOLARITE")
        self.client.force_login(self.d.scolarite)
        reponse = self.client.post(f"/documents/{demande.pk}/traiter/", {"statut": "ACCEPTEE", "document": fichier_pdf()})
        self.assertIn("document", reponse.context["form"].errors)

    def test_etudiant_ne_peut_pas_traiter(self):
        demande = DemandeDocument.objects.create(etudiant=self.d.etu1, type_document="ATTESTATION_SCOLARITE")
        self.client.force_login(self.d.etu1)
        self.assertEqual(self.client.get(f"/documents/{demande.pk}/traiter/").status_code, 403)

    def test_etudiant_ne_voit_que_ses_demandes(self):
        DemandeDocument.objects.create(etudiant=self.d.etu2, type_document="RELEVE_NOTES")
        self.client.force_login(self.d.etu1)
        self.assertEqual(len(self.client.get("/documents/").context["page"].object_list), 0)
