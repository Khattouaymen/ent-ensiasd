import os
import shutil
import tempfile
import zipfile
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import get_valid_filename, slugify
from django.views.decorators.http import require_POST

from comptes.permissions import role_requis
from config.formulaires import telecharger
from structure.models import Classe

from .forms import DevoirForm, ExamenForm, RenduForm
from .models import Devoir, Examen, Rendu

AUTEURS_EXAMENS = ("ENSEIGNANT", "SCOLARITE", "ADMIN")


def examens_visibles(utilisateur):
    if utilisateur.est_etudiant:
        return Examen.pour_etudiant(utilisateur)
    if utilisateur.est_enseignant:
        return Examen.pour_enseignant(utilisateur)
    return Examen.objects.all()


def devoirs_visibles(utilisateur):
    """Étudiant : les devoirs de sa classe et de son groupe. Enseignant : les siens. Personnel : tous."""
    if utilisateur.est_etudiant:
        return Devoir.pour_etudiant(utilisateur)
    return devoirs_geres(utilisateur)


def devoirs_geres(utilisateur):
    """Devoirs dont l'utilisateur peut voir et télécharger les rendus."""
    if utilisateur.est_enseignant:
        return Devoir.objects.filter(enseignant=utilisateur)
    if utilisateur.est_scolarite or utilisateur.est_admin:
        return Devoir.objects.all()
    return Devoir.objects.none()


def echeances(utilisateur, depuis, jusqua=None, classe=None, passees=False):
    """Examens et dates limites de devoirs, triés : [{"quand", "date", "type", "objet", "rendu"}, …]."""
    examens = examens_visibles(utilisateur).select_related("matiere", "classe__filiere", "classe__niveau", "groupe", "salle")
    devoirs = devoirs_visibles(utilisateur).select_related("matiere", "classe__filiere", "classe__niveau", "groupe")
    if classe:
        examens, devoirs = examens.filter(classe=classe), devoirs.filter(classe=classe)
    debut = timezone.make_aware(datetime.combine(depuis, time.min))
    if passees:
        examens, devoirs = examens.filter(date__lt=depuis), devoirs.filter(date_limite__lt=debut)
    else:
        examens, devoirs = examens.filter(date__gte=depuis), devoirs.filter(date_limite__gte=debut)
        if jusqua:
            fin = timezone.make_aware(datetime.combine(jusqua + timedelta(days=1), time.min))
            examens, devoirs = examens.filter(date__lte=jusqua), devoirs.filter(date_limite__lt=fin)
    rendus = {}
    if utilisateur.est_etudiant:
        rendus = {r.devoir_id: r for r in utilisateur.rendus.filter(devoir__in=devoirs)}
    personnel = utilisateur.est_scolarite or utilisateur.est_admin
    elements = [
        {
            "quand": e.debut,
            "date": e.date,
            "type": "examen",
            "objet": e,
            "supprimable": personnel or e.cree_par_id == utilisateur.pk,
        }
        for e in examens
    ]
    for d in devoirs:
        date = timezone.localtime(d.date_limite).date()
        elements.append({"quand": d.date_limite, "date": date, "type": "devoir", "objet": d, "rendu": rendus.get(d.pk)})
    elements.sort(key=lambda e: e["quand"], reverse=passees)
    aujourdhui = timezone.localdate()
    for e in elements:
        e["dans_jours"] = (e["date"] - aujourdhui).days
    return elements


# --- Calendrier et examens ----------------------------------------------------------------


@login_required
def calendrier(request):
    """Examens et dates limites de devoirs à venir (ou passés avec ?passees=1)."""
    utilisateur = request.user
    passees = request.GET.get("passees") == "1"
    classes = classe = None
    if utilisateur.est_scolarite or utilisateur.est_admin:
        classes = Classe.objects.all()
        classe_id = request.GET.get("classe", "")
        classe = classes.filter(pk=classe_id).first() if classe_id.isdigit() else None
    elements = echeances(utilisateur, timezone.localdate(), classe=classe, passees=passees)
    contexte = {
        "elements": elements[:100] if passees else elements,
        "passees": passees,
        "classes": classes,
        "classe": classe,
        "peut_programmer": utilisateur.role in AUTEURS_EXAMENS,
    }
    return render(request, "evaluations/calendrier.html", contexte)


@role_requis(*AUTEURS_EXAMENS)
def nouvel_examen(request):
    form = ExamenForm(request.POST or None, auteur=request.user)
    if request.method == "POST" and form.is_valid():
        examen = form.save(commit=False)
        examen.cree_par = request.user
        examen.save()
        examen.notifier()
        messages.success(request, f"Examen programmé le {examen.date:%d/%m/%Y}. Les étudiants concernés ont été prévenus.")
        return redirect("evaluations:calendrier")
    contexte = {"form": form, "titre": "Programmer un examen", "icone": "calendar-plus"}
    return render(request, "evaluations/formulaire.html", contexte)


@role_requis(*AUTEURS_EXAMENS)
@require_POST
def supprimer_examen(request, pk):
    examen = get_object_or_404(examens_visibles(request.user), pk=pk)
    if not (request.user.est_scolarite or request.user.est_admin or examen.cree_par_id == request.user.pk):
        raise PermissionDenied
    examen.delete()
    messages.success(request, "L'examen a été supprimé.")
    return redirect("evaluations:calendrier")


# --- Devoirs ------------------------------------------------------------------------------


