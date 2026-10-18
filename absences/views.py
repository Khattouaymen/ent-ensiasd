import csv
from collections import defaultdict
from datetime import date as Date
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header

from comptes.permissions import role_requis
from config.formulaires import paginer, telecharger
from emplois.models import Seance
from emplois.views import grille
from notifications.models import Notification
from structure.models import Classe

from .forms import JustificationForm
from .models import Absence, AlerteAbsence, Justification

# --- Saisie des absences et retards (enseignant, administrateur) -------------------------------

PRESENT, ABSENT, RETARD = "present", "absent", "retard"


def seances_pour_appel(user):
    seances = Seance.objects.select_related("matiere", "salle", "groupe", "classe__filiere", "classe__niveau")
    return seances if user.est_admin else seances.filter(enseignant=user)


@role_requis("ENSEIGNANT", "ADMIN")
def choisir_seance(request):
    seances = list(seances_pour_appel(request.user))
    il_y_a_un_mois = timezone.localdate() - timedelta(days=30)
    rattrapages = sorted(
        (s for s in seances if s.date_unique and s.date_unique >= il_y_a_un_mois), key=lambda s: s.date_unique
    )
    return render(
        request,
        "absences/choisir_seance.html",
        {"jours": grille(seances), "rattrapages": rattrapages, "nb_seances": len(seances)},
    )


def lire_date(texte, seance):
    """Convertit la date choisie pour l'appel ; renvoie (date, message d'erreur)."""
    try:
        date = Date.fromisoformat(texte)
    except (TypeError, ValueError):
        return None, "Date invalide."
    if date > timezone.localdate():
        return None, "Impossible de faire l'appel pour une date future."
    return date, seance.empechement(date)


def absences_existantes(seance, date):
    """Absences et retards déjà saisis pour cette séance à cette date, par étudiant."""
    absences = Absence.objects.filter(seance=seance, date=date).select_related("seance").prefetch_related("justifications")
    return {a.etudiant_id: a for a in absences}


@transaction.atomic
def enregistrer_appel(seance, date, etudiants, choix, agent):
    """Enregistre l'appel ; renvoie le nombre d'absences justifiées laissées telles quelles.

    Tout se fait dans une transaction : en cas d'erreur, l'appel n'est pas enregistré à moitié,
    et deux envois simultanés (double clic) sont traités l'un après l'autre. Les écritures sont
    groupées : le nombre de requêtes ne dépend pas de l'effectif de la classe.
    """
    existantes = absences_existantes(seance, date)
    a_creer, a_modifier, a_supprimer, absents = [], [], [], []
    conservees = 0
    for etudiant in etudiants:
        choix_etudiant = choix.get(etudiant.pk, PRESENT)
        absence = existantes.get(etudiant.pk)
        if absence is not None and absence.justifications.all():
            # Une absence pour laquelle l'étudiant a déposé un justificatif n'est plus modifiée.
            if choix_etudiant != ABSENT:
                conservees += 1
            continue
        if choix_etudiant == PRESENT:
            if absence is not None:
                a_supprimer.append(absence.pk)
            continue
        nature = Absence.Nature.RETARD if choix_etudiant == RETARD else Absence.Nature.ABSENCE
        if absence is None:
            absence = Absence(etudiant=etudiant, seance=seance, date=date, nature=nature, saisie_par=agent)
            absence.calculer_duree()
            a_creer.append(absence)
        elif absence.nature != nature:
            absence.nature = nature
            absence.calculer_duree()
            a_modifier.append(absence)
        if nature == Absence.Nature.ABSENCE:
            absents.append(etudiant)

    Absence.objects.filter(pk__in=a_supprimer).delete()
    Absence.objects.bulk_update(a_modifier, ["nature", "duree_heures"])
    # ignore_conflicts : avec une base qui ne sérialise pas les transactions (PostgreSQL), un double
    # envoi peut encore tenter de créer une absence que le premier vient d'enregistrer.
    Absence.objects.bulk_create(a_creer, ignore_conflicts=True)
    AlerteAbsence.verifier_apres_appel(seance.matiere, absents)
    return conservees


