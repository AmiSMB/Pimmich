import json
import secrets
from werkzeug.security import generate_password_hash
import argparse
import sys

def generate_random_password(length=12):
    """
    Génère un mot de passe aléatoire sécurisé et facile à taper.
    Generate a secure random password that is easy to type.
    """
    # Alphabet sans caractères ambigus (I, l, 1, O, 0) et sans ponctuation pour faciliter la saisie
    # Exclude ambiguous characters (I, l, 1, O, 0) and punctuation to make it easier to type.
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    password = ''.join(secrets.choice(alphabet) for i in range(length))
    return password

def create_credentials_file(output_path, username="admin", language="fr"):
    """
    Génère un nouveau mot de passe, le hache et crée le fichier credentials.json.
    Generate a new password, hash it, and create the credentials.json file.
    """
    password = generate_random_password()
    flask_secret_key = secrets.token_hex(24) # Génère une clé sécurisée de 24 octets pour Flask
    # Generate a secure 24-byte key for Flask.
    
    # Hacher le mot de passe en utilisant une méthode sécurisée.
    # Hash the password using a secure method.
    # Werkzeug gère automatiquement le salage (salt).
    # Werkzeug handles salting automatically.
    password_hash = generate_password_hash(password)
    
    credentials = {
        "username": username,
        "password_hash": password_hash,
        "flask_secret_key": flask_secret_key
    }
    
    if language == "en":
        created_message = "✅ Secure credentials file created."
        credentials_warning = "⚠️  SAVE THESE CREDENTIALS; THEY WILL NOT BE SHOWN AGAIN  ⚠️"
        username_label = "Username"
        password_label = "Password"
        error_message = f"ERROR: Could not create the credentials file at '{output_path}'."
        details_label = "Details"
    else:
        created_message = "✅ Fichier d'identification sécurisé créé."
        credentials_warning = "⚠️  NOTEZ CES IDENTIFIANTS, ILS NE SERONT PLUS AFFICHÉS  ⚠️"
        username_label = "Utilisateur"
        password_label = "Mot de passe"
        error_message = f"ERREUR: Impossible de créer le fichier d'identification à '{output_path}'."
        details_label = "Détails"

    try:
        with open(output_path, 'w') as f:
            json.dump(credentials, f, indent=2)
        
        # Afficher les identifiants pour que l'utilisateur les note.
        # Display the credentials so the user can write them down.
        # C'est la seule fois où le mot de passe en clair sera affiché.
        # This is the only time the password will be shown in plain text.
        print("\n" + "="*60, file=sys.stderr)
        print(created_message, file=sys.stderr)
        print("\n" + "-"*60, file=sys.stderr)
        print(credentials_warning, file=sys.stderr)
        print(f"   {username_label}: {username}", file=sys.stderr)
        print(f"   {password_label}: {password}", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)

    except Exception as e:
        print(error_message, file=sys.stderr)
        print(f"{details_label}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crée un fichier credentials.json sécurisé avec un mot de passe aléatoire. / Create a secure credentials.json file with a random password."
    )
    parser.add_argument(
        '--output',
        required=True,
        help="Chemin complet du fichier credentials.json à créer. / Full path of the credentials.json file to create."
    )
    parser.add_argument(
        '--username',
        default='admin',
        help="Nom de l'utilisateur à créer (par défaut: admin). / Username to create (default: admin)."
    )
    parser.add_argument(
        '--language',
        choices=('fr', 'en'),
        default='fr',
        help="Langue des messages affichés / Language for output messages."
    )
    
    args = parser.parse_args()
    
    create_credentials_file(args.output, args.username, args.language)
