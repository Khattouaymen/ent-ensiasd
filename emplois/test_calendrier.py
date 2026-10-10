"""Calendrier : annulations, rattrapages, jours non travaillés, affectations et formulaire d'administration."""

from datetime import date, time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from config.donnees_test import MARDI, creer_etablissement

from .models import AnnulationSeance, JourNonTravaille, Seance
from .views import planning


class CalendrierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()

    def rattrapage(self, **kwargs):
        valeurs = dict(
            classe=self.d.classe, matiere=self.d.bd, enseignant=self.d.prof, salle=self.d.salle,
            date_unique=MARDI, heure_debut=time(8, 30), heure_fin=time(10, 30),
        )
        valeurs.update(kwargs)
        return Seance(**valeurs)

    def test_annulation_notifie_l_enseignant_et_les_etudiants(self):
        annulation = AnnulationSeance.objects.create(seance=self.d.seance, date=MARDI, motif="Mission")
        annulation.notifier()
        for u in (self.d.prof, self.d.etu1, self.d.etu2):
            self.assertEqual(u.notifications.count(), 1)
        self.assertEqual(self.d.etu_ia.notifications.count(), 0)

    def test_annulation_refusee_un_autre_jour(self):
        with self.assertRaises(ValidationError):
            AnnulationSeance(seance=self.d.seance, date=MARDI + timedelta(days=1)).full_clean()

    def test_planning_de_la_semaine(self):
        lundi = MARDI - timedelta(days=1)
        AnnulationSeance.objects.create(seance=self.d.seance, date=MARDI)
        rattrapage = self.rattrapage(date_unique=MARDI + timedelta(days=4), salle=self.d.salle)
        rattrapage.save()
        JourNonTravaille.objects.create(nom="Pont", date_debut=lundi + timedelta(days=2), date_fin=lundi + timedelta(days=2))

        jours = {j["date"]: j for j in planning(Seance.objects.all(), lundi, lundi + timedelta(days=5))}
        self.assertEqual(jours[MARDI]["seances"][0][0], self.d.seance)
        self.assertIsNotNone(jours[MARDI]["seances"][0][1])  # annulée ce jour-là
        self.assertEqual(jours[MARDI + timedelta(days=4)]["seances"][0][0], rattrapage)
        self.assertEqual(jours[lundi + timedelta(days=2)]["fermeture"].nom, "Pont")
        # La séance hebdomadaire réapparaît la semaine suivante, sans annulation
        suivante = planning(Seance.objects.filter(date_unique=None), lundi + timedelta(days=7), lundi + timedelta(days=12))
        self.assertIsNone(suivante[1]["seances"][0][1])

    def test_rattrapage_possible_dans_le_creneau_d_une_seance_annulee(self):
        with self.assertRaises(ValidationError):
            self.rattrapage().full_clean()  # même salle, même enseignant, même classe : conflit
        AnnulationSeance.objects.create(seance=self.d.seance, date=MARDI)
        self.rattrapage().full_clean()

    def test_deux_rattrapages_a_des_dates_differentes_ne_sont_pas_en_conflit(self):
        self.rattrapage(date_unique=date(2026, 9, 29)).save()
        self.rattrapage(date_unique=date(2026, 9, 22), heure_debut=time(14, 0), heure_fin=time(16, 0)).save()
        self.rattrapage(date_unique=date(2026, 9, 15), heure_debut=time(14, 0), heure_fin=time(16, 0)).full_clean()

    def test_le_jour_d_un_rattrapage_est_deduit_de_sa_date(self):
        s = self.rattrapage(date_unique=date(2026, 10, 9), heure_debut=time(14, 0), heure_fin=time(16, 0))
        s.full_clean()
        s.save()
        self.assertEqual(s.jour, Seance.Jour.VENDREDI)

    def test_pas_de_seance_le_dimanche(self):
        with self.assertRaises(ValidationError):
            self.rattrapage(date_unique=date(2026, 10, 11)).full_clean()

    def test_enseignant_non_affecte_refuse(self):
        s = self.rattrapage(enseignant=self.d.autre_prof, heure_debut=time(14, 0), heure_fin=time(16, 0))
        with self.assertRaisesMessage(ValidationError, "n'est pas affecté"):
            s.full_clean()

    def test_formulaire_admin_indique_la_classe_de_chaque_groupe(self):
        self.client.force_login(self.d.admin)
        reponse = self.client.get("/admin/emplois/seance/add/")
        self.assertContains(reponse, f'data-classe="{self.d.classe.pk}"', count=2)
        self.assertContains(reponse, "seance_groupes.js")

    def test_emploi_du_temps_par_semaine(self):
        self.client.force_login(self.d.etu1)
        reponse = self.client.get(f"/emploi-du-temps/?semaine={MARDI.isoformat()}")
        self.assertEqual(reponse.context["lundi"], MARDI - timedelta(days=1))
        self.assertContains(reponse, "Bases de données")
