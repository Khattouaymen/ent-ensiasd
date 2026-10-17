# ENT ENSIASD – Système de gestion d'un établissement scolaire

Projet MGSI S3 (2026/2027) – ENSIASD Taroudant.
Plateforme web : absences, ressources pédagogiques, demandes de documents, classes et emplois du temps.

**Technologies :** Python 3.11 · Django 5.2 LTS · SQLite · Bootstrap 5

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
| `emplois/` | Séances + **détection des conflits** (`Seance.conflits()`) | BF13, BF14, BF15 |
| `ressources/` | Cours, TD, TP filtrés par filière et niveau | BF06, BF07 |
| `documents/` | Demandes de documents et cycle de vie des statuts | BF08 – BF10 |
| `absences/` | Appel par séance, total d'heures, justifications, export CSV | BF02 – BF05, US18 |
| `notifications/` | Notifications internes | — |

Autres dossiers : `config/` (paramètres, URL, validation et téléchargement des fichiers, données de test), `templates/` (pages HTML), `static/` (CSS).

## Fonctionnalités

Toutes les user stories du backlog (US01 à US18) sont réalisées, ainsi que les améliorations issues de l'audit.

| Rôle | Pages |
|---|---|
| **Étudiant** | Tableau de bord · Emploi du temps de la semaine (annulations, rattrapages, jours fériés) · Cours/TD/TP de sa filière et de son niveau · Mes absences (heures par matière, retards, alertes de seuil) + justification, y compris après un refus · Demandes de documents + téléchargement · Notifications · Mon compte |
| **Enseignant** | Tableau de bord · Emploi du temps · Faire l'appel (présent / absent / retard, séances hebdomadaires et rattrapages) · Déposer / supprimer ses supports |
| **Scolarité** | Demandes de documents (attestation de scolarité générée en PDF, ajout du fichier après coup) · Justifications · Absences par classe + alertes + export CSV · Statistiques · Import CSV des étudiants · Emplois du temps des classes |
| **Administrateur** | Administration `/admin/` (structure, comptes, affectations, séances, annulations, jours non travaillés) · Statistiques · Import CSV · Absences par classe · Appel pour toute séance |

### Règles importantes

**Sécurité**
- Les droits d'administration découlent uniquement du rôle ADMIN (`createsuperuser` crée un compte ADMIN).
- Connexion bloquée 15 minutes après 5 échecs (par identifiant et adresse IP). Les compteurs sont gardés dans la base (cache Django, table `cache_ent` créée par `migrate`) : ils survivent aux redémarrages du site.
- Mot de passe oublié : lien de réinitialisation envoyé par e-mail, au plus 3 fois par heure pour une même adresse. En développement, l'e-mail s'affiche dans la console du serveur ; en production, renseigner `DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`.
- Les fichiers déposés ne sont jamais publics, et leur contenu réel est vérifié (un exécutable renommé en `.pdf` est refusé).

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

**Import CSV des étudiants** (`/comptes/importer/`)
- Colonnes `nom;prenom;cne;email;groupe` (un modèle est téléchargeable sur la page). L'identifiant est le CNE en minuscules.
- Import « tout ou rien » : la moindre erreur (CNE en double, groupe inconnu…) n'enregistre aucun compte.
- Un mot de passe provisoire est généré pour chacun ; il n'est affiché qu'une fois (CSV à télécharger) et doit être changé à la première connexion.

## Sauvegardes (BNF07)

```bash
python manage.py sauvegarder
```

Crée `sauvegardes/sauvegarde_ent_<date>.zip` (base + fichiers déposés) et ne garde que les 14 dernières.
Pour une sauvegarde automatique chaque nuit sous Windows (à adapter au chemin du projet) :

```bash
schtasks /Create /SC DAILY /ST 02:00 /TN "Sauvegarde ENT ENSIASD" /TR "\"D:\projet gestion scolaire\.venv\Scripts\python.exe\" \"D:\projet gestion scolaire\manage.py\" sauvegarder"
```

Sous Linux : `0 2 * * * cd /chemin/du/projet && .venv/bin/python manage.py sauvegarder` dans la crontab.

Après la sauvegarde, `python manage.py purger_notifications` supprime les notifications de plus de 180 jours
(`--jours 90` pour changer la durée) : sans cela, la table grossit à chaque appel et à chaque annulation de séance.

## Pistes d'amélioration

- Déploiement (PythonAnywhere, Render…) avec `DJANGO_DEBUG=0`, une vraie `DJANGO_SECRET_KEY` et `collectstatic`.
- Notifications par e-mail en plus des notifications internes.
- Gestion des notes et des examens (hors périmètre du dossier de cadrage).

## Tests

```bash
python -X no_debug_ranges manage.py test
```

L'option `-X no_debug_ranges` contourne un bug d'affichage des erreurs propre à Python 3.11.0 (corrigé dans les versions 3.11.x suivantes).

## Règles de travail en équipe

- Une branche Git par user story (`us13-saisie-absences`), fusion par pull request.
- Lancer les tests avant chaque push.
- Après une modification d'un `models.py` : `python manage.py makemigrations` et versionner la migration.
- Ne jamais versionner `db.sqlite3`, `media/` ni `.venv/` (déjà dans `.gitignore`).
