import base64
import csv
import io
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce, TruncWeek
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone

from absences.models import Absence, AlerteAbsence, Justification
from annonces.models import Annonce
from documents.models import DemandeDocument
from emplois.models import JourNonTravaille, Seance
from emplois.views import planning, seances_de
from evaluations.models import envoyer_rappels
from evaluations.views import echeances
from ressources.models import Ressource
from structure.models import Classe, Filiere

from .forms import ChangementMotDePasseForm, ImportEtudiantsForm
from .importation import importer
from .models import Utilisateur
from .permissions import role_requis
from .templatetags.ent import heures as format_heures


@login_required
def tableau_de_bord(request):
    """Page d'accueil après connexion, adaptée au rôle de l'utilisateur (BF01).

    Indicateurs : (libellé, valeur, icône Bootstrap Icons, couleur de la pastille).
    """
    user = request.user
    aujourdhui = timezone.localdate()
    contexte = {
        "notifications": user.notifications.all()[:5],
        "fermeture": JourNonTravaille.couvrant(aujourdhui),
        "annonces": Annonce.visibles_par(user)[:3],
    }
    # Pas de tâche planifiée sur l'hébergement gratuit : les rappels partent à l'ouverture des tableaux de bord.
    envoyer_rappels()
    if user.est_etudiant or user.est_enseignant:
        contexte["a_venir"] = echeances(user, aujourdhui, jusqua=aujourdhui + timedelta(days=14))[:5]
        jours = planning(seances_de(user), aujourdhui, aujourdhui)
        contexte["seances_du_jour"] = jours[0]["seances"] if jours else []

    if user.est_admin:
        contexte["stats"] = [
            ("Filières", Filiere.objects.count(), "diagram-3", "primaire"),
            ("Classes", Classe.objects.count(), "people", "turquoise"),
            ("Étudiants", Utilisateur.objects.filter(role=Utilisateur.Role.ETUDIANT).count(), "mortarboard", "violet"),
            ("Enseignants", Utilisateur.objects.filter(role=Utilisateur.Role.ENSEIGNANT).count(), "person-workspace", "accent"),
            ("Séances planifiées", Seance.objects.count(), "calendar-week", "primaire"),
            (
                "Alertes critiques",
                AlerteAbsence.objects.filter(niveau=AlerteAbsence.Niveau.CRITIQUE).count(),
                "exclamation-triangle",
                "danger",
            ),
        ]
    elif user.est_scolarite:
        contexte["stats"] = [
            (
                "Demandes en attente",
                DemandeDocument.objects.filter(statut=DemandeDocument.Statut.EN_ATTENTE).count(),
                "file-earmark-text",
                "primaire",
            ),
            (
                "Justifications à traiter",
                Justification.objects.filter(statut=Justification.Statut.EN_ATTENTE).count(),
                "patch-check",
                "accent",
            ),
            (
                "Étudiants en alerte",
                AlerteAbsence.objects.values("etudiant").distinct().count(),
                "exclamation-triangle",
                "danger",
            ),
        ]
    elif user.est_enseignant:
        contexte["stats"] = [
            ("Séances par semaine", user.seances.filter(date_unique__isnull=True).count(), "calendar-week", "primaire"),
            ("Classes", user.seances.values("classe").distinct().count(), "people", "turquoise"),
            ("Ressources déposées", user.ressources_deposees.count(), "journal-arrow-up", "violet"),
            ("Étudiants en alerte", Absence.etudiants_en_alerte(user), "exclamation-triangle", "danger"),
        ]
    elif user.est_etudiant:
        heures = Absence.heures_par_matiere(user)
        contexte["stats"] = [
            ("Heures d'absence", format_heures(sum(l["total"] for l in heures)), "clock-history", "primaire"),
            ("Dont non justifiées", format_heures(sum(l["non_justifiees"] for l in heures)), "exclamation-circle", "danger"),
            ("Retards", sum(l["retards"] for l in heures), "hourglass-split", "accent"),
            (
                "Demandes en cours",
                user.demandes_documents.filter(
                    statut__in=[DemandeDocument.Statut.EN_ATTENTE, DemandeDocument.Statut.ACCEPTEE]
                ).count(),
                "file-earmark-text",
                "turquoise",
            ),
            (
                "Nouvelles ressources (7 jours)",
                Ressource.visibles_par(user).filter(date_depot__gte=timezone.now() - timedelta(days=7)).count(),
                "journal-plus",
                "violet",
            ),
        ]

    return render(request, "comptes/tableau_de_bord.html", contexte)


@login_required
def mon_compte(request):
    return render(request, "comptes/mon_compte.html")


class ChangerMotDePasse(SuccessMessageMixin, PasswordChangeView):
    """Changement de mot de passe par l'utilisateur lui-même (la session reste ouverte)."""

    form_class = ChangementMotDePasseForm
    template_name = "comptes/mot_de_passe.html"
    success_url = reverse_lazy("mon_compte")
    success_message = "Votre mot de passe a été modifié."

    def form_valid(self, form):
        reponse = super().form_valid(form)
        if self.request.user.doit_changer_mot_de_passe:
            self.request.user.doit_changer_mot_de_passe = False
            self.request.user.save(update_fields=["doit_changer_mot_de_passe"])
        return reponse


def csv_identifiants(comptes):
    """Fichier CSV (encodé pour un lien de téléchargement) des identifiants provisoires créés."""
    tampon = io.StringIO()
    tampon.write("\ufeff")
    ecrivain = csv.writer(tampon, delimiter=";")
    ecrivain.writerow(["Nom", "Prénom", "CNE", "Groupe", "Identifiant", "Mot de passe provisoire"])
    for etudiant, mot_de_passe in comptes:
        groupe = etudiant.groupe.nom if etudiant.groupe else ""
        ecrivain.writerow([etudiant.last_name, etudiant.first_name, etudiant.cne, groupe, etudiant.username, mot_de_passe])
    return base64.b64encode(tampon.getvalue().encode("utf-8")).decode()


