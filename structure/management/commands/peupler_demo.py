"""Remplit la base avec des données fictives pour les tests et la démonstration.

    python manage.py peupler_demo
    python manage.py peupler_demo --mot-de-passe "<mot de passe>"
    python manage.py peupler_demo --mot-de-passe-aleatoire       (généré et affiché une seule fois)
En production, l'une des deux options est obligatoire.
"""

import random
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from absences.models import Absence, AlerteAbsence, Justification
from annonces.models import Annonce
from comptes.importation import mot_de_passe_provisoire
from comptes.models import Utilisateur
from documents.attestation import generer_attestation
from documents.models import DemandeDocument
from emplois.models import AnnulationSeance, JourNonTravaille, Seance
from evaluations.models import Devoir, Examen, Rendu
from ressources.models import Ressource
from structure.models import Classe, Enseignement, Filiere, Groupe, Matiere, Niveau, Salle

MOT_DE_PASSE_DEMO = "Ensiasd@2026"

ETUDIANTS = [
    ("Yassine", "Amrani"), ("Salma", "Bennani"), ("Omar", "Chraibi"), ("Imane", "Daoudi"),
    ("Hamza", "El Idrissi"), ("Khadija", "Fassi"), ("Mehdi", "Ghali"), ("Nadia", "Hajji"),
    ("Ayoub", "Kettani"), ("Sara", "Lahlou"),
]
ENSEIGNANTS = [("Karim", "Alaoui"), ("Fatima", "Berrada"), ("Rachid", "Tazi")]


