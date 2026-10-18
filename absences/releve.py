"""Relevé d'absences d'un étudiant au format PDF : bilan par matière et détail chronologique."""

from io import BytesIO

from django.conf import settings
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import escape
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, Frame, NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle

from comptes.templatetags.ent import heures, libelle_alerte

from .models import Absence, AlerteAbsence

BLEU = HexColor("#115EA3")
NUIT = HexColor("#0B2545")
GRIS = HexColor("#5B6779")
BORDURE = HexColor("#D5DCE6")
FOND_ENTETE = HexColor("#E7EFF8")
FOND_ALTERNE = HexColor("#F7F9FC")
COULEURS_ALERTE = {"CRITIQUE": HexColor("#A8201A"), "AVERTISSEMENT": HexColor("#8A5A00")}
LOGO = settings.BASE_DIR / "static" / "img" / "logo_ensiasd.jpg"
MARGE = 1.8 * cm
LARGEUR_UTILE = A4[0] - 2 * MARGE

STYLE_TITRE = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=BLEU)
STYLE_SECTION = ParagraphStyle(
    "section", fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=NUIT, spaceBefore=16, spaceAfter=6
)
STYLE_CELLULE = ParagraphStyle("cellule", fontName="Helvetica", fontSize=8.5, leading=10.5)
STYLE_NOTE = ParagraphStyle("note", fontName="Helvetica", fontSize=8, leading=10.5, textColor=GRIS)


def style_tableau(entete=True):
    """Bordures fines, en-tête bleu pâle et lignes alternées."""
    commandes = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDURE),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDURE),
        ("ROWBACKGROUNDS", (0, 1 if entete else 0), (-1, -1), [white, FOND_ALTERNE]),
    ]
    if entete:
        commandes += [
            ("BACKGROUND", (0, 0), (-1, 0), FOND_ENTETE),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), NUIT),
        ]
    return TableStyle(commandes)


def cellule(texte):
    """Texte qui peut passer à la ligne ; échappé, car ReportLab l'interprète comme du balisage."""
    return Paragraph(escape(texte), STYLE_CELLULE)


def identite(etudiant, aujourdhui):
    classe = etudiant.classe
    lignes = [
        ["Étudiant(e)", f"{etudiant.last_name.upper()} {etudiant.first_name}".strip() or etudiant.username,
         "CNE", etudiant.cne or "—"],
        ["Classe", str(classe) if classe else "—", "Groupe", etudiant.groupe.nom if etudiant.groupe else "—"],
        ["Situation au", date_format(aujourdhui, "j F Y"), "Seuils d'alerte",
         ", ".join(f"{libelle_alerte(niveau).lower()} {seuil} %" for niveau, seuil in AlerteAbsence.seuils())],
    ]
    lignes = [[valeur if i % 2 == 0 else cellule(valeur) for i, valeur in enumerate(ligne)] for ligne in lignes]
    tableau = Table(lignes, colWidths=[2.4 * cm, 5.8 * cm, 2.6 * cm, 6.6 * cm])
    tableau.setStyle(style_tableau(entete=False))
    for colonne in (0, 2):  # libellés
        tableau.setStyle(TableStyle([
            ("FONT", (colonne, 0), (colonne, -1), "Helvetica-Bold", 8.5),
            ("TEXTCOLOR", (colonne, 0), (colonne, -1), GRIS),
        ]))
    return tableau


def chiffres_cles(totaux):
    valeurs = [
        (heures(sum(l["total"] for l in totaux)), "Heures d'absence"),
        (heures(sum(l["non_justifiees"] for l in totaux)), "Non justifiées"),
        (str(sum(l["retards"] for l in totaux)), "Retards"),
        (str(sum(1 for l in totaux if l["alerte"])), "Matières en alerte"),
    ]
    style_valeur = ParagraphStyle("valeur", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=NUIT)
    tableau = Table(
        [[[Paragraph(escape(v), style_valeur), Paragraph(escape(libelle), STYLE_NOTE)] for v, libelle in valeurs]],
        colWidths=[LARGEUR_UTILE / 4] * 4,
    )
    tableau.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, BORDURE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, BORDURE),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return tableau


def bilan_par_matiere(totaux):
    entete = ["Matière", "Volume", "Absences", "Justifiées", "Non justifiées", "Part du VH", "Retards", "Alerte"]
    lignes = [entete]
    for l in totaux:
        lignes.append([
            cellule(str(l["matiere"])),
            f"{l['matiere'].volume_horaire} h" if l["matiere"].volume_horaire else "—",
            heures(l["total"]),
            heures(l["justifiees"]),
            heures(l["non_justifiees"]),
            f"{l['taux']:.0f} %" if l["matiere"].volume_horaire else "—",
            str(l["retards"]),
            libelle_alerte(l["alerte"]) if l["alerte"] else "—",
        ])
    lignes.append([
        "Total", "",
        heures(sum(l["total"] for l in totaux)),
        heures(sum(l["justifiees"] for l in totaux)),
        heures(sum(l["non_justifiees"] for l in totaux)),
        "", str(sum(l["retards"] for l in totaux)), "",
    ])
    largeurs = [4.4, 1.4, 1.7, 1.8, 2.2, 1.8, 1.4, 2.7]
    tableau = Table(lignes, colWidths=[x * cm for x in largeurs], repeatRows=1)
    tableau.setStyle(style_tableau())
    commandes = [
        ("ALIGN", (1, 0), (6, -1), "RIGHT"),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, NUIT),
    ]
    for i, l in enumerate(totaux, start=1):
        if l["alerte"]:
            commandes += [
                ("TEXTCOLOR", (7, i), (7, i), COULEURS_ALERTE[l["alerte"]]),
                ("FONT", (7, i), (7, i), "Helvetica-Bold", 8.5),
            ]
    tableau.setStyle(TableStyle(commandes))
    return tableau


