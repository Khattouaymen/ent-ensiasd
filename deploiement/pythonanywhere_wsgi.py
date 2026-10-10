# Modèle du fichier WSGI pour PythonAnywhere (onglet « Web » › lien « WSGI configuration file »).
# Remplacez tout le contenu de ce fichier sur PythonAnywhere par ce modèle, puis remplacez
# <identifiant> par votre nom d'utilisateur PythonAnywhere.
#
# La clé secrète n'est pas écrite ici : générez-la une fois dans une console Bash PythonAnywhere avec
#   python3 -c "import secrets; print(secrets.token_urlsafe(50))" > ~/.ent_cle_secrete && chmod 600 ~/.ent_cle_secrete

import os
import sys

CHEMIN_PROJET = "/home/<identifiant>/ent-ensiasd"
if CHEMIN_PROJET not in sys.path:
    sys.path.insert(0, CHEMIN_PROJET)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DJANGO_DEBUG"] = "0"
os.environ["DJANGO_SECRET_KEY_FILE"] = "/home/<identifiant>/.ent_cle_secrete"
os.environ["DJANGO_ALLOWED_HOSTS"] = "<identifiant>.pythonanywhere.com"
# PythonAnywhere transmet l'adresse IP réelle du visiteur dans cet en-tête.
os.environ["DJANGO_ENTETE_IP_CLIENT"] = "HTTP_X_REAL_IP"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
