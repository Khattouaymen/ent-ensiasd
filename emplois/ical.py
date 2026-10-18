"""Flux iCalendar (RFC 5545) de l'emploi du temps d'un utilisateur.

Contient les séances qui ont réellement lieu (sans jours non travaillés ni annulations), les
examens et les dates limites des devoirs. Les heures sont données en UTC, ce qui évite de
décrire le fuseau du Maroc (et son changement d'heure pendant le ramadan) dans le fichier.
"""

from datetime import datetime, timedelta
from datetime import timezone as fuseau

from django.utils import timezone

from evaluations.views import devoirs_visibles, examens_visibles

from .views import planning, seances_de

# Fenêtre exportée : quatre semaines passées, puis jusqu'à la fin de l'année universitaire.
SEMAINES_PASSEES = 4
DUREE_PAR_DEFAUT = timedelta(days=180)
DUREE_DEVOIR = timedelta(minutes=30)


def echapper(texte):
    return str(texte).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def plier(ligne):
    """Coupe une ligne à 75 octets ; les lignes de suite commencent par une espace."""
    if len(ligne.encode("utf-8")) <= 75:
        return ligne
    morceaux, courant, taille, limite = [], "", 0, 75
    for caractere in ligne:
        n = len(caractere.encode("utf-8"))
        if taille + n > limite:
            morceaux.append(courant)
            courant, taille, limite = caractere, n, 74  # l'espace initiale compte dans les 75 octets
        else:
            courant, taille = courant + caractere, taille + n
    morceaux.append(courant)
    return "\r\n ".join(morceaux)


def utc(moment):
    return moment.astimezone(fuseau.utc).strftime("%Y%m%dT%H%M%SZ")


def local(jour, heure):
    return timezone.make_aware(datetime.combine(jour, heure))


def evenement(uid, debut, fin, titre, maintenant, lieu="", description=""):
    lignes = ["BEGIN:VEVENT", f"UID:{uid}@ent-ensiasd", f"DTSTAMP:{utc(maintenant)}"]
    lignes += [f"DTSTART:{utc(debut)}", f"DTEND:{utc(fin)}"]
    lignes.append(f"SUMMARY:{echapper(titre)}")
    if lieu:
        lignes.append(f"LOCATION:{echapper(lieu)}")
    if description:
        lignes.append(f"DESCRIPTION:{echapper(description)}")
    lignes.append("END:VEVENT")
    return lignes


def fin_de_periode(utilisateur, du):
    """Dernier jour exporté : fin de l'année universitaire de la classe (ou des classes de l'enseignant)."""
    if utilisateur.est_etudiant and utilisateur.classe_id:
        return utilisateur.classe.periode()[1]
    classes = {s.classe for s in utilisateur.seances.select_related("classe")} if utilisateur.est_enseignant else set()
    return max((c.periode()[1] for c in classes), default=du + DUREE_PAR_DEFAUT)


def calendrier_ics(utilisateur, aujourdhui, adresse_absolue):
    """Texte du fichier .ics ; « adresse_absolue(chemin) » rend un lien complet vers l'ENT."""
    maintenant = timezone.now()
    du = aujourdhui - timedelta(weeks=SEMAINES_PASSEES)
    au = min(fin_de_periode(utilisateur, du), du + timedelta(days=366))
    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ENSIASD Taroudant//ENT//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:ENT ENSIASD",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for jour in planning(seances_de(utilisateur), du, au):
        for s, annulation in jour["seances"]:
            if annulation:
                continue
            if utilisateur.est_enseignant:
                description = f"{s.classe}{f' · {s.groupe.nom}' if s.groupe_id else ''}"
            else:
                description = f"Enseignant : {s.enseignant}{f' · {s.groupe.nom}' if s.groupe_id else ''}"
            lignes += evenement(
                f"seance-{s.pk}-{jour['date']:%Y%m%d}",
                local(jour["date"], s.heure_debut),
                local(jour["date"], s.heure_fin),
                f"{s.matiere} ({s.get_type_display()})",
                maintenant,
                lieu=s.salle,
                description=description,
            )
    for e in examens_visibles(utilisateur).filter(date__range=(du, au)).select_related("matiere", "salle", "groupe"):
        lignes += evenement(
            f"examen-{e.pk}",
            e.debut,
            e.fin or e.debut + timedelta(hours=2),
            f"{e.get_type_display()} : {e.titre or e.matiere}",
            maintenant,
            lieu=e.salle or "",
            description=e.consignes,
        )
    debut, fin = local(du, datetime.min.time()), local(au + timedelta(days=1), datetime.min.time())
    for d in devoirs_visibles(utilisateur).filter(date_limite__range=(debut, fin)).select_related("matiere"):
        lignes += evenement(
            f"devoir-{d.pk}",
            d.date_limite - DUREE_DEVOIR,
            d.date_limite,
            f"À rendre : {d.titre}",
            maintenant,
            description=f"{d.matiere} – {adresse_absolue(d.get_absolute_url())}",
        )
    lignes.append("END:VCALENDAR")
    return "\r\n".join(plier(ligne) for ligne in lignes) + "\r\n"
