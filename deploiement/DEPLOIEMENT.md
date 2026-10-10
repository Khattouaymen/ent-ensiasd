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
~/.virtualenvs/ent/bin/python manage.py peupler_demo --mot-de-passe "<mot de passe à communiquer aux collègues>"
```

Puis bouton **Reload** dans l'onglet « Web ».

## 5. Sauvegarde quotidienne (onglet « Tasks »)

Tâche quotidienne :

```bash
cd ~/ent-ensiasd && DJANGO_DEBUG=0 DJANGO_SECRET_KEY_FILE=~/.ent_cle_secrete DJANGO_ALLOWED_HOSTS=<identifiant>.pythonanywhere.com ~/.virtualenvs/ent/bin/python manage.py sauvegarder
```

## Mettre à jour le site après une modification

```bash
cd ~/ent-ensiasd && git pull
export DJANGO_DEBUG=0 DJANGO_SECRET_KEY_FILE=~/.ent_cle_secrete DJANGO_ALLOWED_HOSTS=<identifiant>.pythonanywhere.com
~/.virtualenvs/ent/bin/pip install -r requirements.txt
~/.virtualenvs/ent/bin/python manage.py migrate
~/.virtualenvs/ent/bin/python manage.py collectstatic --noinput
```

Puis **Reload** dans l'onglet « Web ».

## Limites de la formule gratuite

- Le site est désactivé s'il n'est pas prolongé tous les 3 mois (bouton *Run until 3 months from today*, onglet « Web »).
- Accès Internet sortant limité : l'envoi d'e-mails (mot de passe oublié) ne fonctionne qu'avec un serveur SMTP autorisé par PythonAnywhere.
- Le blocage après échecs de connexion compte les essais en mémoire : il est remis à zéro à chaque redémarrage du site.
