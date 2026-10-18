"""Génération de l'attestation de scolarité au format PDF."""

from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import escape
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

BLEU = HexColor("#115EA3")
LOGO = settings.BASE_DIR / "static" / "img" / "logo_ensiasd.jpg"


class AttestationImpossible(Exception):
    pass


def generer_attestation(demande):
    """Renvoie un ContentFile PDF prêt à être enregistré dans ``demande.document``."""
    etudiant = demande.etudiant
    classe = etudiant.classe
    if classe is None:
        raise AttestationImpossible("L'étudiant n'est affecté à aucune classe : impossible de générer l'attestation.")

    tampon = BytesIO()
    pdf = canvas.Canvas(tampon, pagesize=A4)
    largeur, hauteur = A4
    marge = 2.2 * cm
    pdf.setTitle(f"Attestation de scolarité – {etudiant.get_full_name()}")
    pdf.setAuthor("ENSIASD Taroudant – Service de scolarité")

    # En-tête : logo de l'école
    logo = ImageReader(str(LOGO))
    logo_l, logo_h = logo.getSize()
    largeur_logo = largeur - 2 * marge
    hauteur_logo = largeur_logo * logo_h / logo_l
    pdf.drawImage(logo, marge, hauteur - marge - hauteur_logo, largeur_logo, hauteur_logo, mask="auto")
    y = hauteur - marge - hauteur_logo - 0.6 * cm
    pdf.setStrokeColor(BLEU)
    pdf.setLineWidth(1.2)
    pdf.line(marge, y, largeur - marge, y)

    # Référence et titre
    annee = classe.annee_universitaire
    y -= 1.2 * cm
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(HexColor("#555555"))
    pdf.drawString(marge, y, f"Réf. : ATT-{annee.replace('/', '')}-{demande.pk:05d}")
    y -= 2 * cm
    pdf.setFont("Helvetica-Bold", 20)
    pdf.setFillColor(BLEU)
    pdf.drawCentredString(largeur / 2, y, "ATTESTATION DE SCOLARITÉ")

    # Corps du texte
    style = ParagraphStyle("corps", fontName="Helvetica", fontSize=12, leading=20, alignment=TA_JUSTIFY)
    # Les valeurs sont échappées : le texte est interprété comme du balisage par ReportLab.
    nom_complet = escape(f"{etudiant.last_name.upper()} {etudiant.first_name}".strip() or etudiant.username)
    cne = f", titulaire du CNE <b>{escape(etudiant.cne)}</b>," if etudiant.cne else ","
    texte = (
        "Le Directeur de l'École Nationale Supérieure de l'Intelligence Artificielle et Sciences "
        "des Données de Taroudant atteste que l'étudiant(e) :"
        f"<br/><br/><b>{nom_complet}</b>{cne}"
        f"<br/><br/>est régulièrement inscrit(e) en <b>{escape(classe.niveau)}</b> de la filière "
        f"<b>{escape(classe.filiere.nom)} ({escape(classe.filiere.code)})</b> "
        f"au titre de l'année universitaire <b>{escape(annee)}</b>."
        "<br/><br/>La présente attestation est délivrée à l'intéressé(e) pour servir et valoir ce que de droit."
    )
    paragraphe = Paragraph(texte, style)
    _, h = paragraphe.wrap(largeur - 2 * marge, hauteur)
    y -= 1.5 * cm + h
    paragraphe.drawOn(pdf, marge, y)

    # Lieu, date et emplacement de la signature
    y -= 2 * cm
    pdf.setFont("Helvetica", 12)
    pdf.setFillColor(HexColor("#000000"))
    pdf.drawRightString(largeur - marge, y, f"Fait à Taroudant, le {date_format(timezone.localdate(), 'j F Y')}")
    y -= 1 * cm
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(largeur - marge, y, "Le Directeur")
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.setFillColor(HexColor("#777777"))
    pdf.drawRightString(largeur - marge, y - 0.5 * cm, "(signature et cachet)")

    # Pied de page
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(
        largeur / 2,
        1.5 * cm,
        f"Document généré par l'ENT ENSIASD le {date_format(timezone.localtime(), 'd/m/Y à H:i')} – "
        "valable uniquement revêtu de la signature et du cachet de l'établissement.",
    )
    pdf.showPage()
    pdf.save()

    nom_fichier = f"attestation_scolarite_{etudiant.username}_{annee.replace('/', '-')}.pdf"
    return ContentFile(tampon.getvalue(), name=nom_fichier)
