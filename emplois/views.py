import secrets
from collections import defaultdict
from datetime import date as Date
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from comptes.permissions import role_requis
from evaluations.models import Examen
from evaluations.views import examens_visibles
from structure.models import Classe

from .models import AnnulationSeance, JourNonTravaille, Seance


def seances_de(user):
    """Séances (hebdomadaires et rattrapages) qui concernent l'utilisateur (étudiant ou enseignant)."""
    seances = Seance.objects.select_related("matiere", "enseignant", "salle", "groupe", "classe__filiere", "classe__niveau")
    if user.est_enseignant:
        return seances.filter(enseignant=user)
    if user.est_etudiant and user.classe_id:
        filtre = Q(groupe__isnull=True)
        if user.groupe_id:
            filtre |= Q(groupe_id=user.groupe_id)
        return seances.filter(filtre, classe_id=user.classe_id)
    return seances.none()


def grille(seances):
    """Regroupe les séances hebdomadaires par jour de la semaine."""
    return [(libelle, [s for s in seances if s.jour == jour and not s.date_unique]) for jour, libelle in Seance.Jour.choices]


def lundi_de(date):
    return date - timedelta(days=date.isoweekday() - 1)


def planning(seances, du, au):
    """Séances qui ont réellement lieu entre deux dates, jour par jour.

    Renvoie [{"date", "fermeture", "seances": [(seance, annulation ou None), …]}, …]
    (du lundi au samedi), en tenant compte des rattrapages, annulations et jours non travaillés.
    """
    seances = list(seances.filter(Q(date_unique__isnull=True) | Q(date_unique__range=(du, au))))
    annulations = {
        (a.seance_id, a.date): a for a in AnnulationSeance.objects.filter(seance__in=seances, date__range=(du, au))
    }
    fermetures = list(JourNonTravaille.objects.filter(date_debut__lte=au, date_fin__gte=du))

    jours = []
    jour = du
    while jour <= au:
        if jour.isoweekday() != 7:
            fermeture = next((f for f in fermetures if f.date_debut <= jour <= f.date_fin), None)
            du_jour = [
                (s, annulations.get((s.pk, jour)))
                for s in seances
                if (s.date_unique == jour) or (not s.date_unique and s.jour == jour.isoweekday())
            ]
            du_jour.sort(key=lambda paire: paire[0].heure_debut)
            jours.append({"date": jour, "fermeture": fermeture, "seances": [] if fermeture else du_jour})
        jour += timedelta(days=1)
    return jours


def ajouter_examens(jours, examens):
    """Ajoute à chaque jour ses examens (« examens ») et ses créneaux triés par heure (« creneaux ») :
    [("seance", séance, annulation ou None) ou ("examen", examen, None), …]."""
    par_jour = defaultdict(list)
    for examen in examens.select_related("matiere", "salle", "groupe"):
        par_jour[examen.date].append(examen)
    for jour in jours:
        jour["examens"] = [] if jour["fermeture"] else par_jour.get(jour["date"], [])
        creneaux = [(s.heure_debut, "seance", s, annulation) for s, annulation in jour["seances"]]
        creneaux += [(e.heure_debut, "examen", e, None) for e in jour["examens"]]
        jour["creneaux"] = [c[1:] for c in sorted(creneaux, key=lambda c: c[0])]
    return jours


def semaine_demandee(request):
    try:
        return lundi_de(Date.fromisoformat(request.GET.get("semaine", "")))
    except ValueError:
        return lundi_de(timezone.localdate())


def contexte_semaine(lundi):
    return {
        "lundi": lundi,
        "samedi": lundi + timedelta(days=5),
        "semaine_precedente": lundi - timedelta(days=7),
        "semaine_suivante": lundi + timedelta(days=7),
        "aujourdhui": timezone.localdate(),
    }


@login_required
def mon_emploi_du_temps(request):
    """Emploi du temps de la semaine de l'étudiant ou de l'enseignant connecté (BF15)."""
    user = request.user
    if user.est_etudiant:
        titre = f"Emploi du temps – {user.classe}" if user.classe_id else "Emploi du temps"
        if user.groupe_id:
            titre += f" · {user.groupe.nom}"
    else:
        titre = "Mon emploi du temps"
    lundi = semaine_demandee(request)
    samedi = lundi + timedelta(days=5)
    jours = planning(seances_de(user), lundi, samedi)
    ajouter_examens(jours, examens_visibles(user).filter(date__range=(lundi, samedi)))
    lien_calendrier = None
    if user.jeton_calendrier:
        lien_calendrier = request.build_absolute_uri(reverse("emplois:flux_ics", args=[user.jeton_calendrier]))
    return render(
        request,
        "emplois/emploi_du_temps.html",
        {
            "titre": titre,
            "jours": jours,
            "sans_classe": user.est_etudiant and not user.classe_id,
            "abonnement": user.est_etudiant or user.est_enseignant,
            "lien_calendrier": lien_calendrier,
            **contexte_semaine(lundi),
        },
    )


@login_required
@require_POST
def abonnement(request):
    """Crée (ou remplace) l'adresse secrète du flux iCalendar : l'ancienne cesse de fonctionner."""
    deja = bool(request.user.jeton_calendrier)
    request.user.jeton_calendrier = secrets.token_urlsafe(32)
    request.user.save(update_fields=["jeton_calendrier"])
    if deja:
        messages.success(request, "Nouveau lien créé : l'ancien ne fonctionne plus. Abonnez à nouveau votre agenda.")
    else:
        messages.success(request, "Lien d'abonnement créé : ajoutez-le à votre agenda.")
    return redirect("emplois:mon_emploi_du_temps")


def flux_ics(request, jeton):
    """Flux iCalendar, sans connexion (les applications d'agenda ne peuvent pas s'identifier) :
    l'adresse secrète tient lieu d'identification."""
    from comptes.models import Utilisateur

    from .ical import calendrier_ics

    utilisateur = get_object_or_404(Utilisateur, jeton_calendrier=jeton, is_active=True)
    contenu = calendrier_ics(utilisateur, timezone.localdate(), request.build_absolute_uri)
    reponse = HttpResponse(contenu, content_type="text/calendar; charset=utf-8")
    reponse["Content-Disposition"] = 'inline; filename="emploi_du_temps_ensiasd.ics"'
    reponse["X-Robots-Tag"] = "noindex"
    return reponse


@role_requis("ADMIN", "SCOLARITE")
def emploi_du_temps_classe(request):
    """Consultation de l'emploi du temps d'une classe par l'administration (BF13)."""
    classes = Classe.objects.all()
    classe_id = request.GET.get("classe", "")
    classe = get_object_or_404(classes, pk=classe_id) if classe_id.isdigit() else classes.first()
    lundi = semaine_demandee(request)
    jours = []
    if classe:
        seances = Seance.objects.filter(classe=classe).select_related("matiere", "enseignant", "salle", "groupe")
        jours = planning(seances, lundi, lundi + timedelta(days=5))
        ajouter_examens(jours, Examen.objects.filter(classe=classe, date__range=(lundi, lundi + timedelta(days=5))))
    return render(
        request,
        "emplois/emploi_du_temps.html",
        {
            "titre": f"Emploi du temps – {classe}" if classe else "Emploi du temps",
            "jours": jours,
            "classes": classes,
            "classe_courante": classe,
            **contexte_semaine(lundi),
        },
    )
