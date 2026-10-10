from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from config.formulaires import paginer


@login_required
def liste(request):
    return render(request, "notifications/liste.html", {"page": paginer(request, request.user.notifications.all())})


@login_required
def ouvrir(request, pk):
    """Marque la notification comme lue puis redirige vers la page concernée."""
    notification = get_object_or_404(request.user.notifications, pk=pk)
    if not notification.lue:
        notification.lue = True
        notification.save(update_fields=["lue"])
    # Seuls les liens internes au site sont suivis.
    if notification.lien and url_has_allowed_host_and_scheme(notification.lien, allowed_hosts={request.get_host()}):
        return redirect(notification.lien)
    return redirect("notifications:liste")


@login_required
@require_POST
def tout_marquer_lu(request):
    request.user.notifications.filter(lue=False).update(lue=True)
    return redirect("notifications:liste")
