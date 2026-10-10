import base64
import csv
import io
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone

from absences.models import Absence, AlerteAbsence, Justification
from documents.models import DemandeDocument
from emplois.models import JourNonTravaille, Seance
from emplois.views import planning, seances_de
from ressources.models import Ressource
from structure.models import Classe, Filiere

from .forms import ChangementMotDePasseForm, ImportEtudiantsForm
from .importation import importer
from .permissions import role_requis
from .models import Utilisateur
from .templatetags.ent import heures as format_heures


@login_required
def tableau_de_bord(request):
    """Page d'accueil après connexion, adaptée au rôle de l'utilisateur (BF01)."""
    user = request.user
    aujourdhui = timezone.localdate()
    contexte = {
        "notifications": user.notifications.all()[:5],
        "fermeture": JourNonTravaille.couvrant(aujourdhui),
    }
    if user.est_etudiant or user.est_enseignant:
        jours = planning(seances_de(user), aujourdhui, aujourdhui)
        contexte["seances_du_jour"] = jours[0]["seances"] if jours else []

    if user.est_admin:
        contexte["stats"] = [
            ("Filières", Filiere.objects.count()),
            ("Classes", Classe.objects.count()),
            ("Étudiants", Utilisateur.objects.filter(role=Utilisateur.Role.ETUDIANT).count()),
            ("Enseignants", Utilisateur.objects.filter(role=Utilisateur.Role.ENSEIGNANT).count()),
            ("Séances planifiées", Seance.objects.count()),
            ("Alertes critiques", AlerteAbsence.objects.filter(niveau=AlerteAbsence.Niveau.CRITIQUE).count()),
        ]
    elif user.est_scolarite:
        contexte["stats"] = [
            ("Demandes en attente", DemandeDocument.objects.filter(statut=DemandeDocument.Statut.EN_ATTENTE).count()),
            ("Justifications à traiter", Justification.objects.filter(statut=Justification.Statut.EN_ATTENTE).count()),
            (
                "Étudiants en alerte",
                AlerteAbsence.objects.values("etudiant").distinct().count(),
            ),
        ]
    elif user.est_enseignant:
        contexte["stats"] = [
            ("Séances par semaine", user.seances.filter(date_unique__isnull=True).count()),
            ("Classes", user.seances.values("classe").distinct().count()),
            ("Ressources déposées", user.ressources_deposees.count()),
        ]
    elif user.est_etudiant:
        heures = Absence.heures_par_matiere(user)
        contexte["stats"] = [
            ("Heures d'absence", format_heures(sum(l["total"] for l in heures))),
            ("Dont non justifiées", format_heures(sum(l["non_justifiees"] for l in heures))),
            ("Retards", sum(l["retards"] for l in heures)),
            (
                "Demandes en cours",
                user.demandes_documents.filter(
                    statut__in=[DemandeDocument.Statut.EN_ATTENTE, DemandeDocument.Statut.ACCEPTEE]
                ).count(),
            ),
            (
                "Nouvelles ressources (7 jours)",
                Ressource.visibles_par(user).filter(date_depot__gte=timezone.now() - timedelta(days=7)).count(),
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


def delai_moyen_jours(objets, debut, fin):
    """Délai moyen (en jours) entre deux dates d'une liste d'objets traités, ou None."""
    delais = [(getattr(o, fin) - getattr(o, debut)).total_seconds() / 86400 for o in objets if getattr(o, fin)]
    return sum(delais) / len(delais) if delais else None


@role_requis("ADMIN", "SCOLARITE")
def statistiques(request):
    """Tableau de bord chiffré : absences par matière et par semaine, délais de traitement."""
    classes = Classe.objects.all()
    classe_id = request.GET.get("classe", "")
    classe = classes.filter(pk=classe_id).first() if classe_id.isdigit() else None

    absences = Absence.objects.filter(nature=Absence.Nature.ABSENCE).select_related("seance__matiere")
    demandes = DemandeDocument.objects.exclude(date_traitement=None)
    justifications = Justification.objects.exclude(date_traitement=None)
    if classe:
        absences = absences.filter(seance__classe=classe)
        demandes = demandes.filter(etudiant__classe=classe)
        justifications = justifications.filter(absence__seance__classe=classe)
    absences = list(absences)

    # Heures d'absence par matière (justifiées / non justifiées)
    par_matiere = {}
    for a in absences:
        ligne = par_matiere.setdefault(a.seance.matiere.nom, {"matiere": a.seance.matiere.nom, "justifiees": 0.0, "non_justifiees": 0.0})
        ligne["justifiees" if a.statut == Absence.Statut.JUSTIFIEE else "non_justifiees"] += a.duree_heures
    par_matiere = sorted(par_matiere.values(), key=lambda l: -(l["justifiees"] + l["non_justifiees"]))

    # Heures d'absence par semaine, sur les 12 dernières semaines de l'année universitaire
    lundi_courant = timezone.localdate() - timedelta(days=timezone.localdate().isoweekday() - 1)
    semaines = [lundi_courant - timedelta(weeks=n) for n in range(11, -1, -1)]
    # Pas de semaines avant la rentrée (elles seraient vides par construction)
    rentrees = [c.periode()[0] for c in ([classe] if classe else classes)]
    if rentrees:
        semaines = [s for s in semaines if s + timedelta(days=6) >= min(rentrees)] or semaines[-1:]
    heures_semaine = {s: 0.0 for s in semaines}
    for a in absences:
        lundi = a.date - timedelta(days=a.date.isoweekday() - 1)
        if lundi in heures_semaine:
            heures_semaine[lundi] += a.duree_heures
    par_semaine = [{"semaine": s.isoformat(), "libelle": f"{s:%d/%m}", "heures": h} for s, h in heures_semaine.items()]

    total = sum(a.duree_heures for a in absences)
    justifiees = sum(a.duree_heures for a in absences if a.statut == Absence.Statut.JUSTIFIEE)
    indicateurs = {
        "total": total,
        "taux_justification": 100 * justifiees / total if total else None,
        "delai_demandes": delai_moyen_jours(demandes, "date_demande", "date_traitement"),
        "delai_justifications": delai_moyen_jours(justifications, "date_depot", "date_traitement"),
        "demandes_traitees": demandes.count(),
        "justifications_traitees": justifications.count(),
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
