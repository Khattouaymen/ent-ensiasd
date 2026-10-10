from django import template

register = template.Library()

COULEURS_STATUT = {
    "EN_ATTENTE": "warning",
    "ACCEPTEE": "info",
    "PRETE": "success",
    "REFUSEE": "danger",
    "JUSTIFIEE": "success",
    "NON_JUSTIFIEE": "secondary",
    "AVERTISSEMENT": "warning",
    "CRITIQUE": "danger",
}

# Pour une justification, « acceptée » est l'issue finale : vert plutôt que bleu.
COULEURS_JUSTIFICATION = {**COULEURS_STATUT, "ACCEPTEE": "success"}

LIBELLES_ALERTE = {"AVERTISSEMENT": "Avertissement", "CRITIQUE": "Seuil critique"}


@register.filter
def couleur_statut(statut):
    """Couleur Bootstrap associée à un statut : {{ demande.statut|couleur_statut }}."""
    return COULEURS_STATUT.get(statut, "secondary") if statut else ""


@register.filter
def couleur_justification(statut):
    return COULEURS_JUSTIFICATION.get(statut, "secondary")


@register.filter
def libelle_alerte(niveau):
    return LIBELLES_ALERTE.get(niveau, niveau)


@register.filter
def heures(valeur):
    """Affiche un nombre d'heures sans décimales inutiles : 1.5 → « 1,5 h », 4.0 → « 4 h »."""
    return f"{valeur:g} h".replace(".", ",")
