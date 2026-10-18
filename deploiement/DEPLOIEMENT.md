# Déploiement sur PythonAnywhere

Adresse du site : `https://<identifiant>.pythonanywhere.com` (formule gratuite).

## 1. Récupérer le code (console Bash de PythonAnywhere)

```bash
git clone https://github.com/<compte-github>/ent-ensiasd.git ~/ent-ensiasd
cd ~/ent-ensiasd
python3.11 -m venv ~/.virtualenvs/ent
~/.virtualenvs/ent/bin/pip install -r requirements.txt
```

## 2. Clé secrète (générée sur le serveur, jamais copiée ailleurs)

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))" > ~/.ent_cle_secrete && chmod 600 ~/.ent_cle_secrete
```

## 3. Application web (onglet « Web »)

1. *Add a new web app* › *Manual configuration* › *Python 3.11*.
2. *Virtualenv* : `/home/<identifiant>/.virtualenvs/ent`.
3. *WSGI configuration file* : remplacer le contenu par `deploiement/pythonanywhere_wsgi.py` (en remplaçant `<identifiant>`).
4. *Static files* : URL `/static/` → dossier `/home/<identifiant>/ent-ensiasd/staticfiles`.
   Ne **pas** ajouter de règle pour `/media/` : les fichiers déposés passent par des vues qui vérifient les droits.
5. *Force HTTPS* : activé.

## 4. Base de données et fichiers statiques (console Bash)

Les commandes `manage.py` doivent voir la même configuration que le site :

```bash
cd ~/ent-ensiasd
export DJANGO_DEBUG=0 DJANGO_SECRET_KEY_FILE=~/.ent_cle_secrete DJANGO_ALLOWED_HOSTS=<identifiant>.pythonanywhere.com
~/.virtualenvs/ent/bin/python manage.py migrate
~/.virtualenvs/ent/bin/python manage.py collectstatic --noinput
~/.virtualenvs/ent/bin/python manage.py peupler_demo --mot-de-passe-aleatoire   # notez le mot de passe affiché
```

Puis bouton **Reload** dans l'onglet « Web ».

## 5. Sauvegardes

Les tâches planifiées (onglet « Tasks ») sont réservées aux comptes payants. Avec la formule gratuite,
lancez la sauvegarde à la main (par exemple chaque semaine) dans une console Bash :

```bash
cd ~/ent-ensiasd
export DJANGO_DEBUG=0 DJANGO_SECRET_KEY_FILE=~/.ent_cle_secrete DJANGO_ALLOWED_HOSTS=<identifiant>.pythonanywhere.com
~/.virtualenvs/ent/bin/python manage.py sauvegarder
~/.virtualenvs/ent/bin/python manage.py purger_notifications   # notifications de plus de 180 jours
```

Les archives restent sur le même compte que le site : téléchargez-en une copie de temps en temps
(onglet « Files », dossier `ent-ensiasd/sauvegardes/`).

## Mettre à jour le site après une modification

```bash
cd ~/ent-ensiasd && git pull
export DJANGO_DEBUG=0 DJANGO_SECRET_KEY_FILE=~/.ent_cle_secrete DJANGO_ALLOWED_HOSTS=<identifiant>.pythonanywhere.com
~/.virtualenvs/ent/bin/pip install -r requirements.txt
~/.virtualenvs/ent/bin/python manage.py migrate
~/.virtualenvs/ent/bin/python manage.py collectstatic --noinput
```

Puis **Reload** dans l'onglet « Web ».

`collectstatic` est indispensable à chaque mise à jour : en production, les fichiers statiques portent une empreinte
dans leur nom (`ent.3f1a9c….css`), et une page qui utilise un fichier absent de `staticfiles/` renvoie une erreur 500.

`migrate` l'est aussi dès qu'une mise à jour ajoute des migrations (par exemple les applications `annonces` et
`evaluations`, ou le lien d'abonnement au calendrier) : sans elle, les nouvelles pages renvoient une erreur 500.

## Rappels des examens et des devoirs

Sans tâche planifiée, les rappels (deux jours avant un examen ou une date limite) partent quand un utilisateur ouvre
son tableau de bord. Avec un compte payant, ajoutez une tâche quotidienne (onglet « Tasks ») :

```bash
cd ~/ent-ensiasd && DJANGO_DEBUG=0 DJANGO_SECRET_KEY_FILE=~/.ent_cle_secrete DJANGO_ALLOWED_HOSTS=<identifiant>.pythonanywhere.com ~/.virtualenvs/ent/bin/python manage.py envoyer_rappels
```

## Limites de la formule gratuite

- Le site est désactivé s'il n'est pas prolongé **chaque mois** (bouton *Run until 1 month from today*, onglet « Web ») ; PythonAnywhere envoie un e-mail de rappel une semaine avant.
- Pas de tâches planifiées : les sauvegardes se lancent à la main (voir plus haut), les rappels partent à l'ouverture des tableaux de bord.
- Espace disque limité : les rendus de devoirs s'ajoutent aux justificatifs et aux supports de cours. Supprimer les devoirs
  des années passées (avec leurs rendus) après les avoir sauvegardés libère de la place.
- 100 secondes de calcul par jour pour les consoles (le site lui-même n'est pas concerné).
- Accès Internet sortant limité : l'envoi d'e-mails (mot de passe oublié) ne fonctionne qu'avec un serveur SMTP autorisé par PythonAnywhere.