@login_required
def devoirs(request):
    """Étudiant : devoirs à rendre et rendus. Enseignant et personnel : devoirs et nombre de rendus."""
    utilisateur = request.user
    liste = devoirs_visibles(utilisateur).select_related("matiere", "classe__filiere", "classe__niveau", "groupe", "enseignant")
    if utilisateur.est_etudiant:
        rendus = {r.devoir_id: r for r in utilisateur.rendus.all()}
        lignes = [{"devoir": d, "rendu": rendus.get(d.pk)} for d in liste]
        a_rendre = [l for l in lignes if not l["rendu"] and l["devoir"].accepte_les_rendus]
        autres = [l for l in lignes if l not in a_rendre]
        autres.sort(key=lambda l: l["devoir"].date_limite, reverse=True)
        return render(request, "evaluations/devoirs_etudiant.html", {"a_rendre": a_rendre, "autres": autres})
    liste = liste.annotate(nb_rendus=Count("rendus")).order_by("-date_limite")
    lignes = [{"devoir": d, "attendus": d.public().count()} for d in liste]
    return render(request, "evaluations/devoirs_enseignant.html", {"lignes": lignes})


@role_requis("ENSEIGNANT")
def nouveau_devoir(request):
    form = DevoirForm(request.POST or None, request.FILES or None, auteur=request.user)
    if request.method == "POST" and form.is_valid():
        devoir = form.save(commit=False)
        devoir.enseignant = request.user
        devoir.save()
        devoir.notifier()
        messages.success(request, "Devoir publié. Les étudiants concernés ont été prévenus.")
        return redirect(devoir)
    contexte = {"form": form, "titre": "Nouveau devoir", "icone": "journal-plus", "fichiers": True}
    return render(request, "evaluations/formulaire.html", contexte)


@login_required
def devoir(request, pk):
    utilisateur = request.user
    devoir = get_object_or_404(devoirs_visibles(utilisateur).select_related("matiere", "classe", "groupe", "enseignant"), pk=pk)
    if not utilisateur.est_etudiant:
        rendus = {r.etudiant_id: r for r in devoir.rendus.all()}
        lignes = [{"etudiant": e, "rendu": rendus.get(e.pk)} for e in devoir.public().select_related("groupe")]
        contexte = {"devoir": devoir, "lignes": lignes, "nb_rendus": len(rendus)}
        return render(request, "evaluations/devoir_enseignant.html", contexte)

    rendu = devoir.rendus.filter(etudiant=utilisateur).first()
    # Lu avant la validation : le formulaire remplace aussitôt le fichier de l'instance.
    ancien_fichier = rendu.fichier.name if rendu else None
    form = RenduForm(request.POST or None, request.FILES or None, instance=rendu)
    if request.method == "POST":
        if not devoir.accepte_les_rendus:
            messages.error(request, "La date limite est dépassée : ce devoir n'accepte plus de rendu.")
            return redirect(devoir)
        if form.is_valid():
            nouveau = form.save(commit=False)
            nouveau.devoir, nouveau.etudiant = devoir, utilisateur
            nouveau.date_depot = timezone.now()
            nouveau.en_retard = devoir.est_depasse
            try:
                with transaction.atomic():
                    nouveau.save()
            except IntegrityError:
                # Double envoi simultané : le premier dépôt est conservé.
                nouveau.fichier.delete(save=False)
                messages.info(request, "Votre rendu vient déjà d'être enregistré.")
                return redirect(devoir)
            if ancien_fichier and ancien_fichier != nouveau.fichier.name:
                default_storage.delete(ancien_fichier)
            messages.success(request, "Votre rendu a été déposé." + (" Il est marqué en retard." if nouveau.en_retard else ""))
            return redirect(devoir)
    return render(request, "evaluations/devoir_etudiant.html", {"devoir": devoir, "rendu": rendu, "form": form})


@login_required
def sujet(request, pk):
    """Fichier de consignes : étudiants concernés, enseignant du devoir et personnel."""
    return telecharger(get_object_or_404(devoirs_visibles(request.user), pk=pk).fichier_consignes)


@login_required
def fichier_rendu(request, pk):
    """Fichier d'un rendu : son auteur, l'enseignant du devoir et le personnel."""
    utilisateur = request.user
    if utilisateur.est_etudiant:
        rendus = Rendu.objects.filter(etudiant=utilisateur)
    else:
        rendus = Rendu.objects.filter(devoir__in=devoirs_geres(utilisateur))
    return telecharger(get_object_or_404(rendus, pk=pk).fichier)


@login_required
def rendus_zip(request, pk):
    """Archive ZIP de tous les rendus d'un devoir, nommés « NOM_Prénom_fichier »."""
    devoir = get_object_or_404(devoirs_geres(request.user), pk=pk)
    # Archive sur disque au-delà de 10 Mo, pour ne pas charger tous les rendus en mémoire.
    archive = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
    noms = set()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:
        for rendu in devoir.rendus.select_related("etudiant"):
            e = rendu.etudiant
            nom = get_valid_filename(f"{e.last_name.upper()}_{e.first_name}_{os.path.basename(rendu.fichier.name)}")
            if nom in noms:  # deux étudiants homonymes
                nom = f"{rendu.pk}_{nom}"
            noms.add(nom)
            try:
                with rendu.fichier.open("rb") as source, zf.open(nom, "w") as destination:
                    shutil.copyfileobj(source, destination)
            except FileNotFoundError:
                continue
    archive.seek(0)
    return FileResponse(archive, as_attachment=True, filename=f"rendus_{slugify(devoir.titre) or devoir.pk}.zip")


@role_requis("ENSEIGNANT", "SCOLARITE", "ADMIN")
@require_POST
def supprimer_devoir(request, pk):
    devoir = get_object_or_404(devoirs_geres(request.user), pk=pk)
    devoir.supprimer_fichiers()
    devoir.delete()
    messages.success(request, "Le devoir et ses rendus ont été supprimés.")
    return redirect("evaluations:devoirs")
