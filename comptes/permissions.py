"""Contrôle d'accès par rôle (BNF01)."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_requis(*roles):
    """Réserve une vue aux utilisateurs connectés ayant l'un des rôles indiqués.

        @role_requis(Utilisateur.Role.ENSEIGNANT, Utilisateur.Role.ADMIN)
        def saisir_absences(request): ...
    """

    def decorateur(vue):
        @wraps(vue)
        @login_required
        def vue_protegee(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied("Vous n'avez pas accès à cette page.")
            return vue(request, *args, **kwargs)

        return vue_protegee

    return decorateur