@role_requis("ADMIN", "SCOLARITE")
def importer_etudiants(request):
    """Création des comptes d'une promotion à partir d'un fichier CSV (tout ou rien)."""
    form = ImportEtudiantsForm(request.POST or None, request.FILES or None)
    contexte = {"form": form}
    if request.method == "POST" and form.is_valid():
        classe = form.cleaned_data["classe"]
        try:
            resultat = importer(form.cleaned_data["fichier"], classe)
        except ValidationError as erreur:
            form.add_error("fichier", erreur)
        else:
            if resultat.erreurs:
                contexte["erreurs"] = resultat.erreurs
            else:
                messages.success(request, f"{len(resultat.comptes)} compte(s) étudiant créé(s) dans la classe {classe}.")
                # Les mots de passe provisoires ne sont affichés qu'une fois et ne sont stockés nulle part en clair.
                contexte.update(comptes=resultat.comptes, csv_base64=csv_identifiants(resultat.comptes), classe=classe)
    return render(request, "comptes/importer_etudiants.html", contexte)


@role_requis("ADMIN", "SCOLARITE")
def modele_import(request):
    contenu = "\ufeffnom;prenom;cne;email;groupe\nAmrani;Yassine;D130000001;yassine.amrani@exemple.ma;G1\n"
    reponse = HttpResponse(contenu, content_type="text/csv; charset=utf-8")
    reponse["Content-Disposition"] = 'attachment; filename="modele_import_etudiants.csv"'
    return reponse


def nombre_et_delai_moyen(traites, debut, fin):
    """Nombre d'objets traités et délai moyen (en jours) entre deux dates, ou None s'il n'y en a pas."""
    resultat = traites.aggregate(
        nombre=Count("pk"), delai=Avg(ExpressionWrapper(F(fin) - F(debut), output_field=DurationField()))
    )
    delai = resultat["delai"]
    return resultat["nombre"], (delai.total_seconds() / 86400 if delai is not None else None)


def somme_heures(**filtre):
    """Somme des heures d'absence (0 s'il n'y en a pas), éventuellement restreinte par un filtre."""
    return Coalesce(Sum("duree_heures", filter=Q(**filtre) if filtre else None), 0.0)


@role_requis("ADMIN", "SCOLARITE")
def statistiques(request):
    """Tableau de bord chiffré : absences par matière et par semaine, délais de traitement.

    Les totaux sont calculés par la base (quelques requêtes, quel que soit le nombre d'absences).
    """
    classes = Classe.objects.all()
    classe_id = request.GET.get("classe", "")
    classe = classes.filter(pk=classe_id).first() if classe_id.isdigit() else None

    absences = Absence.objects.filter(nature=Absence.Nature.ABSENCE).order_by()
    demandes = DemandeDocument.objects.exclude(date_traitement=None)
    justifications = Justification.objects.exclude(date_traitement=None)
    if classe:
        absences = absences.filter(seance__classe=classe)
        demandes = demandes.filter(etudiant__classe=classe)
        justifications = justifications.filter(absence__seance__classe=classe)

    # Heures d'absence par matière (justifiées / non justifiées)
    par_matiere = list(
        absences.values(matiere=F("seance__matiere__nom"))
        .annotate(
            justifiees=somme_heures(statut=Absence.Statut.JUSTIFIEE),
            non_justifiees=somme_heures(statut=Absence.Statut.NON_JUSTIFIEE),
        )
        .order_by((F("justifiees") + F("non_justifiees")).desc(), "matiere")
    )

    # Heures d'absence par semaine, sur les 12 dernières semaines de l'année universitaire
    lundi_courant = timezone.localdate() - timedelta(days=timezone.localdate().isoweekday() - 1)
    semaines = [lundi_courant - timedelta(weeks=n) for n in range(11, -1, -1)]
    # Pas de semaines avant la rentrée (elles seraient vides par construction)
    rentrees = [c.periode()[0] for c in ([classe] if classe else classes)]
    if rentrees:
        semaines = [s for s in semaines if s + timedelta(days=6) >= min(rentrees)] or semaines[-1:]
    heures_semaine = dict(
        absences.filter(date__range=(semaines[0], semaines[-1] + timedelta(days=6)))
        .annotate(semaine=TruncWeek("date"))
        .values_list("semaine")
        .annotate(heures=somme_heures())
    )
    par_semaine = [
        {"semaine": s.isoformat(), "libelle": f"{s:%d/%m}", "heures": heures_semaine.get(s, 0.0)} for s in semaines
    ]

    totaux = absences.aggregate(total=somme_heures(), justifiees=somme_heures(statut=Absence.Statut.JUSTIFIEE))
    demandes_traitees, delai_demandes = nombre_et_delai_moyen(demandes, "date_demande", "date_traitement")
    justifications_traitees, delai_justifications = nombre_et_delai_moyen(justifications, "date_depot", "date_traitement")
    indicateurs = {
        "total": totaux["total"],
        "taux_justification": 100 * totaux["justifiees"] / totaux["total"] if totaux["total"] else None,
        "delai_demandes": delai_demandes,
        "delai_justifications": delai_justifications,
        "demandes_traitees": demandes_traitees,
        "justifications_traitees": justifications_traitees,
    }
    return render(
        request,
        "comptes/statistiques.html",
        {
            "classes": classes,
            "classe": classe,
            "indicateurs": indicateurs,
            "par_matiere": par_matiere,
            "par_semaine": par_semaine,
        },
    )
