from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from comptes.permissions import role_requis
from config.formulaires import paginer
from config.formulaires import telecharger as envoyer_fichier
from notifications.models import Notification

from .attestation import AttestationImpossible, generer_attestation
from .forms import STATUTS_EN_COURS, AjoutDocumentForm, DemandeForm, TraitementDemandeForm
from .models import DemandeDocument

FILTRES = [
    ("a_traiter", "À traiter"),
    *DemandeDocument.Statut.choices,
    ("toutes", "Toutes"),
]


@login_required
def liste(request):
    """Étudiant : ses demandes. Scolarité / administrateur : toutes les demandes, filtrées et paginées."""
    user = request.user
    demandes = DemandeDocument.objects.select_related("etudiant__classe__filiere", "etudiant__classe__niveau", "traitee_par")
    contexte = {}
    if user.est_etudiant:
        demandes = demandes.filter(etudiant=user)
    elif user.est_scolarite or user.est_admin:
        filtre = request.GET.get("statut", "a_traiter")
        if filtre == "a_traiter":
            demandes = demandes.filter(statut__in=STATUTS_EN_COURS).order_by("date_demande")
        elif filtre in DemandeDocument.Statut.values:
            demandes = demandes.filter(statut=filtre)
        recherche = request.GET.get("q", "").strip()
        if recherche:
            demandes = demandes.filter(
                Q(etudiant__last_name__icontains=recherche)
                | Q(etudiant__first_name__icontains=recherche)
                | Q(etudiant__cne__icontains=recherche)
            )
        contexte.update(filtres=FILTRES, filtre=filtre)
    else:
        demandes = demandes.none()
    contexte["page"] = paginer(request, demandes)
    return render(request, "documents/liste.html", contexte)


@role_requis("ETUDIANT")
def nouvelle(request):
    """Demande d'un document administratif (BF08)."""
    form = DemandeForm(request.POST or None, etudiant=request.user)
    if request.method == "POST" and form.is_valid():
        demande = form.save(commit=False)
        demande.etudiant = request.user
        demande.save()
        Notification.envoyer_au_role(
            "SCOLARITE",
            f"Nouvelle demande : {demande.get_type_document_display()} – {request.user}.",
            lien=reverse("documents:traiter", args=[demande.pk]),
        )
        messages.success(request, "Votre demande a été envoyée au service de scolarité.")
        return redirect("documents:liste")
    return render(request, "documents/nouvelle.html", {"form": form})


def joindre_attestation(demande):
    """Génère l'attestation de scolarité si la demande en est une ; renvoie un message d'erreur ou None."""
    if demande.type_document != DemandeDocument.TypeDocument.ATTESTATION_SCOLARITE:
        return None
    try:
        demande.document = generer_attestation(demande)
    except AttestationImpossible as erreur:
        return str(erreur)
    return None


def notifier_document_disponible(demande):
    Notification.envoyer(
        demande.etudiant,
        f"Votre document « {demande.get_type_document_display()} » est disponible au téléchargement.",
        lien=reverse("documents:liste"),
    )


@role_requis("SCOLARITE", "ADMIN")
def traiter(request, pk):
    """Changement de statut d'une demande par la scolarité (BF09), puis ajout éventuel du document."""
    demande = get_object_or_404(DemandeDocument.objects.select_related("etudiant__classe__filiere"), pk=pk)
    form = ajout = None
    action = request.POST.get("action")

    if demande.statut == DemandeDocument.Statut.PRETE:
        # Le document peut être joint (ou remplacé) après coup, ou généré pour une attestation.
        ajout = AjoutDocumentForm(request.POST if action == "joindre" else None, request.FILES if action == "joindre" else None)
        if action == "joindre" and ajout.is_valid():
            demande.document = ajout.cleaned_data["document"]
            demande.save(update_fields=["document"])
            notifier_document_disponible(demande)
            messages.success(request, "Le document a été joint. L'étudiant a été notifié.")
            return redirect("documents:traiter", pk=demande.pk)
        if action == "generer":
            erreur = joindre_attestation(demande)
            if erreur:
                messages.error(request, erreur)
            else:
                demande.save(update_fields=["document"])
                notifier_document_disponible(demande)
                messages.success(request, "L'attestation a été générée. L'étudiant a été notifié.")
            return redirect("documents:traiter", pk=demande.pk)

    elif demande.TRANSITIONS[demande.statut]:
        form = TraitementDemandeForm(request.POST or None, request.FILES or None, demande=demande)
        if request.method == "POST" and form.is_valid():
            nouveau = form.cleaned_data["statut"]
            if form.cleaned_data["document"]:
                demande.document = form.cleaned_data["document"]
            elif nouveau == DemandeDocument.Statut.PRETE:
                erreur = joindre_attestation(demande)
                if erreur:
                    messages.warning(request, erreur)
            try:
                demande.changer_statut(nouveau, request.user, form.cleaned_data["commentaire"])
            except ValidationError as erreur:
                messages.error(request, erreur.messages[0])
            else:
                messages.success(request, f"Demande passée à « {demande.get_statut_display()} ». L'étudiant a été notifié.")
                return redirect("documents:liste")

    return render(request, "documents/traiter.html", {"demande": demande, "form": form, "ajout": ajout})


@login_required
def telecharger(request, pk):
    """Téléchargement du document délivré : réservé à l'étudiant concerné et au personnel (BF10)."""
    user = request.user
    demandes = DemandeDocument.objects.all()
    if not (user.est_scolarite or user.est_admin):
        demandes = demandes.filter(etudiant=user)
    demande = get_object_or_404(demandes, pk=pk)
    return envoyer_fichier(demande.document)