class Command(BaseCommand):
    help = "Crée des données fictives (filière, classe, comptes, emploi du temps, absences…)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mot-de-passe",
            help="Mot de passe de tous les comptes de démonstration. Obligatoire en production : "
            "celui par défaut est publié dans le README.",
        )
        parser.add_argument(
            "--mot-de-passe-aleatoire",
            action="store_true",
            help="Génère un mot de passe aléatoire pour les comptes de démonstration et l'affiche une seule fois.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        mot_de_passe = options["mot_de_passe"]
        if options["mot_de_passe_aleatoire"]:
            mot_de_passe = mot_de_passe_provisoire(12)
        elif mot_de_passe is None:
            if not settings.DEBUG:
                raise CommandError(
                    "En production, choisissez le mot de passe des comptes de démonstration : "
                    'python manage.py peupler_demo --mot-de-passe "…" (ou --mot-de-passe-aleatoire)'
                )
            mot_de_passe = MOT_DE_PASSE_DEMO
        else:
            try:
                validate_password(mot_de_passe)
            except ValidationError as erreur:
                raise CommandError(" ".join(erreur.messages)) from None

        if Filiere.objects.filter(code="MGSI").exists():
            raise CommandError(
                "La base contient déjà les données de démonstration. "
                "Supprimez db.sqlite3 puis relancez « migrate » et « peupler_demo »."
            )

        def compte(username, role, prenom, nom, **extra):
            u = Utilisateur(username=username, role=role, first_name=prenom, last_name=nom,
                            email=f"{username}@ensiasd.test", **extra)
            u.set_password(mot_de_passe)
            u.save()
            return u

        # Structure de l'établissement
        mgsi = Filiere.objects.create(code="MGSI", nom="Management et Gouvernance des Systèmes d'Information")
        Filiere.objects.create(code="IA", nom="Intelligence Artificielle")
        Niveau.objects.create(nom="1ère année", ordre=1)
        a2 = Niveau.objects.create(nom="2ème année", ordre=2)
        classe = Classe.objects.create(filiere=mgsi, niveau=a2, annee_universitaire="2026/2027")
        g1 = Groupe.objects.create(classe=classe, nom="G1")
        g2 = Groupe.objects.create(classe=classe, nom="G2")

        amphi = Salle.objects.create(nom="Amphi A", type=Salle.Type.AMPHI, capacite=120)
        s101 = Salle.objects.create(nom="Salle 101", capacite=40)
        s102 = Salle.objects.create(nom="Salle 102", capacite=40)
        labo = Salle.objects.create(nom="Labo Info 1", type=Salle.Type.LABO, capacite=30)

        def matiere(code, nom, vh):
            return Matiere.objects.create(code=code, nom=nom, filiere=mgsi, niveau=a2, volume_horaire=vh)

        gp = matiere("MGSI-GP", "Gestion de projet agile", 42)
        bd = matiere("MGSI-BD", "Bases de données avancées", 48)
        web = matiere("MGSI-WEB", "Développement web", 48)
        urb = matiere("MGSI-URB", "Urbanisation des SI", 36)

        # Comptes
        compte("admin", Utilisateur.Role.ADMIN, "Admin", "ENT")
        compte("scolarite", Utilisateur.Role.SCOLARITE, "Service", "Scolarité")
        profs = [compte(f"enseignant{i}", Utilisateur.Role.ENSEIGNANT, p, n) for i, (p, n) in enumerate(ENSEIGNANTS, 1)]
        etudiants = [
            compte(f"etudiant{i}", Utilisateur.Role.ETUDIANT, p, n, classe=classe,
                   groupe=g1 if i <= len(ETUDIANTS) // 2 else g2, cne=f"D13{i:07d}")
            for i, (p, n) in enumerate(ETUDIANTS, 1)
        ]

        for prof, mat in [(profs[0], gp), (profs[1], bd), (profs[2], web), (profs[0], urb)]:
            Enseignement.objects.create(enseignant=prof, matiere=mat, classe=classe)

        # Emploi du temps hebdomadaire (chaque séance passe par la détection de conflits)
        J = Seance.Jour
        creneaux = [
            (J.LUNDI, 8, 30, gp, profs[0], amphi, Seance.Type.COURS, None),
            (J.LUNDI, 10, 30, bd, profs[1], amphi, Seance.Type.COURS, None),
            (J.LUNDI, 14, 30, bd, profs[1], labo, Seance.Type.TP, g1),
            (J.LUNDI, 14, 30, gp, profs[0], s101, Seance.Type.TD, g2),
            (J.MARDI, 8, 30, web, profs[2], amphi, Seance.Type.COURS, None),
            (J.MARDI, 10, 30, web, profs[2], labo, Seance.Type.TP, g2),
            (J.MARDI, 10, 30, urb, profs[0], s102, Seance.Type.TD, g1),
            (J.MERCREDI, 8, 30, urb, profs[0], amphi, Seance.Type.COURS, None),
            (J.JEUDI, 8, 30, web, profs[2], labo, Seance.Type.TP, g1),
            (J.JEUDI, 10, 30, bd, profs[1], labo, Seance.Type.TP, g2),
            (J.VENDREDI, 8, 30, gp, profs[0], s101, Seance.Type.TD, g1),
            (J.VENDREDI, 10, 30, bd, profs[1], s101, Seance.Type.TD, None),
        ]
        seances = []
        for jour, h, m, mat, prof, salle, type_, groupe in creneaux:
            s = Seance(classe=classe, groupe=groupe, matiere=mat, enseignant=prof, salle=salle,
                       type=type_, jour=jour, heure_debut=time(h, m), heure_fin=time(h + 2, m))
            s.full_clean()
            s.save()
            seances.append(s)

        # Calendrier : jours fériés nationaux, une annulation et un rattrapage
        aujourdhui = timezone.localdate()
        annee = int(classe.annee_universitaire[:4])
        JourNonTravaille.objects.create(nom="Fête de la Marche Verte", date_debut=date(annee, 11, 6), date_fin=date(annee, 11, 6))
        JourNonTravaille.objects.create(
            nom="Fête de l'Indépendance", date_debut=date(annee, 11, 18), date_fin=date(annee, 11, 18)
        )
        JourNonTravaille.objects.create(nom="Nouvel An", date_debut=date(annee + 1, 1, 1), date_fin=date(annee + 1, 1, 1))

        cours_urbanisation = seances[7]  # mercredi 8h30, toute la classe
        prochain_mercredi = aujourdhui + timedelta(days=(3 - aujourdhui.isoweekday()) % 7 or 7)
        annulation = AnnulationSeance(seance=cours_urbanisation, date=prochain_mercredi, motif="Enseignant en mission")
        annulation.full_clean()
        annulation.save()
        annulation.notifier()
        prochain_samedi = aujourdhui + timedelta(days=(6 - aujourdhui.isoweekday()) % 7 or 7)
        rattrapage = Seance(classe=classe, matiere=urb, enseignant=profs[0], salle=amphi, type=Seance.Type.COURS,
                            date_unique=prochain_samedi, heure_debut=time(8, 30), heure_fin=time(10, 30))
        rattrapage.full_clean()
        rattrapage.save()

        # Historique d'appels depuis la rentrée : absences et retards tirés au hasard (graine fixe)
        hasard = random.Random(2026)
        absenteiste, matiere_sensible = etudiants[6], web
        rentree = classe.periode()[0]
        jour = rentree
        while jour < aujourdhui:
            for seance in seances:
                if seance.empechement(jour):
                    continue
                for etudiant in seance.public():
                    tirage = hasard.random()
                    if etudiant == absenteiste and seance.matiere == matiere_sensible:
                        nature = Absence.Nature.ABSENCE if tirage < 0.7 else None
                    elif tirage < 0.05:
                        nature = Absence.Nature.ABSENCE
                    elif tirage < 0.08:
                        nature = Absence.Nature.RETARD
                    else:
                        nature = None
                    if nature:
                        Absence.objects.create(etudiant=etudiant, seance=seance, date=jour, nature=nature,
                                               saisie_par=seance.enseignant)
            jour += timedelta(days=1)

        # Justifications : une partie acceptée, une refusée, une en attente
        scolarite = Utilisateur.objects.get(username="scolarite")
        absences = list(Absence.objects.filter(nature=Absence.Nature.ABSENCE).exclude(etudiant=absenteiste).order_by("date"))
        for i, absence in enumerate(absences[: max(3, len(absences) // 2)]):
            motif = hasard.choice(["Rendez-vous médical.", "Certificat médical.", "Convocation administrative."])
            justif = Justification(absence=absence, motif=motif)
            justif.piece_jointe.save(f"justificatif_{absence.pk}.pdf", ContentFile(b"%PDF-1.4\n% document fictif\n"), save=False)
            justif.save()
            if i == 0:
                justif.traiter(False, scolarite, "Le certificat est illisible : merci de déposer un scan net.")
            elif i < len(absences) // 2 - 1:
                justif.traiter(True, scolarite)
            # la dernière reste en attente pour la démonstration ; dates réalistes pour les statistiques
            depot = timezone.make_aware(datetime.combine(absence.date, time(18)))
            Justification.objects.filter(pk=justif.pk).update(
                date_depot=depot,
                date_traitement=depot + timedelta(days=1 + i % 3) if justif.date_traitement else None,
            )

        for etudiant in etudiants:
            AlerteAbsence.verifier(etudiant)

        # Demandes de documents : une en attente, une attestation déjà délivrée
        DemandeDocument.objects.create(
            etudiant=etudiants[1],
            type_document=DemandeDocument.TypeDocument.ATTESTATION_SCOLARITE,
            motif="Dossier de bourse",
        )
        delivree = DemandeDocument.objects.create(
            etudiant=etudiants[2], type_document=DemandeDocument.TypeDocument.ATTESTATION_SCOLARITE, motif="Stage d'été"
        )
        delivree.changer_statut(DemandeDocument.Statut.ACCEPTEE, scolarite)
        delivree.document = generer_attestation(delivree)
        delivree.changer_statut(DemandeDocument.Statut.PRETE, scolarite)
        DemandeDocument.objects.filter(pk=delivree.pk).update(date_demande=timezone.now() - timedelta(days=2))

        # Supports pédagogiques (fichiers PDF fictifs)
        supports = [
            (gp, profs[0], Ressource.Type.COURS, "Chapitre 1 – Introduction à Scrum", "scrum_chapitre1.pdf"),
            (gp, profs[0], Ressource.Type.TD, "TD 1 – Rédiger des user stories", "td1_user_stories.pdf"),
            (bd, profs[1], Ressource.Type.COURS, "Chapitre 1 – Normalisation", "bd_normalisation.pdf"),
            (bd, profs[1], Ressource.Type.TP, "TP 1 – Requêtes SQL avancées", "tp1_sql.pdf"),
            (web, profs[2], Ressource.Type.COURS, "Introduction à Django", "intro_django.pdf"),
        ]
        for mat, prof, type_, titre, fichier in supports:
            r = Ressource(matiere=mat, deposee_par=prof, type=type_, titre=titre)
            r.fichier.save(fichier, ContentFile(b"%PDF-1.4\n% support fictif\n"), save=False)
            r.save()

        # Annonces, examens et devoirs (dates calculées à partir d'aujourd'hui, jamais un dimanche)
        def jour_ouvre(dans_jours):
            jour = aujourdhui + timedelta(days=dans_jours)
            return jour + timedelta(days=1) if jour.isoweekday() == 7 else jour

        Annonce.objects.create(
            titre="Calendrier des examens du semestre", importante=True, auteur=scolarite,
            contenu="Les dates des contrôles et des examens de votre classe sont publiées dans « Examens et rendus ».\n"
                    "Un rappel vous sera envoyé deux jours avant chaque épreuve.",
        ).notifier()
        Annonce.objects.create(
            titre="Réunion d'information sur les stages de fin d'année", filiere=mgsi, auteur=scolarite,
            contenu="Présentation des offres de stage et des conventions, jeudi à 16 h en Amphi A.",
        )
        Annonce.objects.create(
            titre="TP de bases de données : apportez vos ordinateurs", classe=classe, auteur=profs[1],
            contenu="Installez PostgreSQL avant la séance (la procédure est dans les supports du cours).",
        )
        # Contrôle après les cours (16 h 45), examen et soutenance des samedis sans séance
        Examen.objects.create(
            classe=classe, matiere=web, type=Examen.Type.CONTROLE, titre="Contrôle continu – Django", date=jour_ouvre(4),
            heure_debut=time(16, 45), heure_fin=time(18, 0), salle=labo, cree_par=profs[2],
        )
        Examen.objects.create(
            classe=classe, matiere=bd, type=Examen.Type.EXAMEN, date=prochain_samedi + timedelta(weeks=1),
            heure_debut=time(9), heure_fin=time(11), salle=amphi,
            consignes="Documents non autorisés. Calculatrice interdite.", cree_par=scolarite,
        )
        Examen.objects.create(
            classe=classe, groupe=g1, matiere=gp, type=Examen.Type.SOUTENANCE, titre="Soutenance du projet Scrum",
            date=prochain_samedi + timedelta(weeks=2), heure_debut=time(9), salle=s101, cree_par=profs[0],
        )
        maintenant = timezone.now()
        Devoir.objects.create(
            classe=classe, matiere=bd, enseignant=profs[1], titre="TP 2 – Index et plans d'exécution",
            consignes="Créez les index demandés, comparez les plans d'exécution avant et après, "
                      "et rendez votre script SQL commenté.",
            date_limite=maintenant + timedelta(days=3, hours=2),
        )
        Devoir.objects.create(
            classe=classe, groupe=g2, matiere=web, enseignant=profs[2], titre="Mini-projet Django", accepte_retard=True,
            consignes="Application de gestion de bibliothèque : modèles, vues et gabarits. Rendez une archive ZIP du projet.",
            date_limite=maintenant + timedelta(days=9),
        )
        termine = Devoir.objects.create(
            classe=classe, matiere=gp, enseignant=profs[0], titre="Rédiger les user stories du projet",
            consignes="Au moins dix user stories au format « En tant que… je veux… afin de… », avec critères d'acceptation.",
            date_limite=maintenant - timedelta(days=5),
        )
        for etudiant in etudiants[:7]:
            depot = termine.date_limite - timedelta(hours=hasard.randint(2, 48))
            rendu = Rendu(devoir=termine, etudiant=etudiant, date_depot=depot)
            rendu.fichier.save(f"user_stories_{etudiant.username}.pdf", ContentFile(b"%PDF-1.4\n% rendu fictif\n"), save=False)
            rendu.save()

        self.stdout.write(self.style.SUCCESS(
            f"Données de démonstration créées : 1 classe, {len(etudiants)} étudiants, "
            f"{len(profs)} enseignants, {len(seances)} séances + 1 rattrapage, {len(supports)} ressources, "
            f"{Absence.objects.count()} absences et retards, {AlerteAbsence.objects.count()} alertes, "
            f"{Annonce.objects.count()} annonces, {Examen.objects.count()} examens, {Devoir.objects.count()} devoirs.\n"
            "Comptes : admin, scolarite, enseignant1 à enseignant3, etudiant1 à etudiant10 "
            "(mot de passe : celui du README, ou celui passé avec --mot-de-passe)."
        ))
        if options["mot_de_passe_aleatoire"]:
            self.stdout.write(self.style.WARNING(
                f"Mot de passe des comptes de démonstration : {mot_de_passe}\n"
                "Notez-le maintenant : il n'est enregistré nulle part en clair et ne sera plus affiché."
            ))
