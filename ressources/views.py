from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from comptes.permissions import role_requis
from config.formulaires import paginer
from config.formulaires import telecharger as envoyer_fichier
from structure.models import Matiere

from .forms import RessourceForm
from .models import Ressource


def ressources_accessibles(user):
    """Étudiant : sa filière et son niveau (BF07). Enseignant : ses dépôts. Autres : tout."""
    if user.est_etudiant:
        return Ressource.visibles_par(user)
    if user.est_enseignant:
        return Ressource.objects.filter(deposee_par=user)
    return Ressource.objects.all()


@login_required
def liste(request):
    ressources = ressources_accessibles(request.user).select_related("matiere", "deposee_par")
    matieres = Matiere.objects.filter(pk__in=ressources.values("matiere")).order_by("nom")

    matiere_id = request.GET.get("matiere", "")
    type_ = request.GET.get("type", "")
    if matiere_id.isdigit():
        ressources = ressources.filter(matiere_id=matiere_id)
    if type_ in Ressource.Type.values:
        ressources = ressources.filter(type=type_)
    recherche = request.GET.get("q", "").strip()
    if recherche:
        ressources = ressources.filter(
            Q(titre__icontains=recherche) | Q(description__icontains=recherche) | Q(matiere__nom__icontains=recherche)
        )

    return render(
        request,
        "ressources/liste.html",
        {
            "page": paginer(request, ressources),
            "matieres": matieres,
            "types": Ressource.Type.choices,
            "matiere_choisie": matiere_id,
            "type_choisi": type_,
        },
    )


@role_requis("ENSEIGNANT")
def deposer(request):
    """Dépôt d'un support de cours, TD ou TP (BF06)."""
    form = RessourceForm(request.POST or None, request.FILES or None, enseignant=request.user)
    if request.method == "POST" and form.is_valid():
        ressource = form.save(commit=False)
        ressource.deposee_par = request.user
        ressource.save()
        messages.success(request, f"« {ressource.titre} » a été déposé.")
        return redirect("ressources:liste")
    return render(request, "ressources/deposer.html", {"form": form})


@role_requis("ENSEIGNANT", "ADMIN")
@require_POST
def supprimer(request, pk):
    ressource = get_object_or_404(Ressource, pk=pk)
    if not request.user.est_admin and ressource.deposee_par_id != request.user.pk:
        raise PermissionDenied
    ressource.fichier.delete(save=False)
    ressource.delete()
    messages.success(request, "La ressource a été supprimée.")
    return redirect("ressources:liste")


@login_required
def telecharger(request, pk):
    """Un étudiant ne peut télécharger que les supports de sa filière et de son niveau."""
    ressources = Ressource.visibles_par(request.user) if request.user.est_etudiant else Ressource.objects.all()
    ressource = get_object_or_404(ressources, pk=pk)
    return envoyer_fichier(ressource.fichier)
