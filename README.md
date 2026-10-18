# ENT ENSIASD – Système de gestion d'un établissement scolaire

Projet MGSI S3 (2026/2027) – ENSIASD Taroudant.
Plateforme web : absences, ressources pédagogiques, demandes de documents, classes et emplois du temps,
annonces, examens et devoirs en ligne.

**Technologies :** Python 3.11 (dernière version 3.11.x) · Django 5.2 LTS · SQLite · Bootstrap 5

## Installation (première fois)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (sous Linux/macOS : source .venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py peupler_demo   # données fictives de démonstration
python manage.py runserver
```

Puis ouvrir http://localhost:8000.

## Comptes de démonstration

Tous les comptes créés par `peupler_demo` ont le mot de passe **`Ensiasd@2026`**.

| Identifiant | Rôle |
|---|---|
| `admin` | Administrateur (accès à `/admin/`) |
| `scolarite` | Service de scolarité |
| `enseignant1` … `enseignant3` | Enseignants |
| `etudiant1` … `etudiant10` | Étudiants de MGSI 2ème année (1–5 : G1, 6–10 : G2) |

Pour repartir de zéro : supprimer `db.sqlite3`, puis `migrate` et `peupler_demo`.

## Organisation du code

Une application Django par module du dossier de cadrage :

| Application | Contenu | Besoins |
|---|---|---|
| `comptes/` | Utilisateur avec rôle, connexion, tableau de bord, décorateur `role_requis` | BF01, BF16, US17 |
| `structure/` | Filières, niveaux, classes, groupes, matières, salles, affectations | BF11, BF12 |
| `emplois/` | Séances + **détection des conflits** (`Seance.conflits()`), abonnement iCalendar (`ical.py`) | BF13, BF14, BF15 |
| `ressources/` | Cours, TD, TP filtrés par filière et niveau | BF06, BF07 |
| `documents/` | Demandes de documents et cycle de vie des statuts | BF08 – BF10 |
| `absences/` | Appel par séance, total d'heures, justifications, export CSV, suivi par l'enseignant, relevé PDF (`releve.py`) | BF02 – BF05, US18 |
| `annonces/` | Annonces pour tout l'établissement, une filière ou une classe | — |
| `evaluations/` | Calendrier des examens, devoirs à rendre en ligne, rappels | — |
| `notifications/` | Notifications internes | — |

Autres dossiers : `config/` (paramètres, URL, validation et téléchargement des fichiers, données de test), `templates/` (pages HTML),
`static/` (thème `css/ent.css`, police Plus Jakarta Sans hébergée sur le site, logos).

## Fonctionnalités

Toutes les user stories du backlog (US01 à US18) sont réalisées, ainsi que les améliorations issues de l'audit.

| Rôle | Pages |
|---|---|
| **Étudiant** | Tableau de bord (séances du jour, échéances, annonces) · Emploi du temps de la semaine (annulations, rattrapages, jours fériés, examens) + abonnement depuis Google Agenda, Outlook ou le téléphone · Examens et rendus · Dépôt des devoirs · Cours/TD/TP de sa filière et de son niveau · Mes absences (heures par matière, retards, alertes de seuil) + justification, y compris après un refus, + relevé PDF · Demandes de documents + téléchargement · Annonces · Notifications · Mon compte |
| **Enseignant** | Tableau de bord (étudiants en alerte, échéances) · Emploi du temps + abonnement · Faire l'appel (présent / absent / retard, séances hebdomadaires et rattrapages) · Suivi des absences de ses étudiants, matière par matière · Programmer un examen · Publier un devoir, consulter et télécharger les rendus (ZIP) · Annonces à ses classes · Déposer / supprimer ses supports |
| **Scolarité** | Demandes de documents (attestation de scolarité générée en PDF, ajout du fichier après coup) · Justifications · Absences par classe + alertes + export CSV + relevé PDF de chaque étudiant · Calendrier des examens · Annonces · Statistiques · Import CSV des étudiants · Emplois du temps des classes |
| **Administrateur** | Administration `/admin/` (structure, comptes, affectations, séances, annulations, jours non travaillés) · Statistiques · Import CSV · Absences par classe + relevés PDF · Appel pour toute séance · Examens · Annonces |

### Règles importantes

**Sécurité**
- Les droits d'administration découlent uniquement du rôle ADMIN (`createsuperuser` crée un compte ADMIN).
- Connexion bloquée 15 minutes après 5 échecs (par identifiant et adresse IP). Les compteurs sont gardés dans la base (cache Django, table `cache_ent` créée par `migrate`) : ils survivent aux redémarrages du site.
- Mot de passe oublié : lien de réinitialisation envoyé par e-mail, au plus 3 fois par heure pour une même adresse. En développement, l'e-mail s'affiche dans la console du serveur ; en production, renseigner `DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`.
- Les fichiers déposés ne sont jamais publics, et leur contenu réel est vérifié (un exécutable renommé en `.pdf` est refusé).
- La session se termine à la fermeture du navigateur, et au plus tard 10 heures après la connexion (ordinateurs partagés).
- Bootstrap et Chart.js viennent d'un CDN, avec leur empreinte (`integrity`) : un fichier modifié sur le CDN serait refusé par le navigateur.
  Pour changer de version, recalculer l'empreinte (`openssl dgst -sha384 -binary fichier | openssl base64 -A`).

**Emploi du temps et appel**
- Détection des conflits de salle, d'enseignant et de classe/groupe ; un enseignant ne peut être planifié que sur une matière qui lui est affectée.
- Rattrapage = séance avec une date unique. Une annulation (admin › Annulations de séances) notifie l'enseignant et les étudiants.
- L'appel est impossible un jour non travaillé, pour une séance annulée, une date future ou hors de l'année universitaire.
- L'appel est enregistré d'un bloc (rien n'est gardé en cas d'erreur) ; un double clic ne l'enregistre qu'une fois.
- La durée d'une absence est figée au moment de l'appel. Un retard ne compte pas d'heures d'absence.
- L'appel ne modifie jamais une absence pour laquelle l'étudiant a déposé un justificatif.

**Seuils d'absence** (`SEUILS_ABSENCE` dans `config/settings.py`)
- Avertissement à 10 % et seuil critique à 25 % du volume horaire de la matière, en heures non justifiées.
- Chaque seuil franchi est notifié une seule fois à l'étudiant et à la scolarité.

**Annonces** (`/annonces/`)
- La scolarité et l'administrateur publient pour tout l'établissement, une filière ou une classe ; un enseignant, pour l'une de ses classes.
- Chaque annonce est notifiée à ses destinataires ; une annonce « importante » reste en tête de liste.
  Après sa date de fin (facultative), elle disparaît des listes.

**Examens, devoirs et rappels** (`/evaluations/`)
- Un examen ou un devoir vise une classe entière ou l'un de ses groupes, dans une matière ; un enseignant ne choisit que parmi ses affectations.
- Les étudiants concernés sont notifiés à la publication, puis rappelés deux jours avant l'échéance (une seule fois). Pour un devoir,
  seuls ceux qui n'ont encore rien déposé reçoivent le rappel.
- Les rappels partent à l'ouverture des tableaux de bord (pas de tâche planifiée sur la formule gratuite de PythonAnywhere) ;
  `python manage.py envoyer_rappels` fait la même chose depuis une tâche planifiée.
- Un nouveau dépôt remplace le précédent. Après la date limite, le dépôt est refusé, sauf si l'enseignant accepte les retards
  (le rendu est alors marqué « en retard »). Mêmes formats et même taille maximale que les ressources (`TAILLE_MAX_RESSOURCE_MO`).

**Abonnement à l'emploi du temps**
- Chaque étudiant ou enseignant crée, sur sa page « Emploi du temps », un lien secret vers un flux iCalendar (séances qui ont lieu,
  examens, dates limites des devoirs). « Changer de lien » rend l'ancien inutilisable (lien partagé par erreur).
- Les heures sont écrites en UTC à partir de la base des fuseaux horaires du serveur : celle-ci doit être à jour pour suivre
  les changements d'heure du Maroc (paquet `tzdata` de `requirements.txt`, et base du système).

**Suivi des absences et relevé**
- L'enseignant voit, pour chaque matière et classe qui lui sont affectées, les heures d'absence de chaque étudiant (toutes séances
  de la matière confondues) et son niveau d'alerte ; les plus absents en tête.
- Le relevé PDF reprend la page « Mes absences » : bilan par matière et détail chronologique. Il est informatif et ne remplace pas
  une attestation signée.

**Import CSV des étudiants** (`/comptes/importer/`)
- Colonnes `nom;prenom;cne;email;groupe` (un modèle est téléchargeable sur la page). L'identifiant est le CNE en minuscules.
- Import « tout ou rien » : la moindre erreur (CNE en double, groupe inconnu…) n'enregistre aucun compte.
- Un mot de passe provisoire est généré pour chacun ; il n'est affiché qu'une fois (CSV à télécharger) et doit être changé à la première connexion.

## Sauvegardes (BNF07)

```bash
python manage.py sauvegarder
```

Crée `sauvegardes/sauvegarde_ent_<date>.zip` (base + fichiers déposés, rendus de devoirs compris) et ne garde que les 14 dernières.
Pour une sauvegarde automatique chaque nuit sous Windows (à adapter au chemin du projet) :

```bash
schtasks /Create /SC DAILY /ST 02:00 /TN "Sauvegarde ENT ENSIASD" /TR "\"D:\projet gestion scolaire\.venv\Scripts\python.exe\" \"D:\projet gestion scolaire\manage.py\" sauvegarder"
```

Sous Linux : `0 2 * * * cd /chemin/du/projet && .venv/bin/python manage.py sauvegarder` dans la crontab.

Après la sauvegarde, `python manage.py purger_notifications` supprime les notifications de plus de 180 jours
(`--jours 90` pour changer la durée) : sans cela, la table grossit à chaque appel et à chaque annulation de séance.

## Pistes d'amélioration

- Notifications par e-mail en plus des notifications internes.
- Gestion des notes (hors périmètre du dossier de cadrage).

Le déploiement sur PythonAnywhere est décrit dans `deploiement/DEPLOIEMENT.md`.

## Tests

```bash
python manage.py test
pip install ruff && ruff check .   # qualité du code (règles dans pyproject.toml)
```

Avec Python 3.11.0, ajouter `-X no_debug_ranges` (`python -X no_debug_ranges manage.py test`) : cette version a un bug
d'affichage des erreurs, corrigé dans les versions 3.11.x suivantes. Le plus simple est d'installer la dernière 3.11.x.

GitHub Actions (`.github/workflows/tests.yml`) relance tout sur chaque pull request et à chaque fusion dans `main` :
Ruff, migrations à jour, tests, puis `check --deploy` et `collectstatic` en configuration de production.

## Règles de travail en équipe

- Une branche Git par user story (`us13-saisie-absences`), fusion par pull request.
- Lancer les tests avant chaque push ; une pull request ne se fusionne que si la vérification GitHub Actions est verte.
- Après une modification d'un `models.py` : `python manage.py makemigrations` et versionner la migration.
- Ne jamais versionner `db.sqlite3`, `media/` ni `.venv/` (déjà dans `.gitignore`).
