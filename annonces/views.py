from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from comptes.permissions import role_requis
from config.formulaires import paginer

from .forms import AnnonceForm
from .models import Annonce

AUTEURS = ("SCOLARITE", "ADMIN", "ENSEIGNANT")


@login_required
def liste(request):
    annonces = Annonce.visibles_par(request.user)
    contexte = {"page": paginer(request, annonces), "peut_publier": request.user.role in AUTEURS}
    return render(request, "annonces/liste.html", contexte)


@login_required
def detail(request, pk):
    annonce = get_object_or_404(Annonce.visibles_par(request.user, y_compris_expirees=True), pk=pk)
    return render(
        request, "annonces/detail.html", {"annonce": annonce, "peut_supprimer": annonce.peut_etre_supprimee_par(request.user)}
    )


@role_requis(*AUTEURS)
def nouvelle(request):
    form = AnnonceForm(request.POST or None, auteur=request.user)
    if request.method == "POST" and form.is_valid():
        annonce = form.save(commit=False)
        annonce.auteur = request.user
        annonce.save()
        annonce.notifier()
        messages.success(request, f"Annonce publiée pour : {annonce.destinataires_libelle}.")
        return redirect(annonce)
    return render(request, "annonces/nouvelle.html", {"form": form})


@role_requis(*AUTEURS)
@require_POST
def supprimer(request, pk):
    annonce = get_object_or_404(Annonce, pk=pk)
    if not annonce.peut_etre_supprimee_par(request.user):
        raise PermissionDenied
    annonce.delete()
    messages.success(request, "L'annonce a été supprimée.")
    return redirect("annonces:liste")
