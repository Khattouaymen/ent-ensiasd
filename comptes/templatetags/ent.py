from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

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


@register.simple_tag(takes_context=True)
def lien_menu(context, nom_url, icone, libelle, *autres_vues, compteur=0):
    """Lien de la barre latérale, mis en évidence sur sa page et sur les pages « autres_vues ».

        {% lien_menu "absences:justifications" "patch-check" "Justifications" "absences:traiter_justification" %}
    """
    correspondance = context["request"].resolver_match
    vue = correspondance.view_name if correspondance else ""
    actif = vue == nom_url or vue in autres_vues
    return format_html(
        '<a class="ent-lien{}" href="{}"{}><i class="bi bi-{}" aria-hidden="true"></i><span>{}</span>{}</a>',
        " actif" if actif else "",
        reverse(nom_url),
        mark_safe(' aria-current="page"') if actif else "",
        icone,
        libelle,
        format_html('<span class="badge rounded-pill bg-danger">{}</span>', compteur) if compteur else "",
    )


@register.filter
def initiales(utilisateur):
    """Initiales affichées dans l'avatar : « Yassine Amrani » → « YA »."""
    lettres = (utilisateur.first_name[:1] + utilisateur.last_name[:1]) or utilisateur.username[:2]
    return lettres.upper()
