def notifications(request):
    """Nombre de notifications non lues, affiché dans la barre de navigation."""
    if not request.user.is_authenticated:
        return {}
    return {"nb_notifications_non_lues": request.user.notifications.filter(lue=False).count()}