@role_requis("ENSEIGNANT", "ADMIN")
def appel(request, seance_id):
    """Feuille d'appel d'une séance à une date donnée : présent, absent ou en retard (BF02)."""
    seance = get_object_or_404(seances_pour_appel(request.user), pk=seance_id)

    texte_date = request.POST.get("date") or request.GET.get("date")
    if texte_date:
        date, erreur = lire_date(texte_date, seance)
    else:
        date = seance.derniere_date()
        erreur = "Cette séance de rattrapage n'a pas encore eu lieu." if date > timezone.localdate() else seance.empechement(date)
    if date is None:
        messages.error(request, erreur)
        return redirect("absences:appel", seance_id=seance.pk)
    if erreur and request.method == "POST":
        messages.error(request, erreur)
        return redirect(f"{reverse('absences:appel', args=[seance.pk])}?date={date.isoformat()}")

    etudiants = list(seance.public().select_related("groupe"))

    if request.method == "POST":
        choix = {e.pk: request.POST.get(f"etudiant_{e.pk}", PRESENT) for e in etudiants}
        conservees = enregistrer_appel(seance, date, etudiants, choix, request.user)
        nb = Absence.objects.filter(seance=seance, date=date).aggregate(
            absents=Count("pk", filter=Q(nature=Absence.Nature.ABSENCE)),
            retards=Count("pk", filter=Q(nature=Absence.Nature.RETARD)),
        )
        messages.success(
            request, f"Appel du {date:%d/%m/%Y} enregistré : {nb['absents']} absent(s), {nb['retards']} retard(s)."
        )
        if conservees:
            messages.warning(request, f"{conservees} absence(s) déjà justifiée(s) par l'étudiant n'ont pas été modifiées.")
        return redirect(f"{reverse('absences:appel', args=[seance.pk])}?date={date.isoformat()}")

    existantes = absences_existantes(seance, date)
    lignes = []
    for etudiant in etudiants:
        absence = existantes.get(etudiant.pk)
        if absence is None:
            choix = PRESENT
        else:
            choix = RETARD if absence.est_retard else ABSENT
        lignes.append({"etudiant": etudiant, "choix": choix, "verrouillee": bool(absence and absence.justifications.all())})

    return render(
        request,
        "absences/appel.html",
        {"seance": seance, "date": date, "lignes": lignes, "erreur_date": erreur},
    )


# --- Espace étudiant -------------------------------------------------------------------------


@role_requis("ETUDIANT")
def mes_absences(request):
    """Total d'heures d'absence par matière (BF03), alertes et liste détaillée."""
    absences = request.user.absences.select_related("seance__matiere").prefetch_related("justifications")
    totaux = Absence.heures_par_matiere(request.user)
    return render(
        request,
        "absences/mes_absences.html",
        {
            "absences": absences,
            "totaux": totaux,
            "total": sum(l["total"] for l in totaux),
            "total_non_justifiees": sum(l["non_justifiees"] for l in totaux),
            "total_retards": sum(l["retards"] for l in totaux),
            "seuils": AlerteAbsence.seuils(),
        },
    )


@role_requis("ETUDIANT")
def justifier(request, absence_id):
    """Dépôt d'une justification avec pièce jointe (BF04), y compris après un refus."""
    absence = get_object_or_404(
        request.user.absences.select_related("seance__matiere").prefetch_related("justifications"), pk=absence_id
    )
    if not absence.peut_etre_justifiee:
        messages.info(request, "Cette absence a déjà une justification en cours ou acceptée.")
        return redirect("absences:mes_absences")

    precedente = absence.derniere_justification
    form = JustificationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        justification = form.save(commit=False)
        justification.absence = absence
        try:
            with transaction.atomic():
                justification.save()
        except IntegrityError:
            # Double envoi : une justification vient d'être enregistrée pour cette absence
            # (une seule peut être en attente). La pièce jointe du doublon est supprimée.
            justification.piece_jointe.delete(save=False)
            messages.info(request, "Cette absence a déjà une justification en cours ou acceptée.")
            return redirect("absences:mes_absences")
        Notification.envoyer_au_role(
            "SCOLARITE",
            f"Nouvelle justification d'absence : {request.user} ({absence.seance.matiere}, {absence.date:%d/%m/%Y}).",
            lien=reverse("absences:traiter_justification", args=[justification.pk]),
        )
        messages.success(request, "Votre justification a été envoyée au service de scolarité.")
        return redirect("absences:mes_absences")
    return render(request, "absences/justifier.html", {"form": form, "absence": absence, "precedente": precedente})


# --- Traitement des justifications (scolarité) ------------------------------------------------


@role_requis("SCOLARITE", "ADMIN")
def justifications(request):
    filtre = request.GET.get("statut", Justification.Statut.EN_ATTENTE)
    liste = Justification.objects.select_related(
        "absence__etudiant__classe__filiere", "absence__etudiant__classe__niveau", "absence__seance__matiere"
    )
    if filtre in Justification.Statut.values:
        liste = liste.filter(statut=filtre)
    if filtre == Justification.Statut.EN_ATTENTE:
        liste = liste.order_by("date_depot")
    recherche = request.GET.get("q", "").strip()
    if recherche:
        liste = liste.filter(
            Q(absence__etudiant__last_name__icontains=recherche)
            | Q(absence__etudiant__first_name__icontains=recherche)
            | Q(absence__etudiant__cne__icontains=recherche)
        )
    filtres = [*Justification.Statut.choices, ("toutes", "Toutes")]
    return render(
        request,
        "absences/justifications.html",
        {"page": paginer(request, liste), "filtre": filtre, "filtres": filtres},
    )


