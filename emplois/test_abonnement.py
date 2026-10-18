"""Abonnement à l'emploi du temps : adresse secrète et flux iCalendar."""

from datetime import date, datetime, time, timedelta
from datetime import timezone as fuseau

from django.test import TestCase
from django.utils import timezone

from config.donnees_test import MARDI, creer_etablissement
from evaluations.models import Devoir, Examen

from .ical import calendrier_ics, local, utc
from .models import AnnulationSeance, JourNonTravaille

# Date de référence fixe : le flux couvre les quatre semaines précédentes et la suite de l'année.
AUJOURDHUI = date(2026, 10, 1)


def evenements(contenu):
    return contenu.split("BEGIN:VEVENT")[1:]


class AbonnementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = creer_etablissement()

    def flux(self, utilisateur):
        return calendrier_ics(utilisateur, AUJOURDHUI, lambda chemin: f"https://ent.test{chemin}")

    def test_creer_puis_changer_de_lien(self):
        self.client.force_login(self.d.etu1)
        self.client.post("/emploi-du-temps/abonnement/")
        self.d.etu1.refresh_from_db()
        premier = self.d.etu1.jeton_calendrier
        self.assertTrue(premier)
        self.assertContains(self.client.get("/emploi-du-temps/"), f"/emploi-du-temps/calendrier/{premier}.ics")

        self.client.logout()  # le flux se lit sans connexion
        reponse = self.client.get(f"/emploi-du-temps/calendrier/{premier}.ics")
        self.assertEqual(reponse["Content-Type"], "text/calendar; charset=utf-8")
        self.assertTrue(reponse.content.startswith(b"BEGIN:VCALENDAR\r\n"))

        self.client.force_login(self.d.etu1)
        self.client.post("/emploi-du-temps/abonnement/")
        self.client.logout()
        self.assertEqual(self.client.get(f"/emploi-du-temps/calendrier/{premier}.ics").status_code, 404)
        self.assertEqual(self.client.get("/emploi-du-temps/calendrier/inconnu.ics").status_code, 404)

    def test_seances_en_heure_utc_sans_jours_feries_ni_annulations(self):
        mardi_suivant = MARDI + timedelta(weeks=1)
        JourNonTravaille.objects.create(nom="Férié", date_debut=mardi_suivant, date_fin=mardi_suivant)
        AnnulationSeance.objects.create(seance=self.d.seance, date=MARDI + timedelta(weeks=2), motif="Mission")
        contenu = self.flux(self.d.etu1)
        uid = "UID:seance-%d-{}@ent-ensiasd" % self.d.seance.pk
        self.assertIn(uid.format("20261006"), contenu)
        # Heure locale convertie en UTC selon la base des fuseaux horaires (décalage du Maroc variable).
        self.assertIn("DTSTART:" + utc(local(date(2026, 10, 6), time(8, 30))), contenu)
        self.assertIn("SUMMARY:Bases de données (Cours)", contenu)
        self.assertNotIn(uid.format("20261013"), contenu)  # jour férié
        self.assertNotIn(uid.format("20261020"), contenu)  # séance annulée
        self.assertIn(uid.format("20261027"), contenu)

    def test_conversion_en_utc(self):
        heure_marocaine = datetime(2026, 10, 6, 8, 30, tzinfo=fuseau(timedelta(hours=1)))
        self.assertEqual(utc(heure_marocaine), "20261006T073000Z")

    def test_examens_et_dates_limites(self):
        Examen.objects.create(
            classe=self.d.classe, matiere=self.d.bd, date=date(2026, 11, 3), heure_debut=time(9), titre="Partiel"
        )
        du_g2 = Examen.objects.create(
            classe=self.d.classe, groupe=self.d.g2, matiere=self.d.bd, date=date(2026, 11, 4), heure_debut=time(9)
        )
        limite = timezone.make_aware(datetime(2026, 11, 5, 23, 59))
        Devoir.objects.create(
            classe=self.d.classe, matiere=self.d.bd, enseignant=self.d.prof, titre="TP noté", consignes="…",
            date_limite=limite,
        )
        contenu = self.flux(self.d.etu1)
        self.assertIn("SUMMARY:Examen : Partiel", contenu)
        self.assertNotIn(f"UID:examen-{du_g2.pk}@", contenu)  # examen du groupe G2
        self.assertIn("SUMMARY:À rendre : TP noté", contenu)
        self.assertIn("DTEND:" + utc(limite), contenu)
        self.assertIn("DTSTART:" + utc(limite - timedelta(minutes=30)), contenu)
        self.assertIn("https://ent.test/evaluations/devoirs/", contenu.replace("\r\n ", ""))

    def test_rien_de_la_classe_voisine(self):
        contenu = self.flux(self.d.etu_ia)
        self.assertEqual(evenements(contenu), [])

    def test_flux_de_l_enseignant(self):
        contenu = self.flux(self.d.prof)
        self.assertIn("DESCRIPTION:MGSI – 2ème année (2026/2027)", contenu.replace("\r\n ", ""))
        self.assertTrue(evenements(contenu))

    def test_format_rfc_5545(self):
        contenu = self.flux(self.d.etu1)
        self.assertTrue(contenu.endswith("END:VCALENDAR\r\n"))
        lignes = contenu.split("\r\n")
        self.assertNotIn("\n", "".join(lignes))
        self.assertLessEqual(max(len(ligne.encode("utf-8")) for ligne in lignes), 75)