def detail(absences):
    lignes = [["Date", "Créneau", "Matière", "Type", "Nature", "Durée", "Statut", "Justificatif"]]
    for a in absences:
        s, justification = a.seance, a.derniere_justification
        lignes.append([
            f"{a.date:%d/%m/%Y}",
            f"{s.heure_debut:%H:%M}–{s.heure_fin:%H:%M}",
            cellule(str(s.matiere)),
            s.get_type_display(),
            a.get_nature_display(),
            "—" if a.est_retard else heures(a.duree_heures),
            "—" if a.est_retard else a.get_statut_display(),
            justification.get_statut_display() if justification else "—",
        ])
    largeurs = [1.9, 2.1, 4.5, 1.4, 1.5, 1.3, 2.4, 2.3]
    tableau = Table(lignes, colWidths=[x * cm for x in largeurs], repeatRows=1)
    tableau.setStyle(style_tableau())
    tableau.setStyle(TableStyle([("ALIGN", (5, 0), (5, -1), "RIGHT")]))
    return tableau


def generer_releve(etudiant):
    """Contenu PDF (bytes) du relevé d'absences et de retards de l'étudiant, à la date du jour."""
    aujourdhui = timezone.localdate()
    nom = f"{etudiant.last_name.upper()} {etudiant.first_name}".strip() or etudiant.username
    genere_le = f"Généré par l'ENT ENSIASD le {date_format(timezone.localtime(), 'd/m/Y à H:i')}"
    logo = ImageReader(str(LOGO))
    logo_l, logo_h = logo.getSize()
    hauteur_logo = LARGEUR_UTILE * logo_h / logo_l

    def pied(pdf, doc):
        pdf.saveState()
        pdf.setFont("Helvetica", 7.5)
        pdf.setFillColor(GRIS)
        pdf.drawString(MARGE, MARGE - 0.7 * cm, f"{genere_le} – relevé informatif, sans valeur d'attestation.")
        pdf.drawRightString(A4[0] - MARGE, MARGE - 0.7 * cm, f"Page {doc.page}")
        pdf.restoreState()

    def premiere_page(pdf, doc):
        pdf.drawImage(logo, MARGE, A4[1] - MARGE - hauteur_logo, LARGEUR_UTILE, hauteur_logo, mask="auto")
        pdf.setStrokeColor(BLEU)
        pdf.setLineWidth(1.2)
        y = A4[1] - MARGE - hauteur_logo - 0.4 * cm
        pdf.line(MARGE, y, A4[0] - MARGE, y)
        pied(pdf, doc)

    def pages_suivantes(pdf, doc):
        pdf.setFont("Helvetica", 8.5)
        pdf.setFillColor(GRIS)
        pdf.drawString(MARGE, A4[1] - MARGE + 0.1 * cm, f"Relevé d'absences – {nom}")
        pdf.setStrokeColor(BORDURE)
        pdf.line(MARGE, A4[1] - MARGE - 0.15 * cm, A4[0] - MARGE, A4[1] - MARGE - 0.15 * cm)
        pied(pdf, doc)

    tampon = BytesIO()
    doc = BaseDocTemplate(
        tampon, pagesize=A4, leftMargin=MARGE, rightMargin=MARGE, topMargin=MARGE, bottomMargin=MARGE,
        title=f"Relevé d'absences – {nom}", author="ENSIASD Taroudant – ENT",
    )
    sans_marge = {"leftPadding": 0, "rightPadding": 0, "topPadding": 0, "bottomPadding": 0}
    hauteur = A4[1] - 2 * MARGE
    doc.addPageTemplates([
        PageTemplate("premiere", [Frame(MARGE, MARGE, LARGEUR_UTILE, hauteur - hauteur_logo - 0.9 * cm, **sans_marge)],
                     onPage=premiere_page),
        PageTemplate("suite", [Frame(MARGE, MARGE, LARGEUR_UTILE, hauteur - 0.6 * cm, **sans_marge)], onPage=pages_suivantes),
    ])

    totaux = Absence.heures_par_matiere(etudiant)
    absences = list(
        etudiant.absences.select_related("seance__matiere")
        .prefetch_related("justifications")
        .order_by("date", "seance__heure_debut")
    )
    elements = [
        NextPageTemplate("suite"),
        Paragraph("RELEVÉ D'ABSENCES ET DE RETARDS", STYLE_TITRE),
        Spacer(1, 0.4 * cm),
        identite(etudiant, aujourdhui),
        Spacer(1, 0.4 * cm),
        chiffres_cles(totaux),
    ]
    if absences:
        elements += [
            Paragraph("Bilan par matière", STYLE_SECTION),
            bilan_par_matiere(totaux),
            Spacer(1, 0.15 * cm),
            Paragraph(
                "Part du VH : heures d'absence non justifiées rapportées au volume horaire de la matière. "
                "Un retard ne compte pas d'heures d'absence.",
                STYLE_NOTE,
            ),
            Paragraph("Détail des absences et retards", STYLE_SECTION),
            detail(absences),
        ]
    else:
        elements += [Spacer(1, 0.6 * cm), Paragraph("Aucune absence ni aucun retard enregistré.", STYLE_CELLULE)]
    doc.build(elements)
    return tampon.getvalue()