@role_requis("SCOLARITE", "ADMIN")
def traiter_justification(request, pk):
    """Validation ou refus d'une justification (BF05)."""
    justification = get_object_or_404(
        Justification.objects.select_related("absence__etudiant", "absence__seance__matiere", "traitee_par"), pk=pk
    )
    if request.method == "POST":
        decision = request.POST.get("decision")
        if decision not in ("accepter", "refuser"):
            messages.error(request, "Décision invalide.")
        else:
            try:
                justification.traiter(decision == "accepter", request.user, request.POST.get("commentaire", "").strip())
            except ValidationError as erreur:
                messages.error(request, erreur.messages[0])
            else:
                messages.success(
                    request, f"Justification {justification.get_statut_display().lower()}. L'étudiant a été notifié."
                )
                return redirect("absences:justifications")
    historique = justification.absence.justifications.exclude(pk=justification.pk)
    return render(
        request, "absences/traiter_justification.html", {"justification": justification, "historique": historique}
    )


@login_required
def piece_jointe(request, pk):
    """Pièce jointe d'une justification : réservée à l'étudiant concerné et au personnel administratif."""
    user = request.user
    justifications_visibles = Justification.objects.all()
    if not (user.est_scolarite or user.est_admin):
        justifications_visibles = justifications_visibles.filter(absence__etudiant=user)
    return telecharger(get_object_or_404(justifications_visibles, pk=pk).piece_jointe)


# --- Suivi par classe et export (administrateur, scolarité) -----------------------------------


def absences_de_la_classe(classe):
    dernieres_justifications = Prefetch("justifications", queryset=Justification.objects.order_by("-date_depot"))
    return (
        Absence.objects.filter(seance__classe=classe)
        .select_related("etudiant__groupe", "seance__matiere")
        .prefetch_related(dernieres_justifications)
        .order_by("etudiant__last_name", "etudiant__first_name", "date", "seance__heure_debut")
    )


@role_requis("SCOLARITE", "ADMIN")
def par_classe(request):
    """Récapitulatif des absences et retards des étudiants d'une classe, avec les alertes de seuil."""
    classes = Classe.objects.all()
    classe_id = request.GET.get("classe", "")
    classe = get_object_or_404(classes, pk=classe_id) if classe_id.isdigit() else classes.first()

    lignes = []
    if classe:
        cumul = defaultdict(lambda: {"total": 0.0, "non_justifiees": 0.0, "nombre": 0, "retards": 0})
        for absence in absences_de_la_classe(classe):
            c = cumul[absence.etudiant_id]
            if absence.est_retard:
                c["retards"] += 1
                continue
            c["nombre"] += 1
            c["total"] += absence.duree_heures
            if absence.statut == Absence.Statut.NON_JUSTIFIEE:
                c["non_justifiees"] += absence.duree_heures

        alertes = defaultdict(list)
        for alerte in AlerteAbsence.objects.filter(etudiant__classe=classe).select_related("matiere"):
            alertes[alerte.etudiant_id].append(alerte)
        for etudiant in classe.etudiants.filter(role="ETUDIANT").select_related("groupe"):
            critiques = [a for a in alertes[etudiant.pk] if a.niveau == AlerteAbsence.Niveau.CRITIQUE]
            avertissements = [
                a for a in alertes[etudiant.pk]
                if a.niveau == AlerteAbsence.Niveau.AVERTISSEMENT and a.matiere_id not in {c.matiere_id for c in critiques}
            ]
            lignes.append(
                {"etudiant": etudiant, **cumul[etudiant.pk], "critiques": critiques, "avertissements": avertissements}
            )
        lignes.sort(key=lambda l: (-len(l["critiques"]), -l["non_justifiees"], l["etudiant"].last_name))

    return render(request, "absences/par_classe.html", {"classes": classes, "classe": classe, "lignes": lignes})


@role_requis("SCOLARITE", "ADMIN")
def exporter(request, classe_id):
    """Export CSV (compatible Excel) des absences et retards d'une classe (US18)."""
    classe = get_object_or_404(Classe.objects.all(), pk=classe_id)
    reponse = HttpResponse(content_type="text/csv; charset=utf-8")
    nom = f"absences_{classe.filiere.code}_{classe.niveau}_{classe.annee_universitaire}".replace(" ", "_").replace("/", "-")
    # Encodage RFC 6266 : le nom de fichier garde ses accents dans tous les navigateurs
    reponse["Content-Disposition"] = content_disposition_header(True, f"{nom}.csv")
    reponse.write("\ufeff")  # BOM : Excel reconnaît l'UTF-8 et les accents

    ecrivain = csv.writer(reponse, delimiter=";")
    ecrivain.writerow(
        ["Nom", "Prénom", "CNE", "Groupe", "Matière", "Type", "Date", "Créneau", "Nature", "Durée (h)", "Statut", "Justification"]
    )
    for a in absences_de_la_classe(classe):
        s = a.seance
        justification = a.derniere_justification
        ecrivain.writerow([
            a.etudiant.last_name,
            a.etudiant.first_name,
            a.etudiant.cne,
            a.etudiant.groupe.nom if a.etudiant.groupe else "",
            s.matiere.nom,
            s.get_type_display(),
            f"{a.date:%d/%m/%Y}",
            f"{s.heure_debut:%H:%M}-{s.heure_fin:%H:%M}",
            a.get_nature_display(),
            f"{a.duree_heures:g}".replace(".", ","),
            "" if a.est_retard else a.get_statut_display(),
            justification.get_statut_display() if justification else "",
        ])
    return reponse
