#!/bin/bash

# Usage : ./setup.sh [fr|en] (français par défaut)
# Usage: ./setup.sh [fr|en] (French by default).
APP_LANGUAGE="${1:-fr}"
case "$APP_LANGUAGE" in
    fr|en) ;;
    *) APP_LANGUAGE="fr" ;;
esac

say() {
    local french_text="$1"
    local english_text="$2"
    if [ "$APP_LANGUAGE" = "en" ]; then
        printf '%s\n' "$english_text"
    else
        printf '%s\n' "$french_text"
    fi
}

say "=== [1/12] Mise à jour de la liste des paquets (apt update) ===" "=== [1/12] Updating the package list (apt update) ==="
sudo apt update


say "=== [2/12] Installation des dépendances ===" "=== [2/12] Installing dependencies ==="
# Remplacement de libatlas-base-dev (obsolète sur Debian 12+) par libopenblas-dev pour la compilation de numpy.
# Replace libatlas-base-dev (obsolete on Debian 12+) with libopenblas-dev to build NumPy.
if ! sudo apt install -y sway xterm python3 python3-venv python3-pip libjpeg-dev libopenjp2-7-dev libtiff-dev libopenblas-dev ffmpeg git cifs-utils smbclient network-manager jq mpv gettext portaudio19-dev unzip libheif-dev; then
    say "L'installation avec portaudio19-dev a échoué. Tentative avec libportaudio-dev..." "Installation with portaudio19-dev failed. Trying libportaudio-dev instead..."
    # Fallback pour les futures versions de Debian/Raspberry Pi OS où le paquet pourrait être renommé
    # Fallback for future Debian/Raspberry Pi OS versions where the package may be renamed.
    sudo apt install -y sway xterm python3 python3-venv python3-pip libjpeg-dev libopenjp2-7-dev libtiff-dev libopenblas-dev ffmpeg git cifs-utils smbclient network-manager jq mpv gettext libportaudio-dev unzip libheif-dev
fi

say "=== [2.5/12] Configuration de la langue française (locale fr_FR) ===" "=== [2.5/12] Configuring the French locale (fr_FR) ==="
if [ -f "/etc/locale.gen" ]; then
    if ! grep -q "^fr_FR.UTF-8 UTF-8" /etc/locale.gen; then
        say "Activation de la locale fr_FR.UTF-8..." "Enabling the fr_FR.UTF-8 locale..."
        sudo sed -i 's/# fr_FR.UTF-8 UTF-8/fr_FR.UTF-8 UTF-8/' /etc/locale.gen
        sudo locale-gen
    else
        say "✅ La locale fr_FR.UTF-8 est déjà activée." "✅ The fr_FR.UTF-8 locale is already enabled."
    fi
fi


say "=== [3/12] Désactivation de l'économie d'énergie Wi-Fi ===" "=== [3/12] Disabling Wi-Fi power saving ==="
# Installation conditionnelle de RPi.GPIO (pour le ventilateur)
# Install RPi.GPIO conditionally (for fan control).
if [ -f "/etc/os-release" ]; then
    source /etc/os-release
    if [[ "$ID" == "raspbian" || "$ID" == "debian" ]]; then
        say "Détection de Raspberry Pi OS (ou Debian). Installation de RPi.GPIO..." "Raspberry Pi OS (or Debian) detected. Installing RPi.GPIO..."
        sudo apt-get install -y python3-rpi.gpio
    fi
fi

CONF_FILE="/etc/NetworkManager/conf.d/99-disable-wifi-powersave.conf"
if [ ! -f "$CONF_FILE" ]; then
    say "Création du fichier de configuration pour désactiver l'économie d'énergie Wi-Fi..." "Creating the configuration file to disable Wi-Fi power saving..."
    sudo tee "$CONF_FILE" > /dev/null <<'EOL'
[connection]
wifi.powersave = 2
EOL
    say "✅ Économie d'énergie Wi-Fi désactivée. Redémarrage de NetworkManager..." "✅ Wi-Fi power saving disabled. Restarting NetworkManager..."
    sudo systemctl restart NetworkManager
    sleep 2 # Petite pause pour laisser le service redémarrer
    # Briefly wait for the service to restart.
else
    say "✅ L'économie d'énergie Wi-Fi est déjà désactivée." "✅ Wi-Fi power saving is already disabled."
fi

say "=== [4/12] Configuration automatique du fuseau horaire ===" "=== [4/12] Configuring the time zone automatically ==="
# Valeur par défaut
# Default value.
DETECTED_TIMEZONE="UTC"
# Source par défaut
# Default source.
TIMEZONE_SOURCE="fallback"

say "Tentative de détection du fuseau horaire via l'adresse IP publique..." "Trying to detect the time zone from the public IP address..."
# Utilise l'API ip-api.com et l'outil jq pour extraire le fuseau horaire
# Use the ip-api.com API and jq to extract the time zone.
TIMEZONE_FROM_API=$(curl -s http://ip-api.com/json | jq -r '.timezone')

# Vérifie si la détection a réussi
# Check whether detection succeeded.
if [ -n "$TIMEZONE_FROM_API" ] && [ "$TIMEZONE_FROM_API" != "null" ]; then
    say "Fuseau horaire détecté : $TIMEZONE_FROM_API" "Detected time zone: $TIMEZONE_FROM_API"
    sudo timedatectl set-timezone "$TIMEZONE_FROM_API"
    DETECTED_TIMEZONE="$TIMEZONE_FROM_API"
    TIMEZONE_SOURCE="auto"
    say "✅ Fuseau horaire configuré automatiquement. Heure actuelle : $(date)" "✅ Time zone configured automatically. Current time: $(date)"
else
    say "⚠️ La détection automatique a échoué. Le fuseau horaire sera réglé sur UTC par défaut." "⚠️ Automatic detection failed. The time zone will default to UTC."
    sudo timedatectl set-timezone UTC
    say "Vous pourrez le changer manuellement plus tard avec : sudo timedatectl set-timezone Votre/Ville" "You can change it manually later with: sudo timedatectl set-timezone Your/City"
fi

say "=== [5/12] Installation et configuration de NGINX pour redirection sans :5000 ===" "=== [5/12] Installing and configuring NGINX to serve Pimmich without :5000 ==="
# Installer NGINX si ce n'est pas déjà fait
# Install NGINX if it is not already installed.
if ! command -v nginx &> /dev/null; then
    say "Installation de NGINX..." "Installing NGINX..."
    sudo apt install -y nginx
else
    say "✅ NGINX est déjà installé." "✅ NGINX is already installed."
fi

# Supprimer la config par défaut si elle existe
# Remove the default configuration if it exists.
if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
    say "⛔ Fichier de configuration par défaut supprimé." "⛔ Default configuration file removed."
fi

# Créer une nouvelle config pour Pimmich
# Create a new configuration for Pimmich.
sudo tee /etc/nginx/sites-available/pimmich > /dev/null <<'EOL'
server {
    listen 80;
    server_name _;

    client_max_body_size 200M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # Augmenter les timeouts pour les opérations longues comme l'import de vidéos
        # Increase timeouts for long-running operations such as video imports.
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }
}
EOL

# Activer la nouvelle config
# Enable the new configuration.
if [ ! -f /etc/nginx/sites-enabled/pimmich ]; then
    sudo ln -s /etc/nginx/sites-available/pimmich /etc/nginx/sites-enabled/
    say "✅ Configuration Pimmich activée dans NGINX." "✅ Pimmich configuration enabled in NGINX."
fi

# Redémarrer NGINX
# Restart NGINX.
sudo systemctl restart nginx
say "✅ NGINX redémarré et prêt." "✅ NGINX restarted and ready."

say "=== [6/12] Création de l’environnement Python ===" "=== [6/12] Creating the Python environment ==="
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate

say "Mise à jour de pip..." "Updating pip..."
pip install --default-timeout=1000 --retries=10 --upgrade pip

say "Installation des dépendances de requirements.txt..." "Installing dependencies from requirements.txt..."
if ! pip install --default-timeout=1000 --retries=10 -r requirements.txt; then
    say "❌ Échec de l'installation des dépendances Python de base !" "❌ Failed to install the base Python dependencies!"
    exit 1
fi

say "Installation de la bibliothèque pour les QR codes..." "Installing the QR code library..."
if ! pip install --default-timeout=1000 --retries=10 "qrcode[pil]"; then
    say "❌ Échec de l'installation de qrcode[pil] !" "❌ Failed to install qrcode[pil]!"
    exit 1
fi

say "Mise à jour de la bibliothèque pour le bot Telegram..." "Updating the Telegram bot library..."
if ! pip install --default-timeout=1000 --retries=10 --upgrade python-telegram-bot; then
    say "❌ Échec de la mise à jour de python-telegram-bot !" "❌ Failed to update python-telegram-bot!"
    exit 1
fi

# Détecter le modèle du Raspberry Pi
# Detect the Raspberry Pi model.
PI_MODEL=""
if [ -f /proc/device-tree/model ]; then
    MODEL_STR=$(cat /proc/device-tree/model)
    if [[ "$MODEL_STR" =~ "Raspberry Pi 4" ]]; then
        PI_MODEL="4"
    elif [[ "$MODEL_STR" =~ "Raspberry Pi 5" ]]; then
        PI_MODEL="5"
    elif [[ "$MODEL_STR" =~ "Raspberry Pi 3" ]]; then
        PI_MODEL="3"
    elif [[ "$MODEL_STR" =~ "Raspberry Pi 2" ]]; then
        PI_MODEL="2"
    elif [[ "$MODEL_STR" =~ "Zero" ]]; then
        PI_MODEL="1"
    else
        PI_MODEL="1"
    fi
fi

ARCH=$(uname -m)
if [[ "$ARCH" == "armv6l" || "$PI_MODEL" == "1" || "$PI_MODEL" == "2" ]]; then
    say "⚠️ Raspberry Pi 1/2/Zero ou architecture armv6l détectée." "⚠️ Raspberry Pi 1/2/Zero or armv6l architecture detected."
    say "⚠️ Le contrôle vocal (Vosk/Porcupine) n'est pas pris en charge ou est trop gourmand sur cette carte." "⚠️ Voice control (Vosk/Porcupine) is unsupported or too resource-intensive on this device."
    say "⚠️ Les dépendances vocales ne seront pas installées." "⚠️ Voice-control dependencies will not be installed."
    
    # On installe tout de même le son de notification par défaut
    # Install the default notification sound anyway.
    say "=== [NOUVEAU] Téléchargement du son de notification vocale ===" "=== Downloading the voice notification sound ==="
    SOUNDS_DIR="static/sounds"
    NOTIFICATION_SOUND="$SOUNDS_DIR/ding.wav"
    if [ ! -f "$NOTIFICATION_SOUND" ]; then
        say "Son de notification non trouvé. Téléchargement..." "Notification sound not found. Downloading..."
        mkdir -p "$SOUNDS_DIR"
        wget -q -O "$NOTIFICATION_SOUND" "https://github.com/actions/sounds/raw/main/sounds/notification.wav"
        say "✅ Son de notification installé." "✅ Notification sound installed."
    else
        say "✅ Le son de notification est déjà présent." "✅ The notification sound is already present."
    fi
else
    say "Installation de pillow-heif pour la prise en charge des photos HEIC (iPhone)..." "Installing pillow-heif for HEIC photo support (iPhone)..."
    if ! pip install pillow-heif; then
        say "⚠️ Avertissement : l'installation de pillow-heif a échoué. La prise en charge de HEIC/HEIF sera désactivée." "⚠️ Warning: pillow-heif installation failed. HEIC/HEIF support will be disabled."
    else
        say "✅ pillow-heif installé avec succès." "✅ pillow-heif installed successfully."
    fi

    say "Installation des bibliothèques pour le contrôle vocal..." "Installing voice-control libraries..."
    if ! pip install vosk sounddevice numpy thefuzz python-Levenshtein pygame num2words; then
        say "❌ Échec de l'installation des bibliothèques de contrôle vocal !" "❌ Failed to install the voice-control libraries!"
        exit 1
    fi

    say "Réinstallation forcée de pvporcupine pour inclure les modèles de langue..." "Force-reinstalling pvporcupine to include language models..."
    if ! pip install --force-reinstall --no-cache-dir pvporcupine; then
        say "❌ Échec de l'installation de pvporcupine !" "❌ Failed to install pvporcupine!"
        exit 1
    fi
    say "Vérification manuelle et téléchargement du modèle de langue français s'il est absent..." "Checking for the French language model and downloading it if missing..."

    SITE_PACKAGES_DIR=$(python3 -c "import site; print(site.getsitepackages()[0])")
    FR_MODEL_PATH="$SITE_PACKAGES_DIR/pvporcupine/lib/common/porcupine_params_fr.pv"

    if [ ! -f "$FR_MODEL_PATH" ]; then
        say "⚠️ Le modèle de langue français est absent. Tentative de téléchargement manuel..." "⚠️ The French language model is missing. Trying a manual download..."
        FR_MODEL_URL="https://github.com/Picovoice/porcupine/raw/master/lib/common/porcupine_params_fr.pv"
        DEST_DIR=$(dirname "$FR_MODEL_PATH")
        mkdir -p "$DEST_DIR"
        if ! wget -q -O "$FR_MODEL_PATH" "$FR_MODEL_URL"; then
            say "❌ ERREUR : le téléchargement manuel du modèle de langue a échoué. Le contrôle vocal ne fonctionnera pas." "❌ ERROR: Manual download of the language model failed. Voice control will not work."
        else
            say "✅ Modèle de langue français téléchargé et installé manuellement." "✅ French language model downloaded and installed manually."
        fi
    else
        say "✅ Le modèle de langue français est déjà présent." "✅ The French language model is already present."
    fi

    say "=== [NOUVEAU] Téléchargement du son de notification vocale ===" "=== Downloading the voice notification sound ==="
    SOUNDS_DIR="static/sounds"
    NOTIFICATION_SOUND="$SOUNDS_DIR/ding.wav"
    if [ ! -f "$NOTIFICATION_SOUND" ]; then
        say "Son de notification non trouvé. Téléchargement..." "Notification sound not found. Downloading..."
        mkdir -p "$SOUNDS_DIR"
        wget -q -O "$NOTIFICATION_SOUND" "https://github.com/actions/sounds/raw/main/sounds/notification.wav"
        say "✅ Son de notification installé." "✅ Notification sound installed."
    else
        say "✅ Le son de notification est déjà présent." "✅ The notification sound is already present."
    fi

    say "=== [NOUVEAU] Téléchargement du modèle de reconnaissance vocale (Vosk) ===" "=== Downloading the speech-recognition model (Vosk) ==="
    MODELS_DIR="models"
    VOSK_MODEL_DIR="$MODELS_DIR/vosk-model-small-fr-0.22"
    VOSK_ZIP_FILE="$MODELS_DIR/vosk-model-fr.zip"

    if [ ! -d "$VOSK_MODEL_DIR" ]; then
        say "Modèle Vosk non trouvé. Téléchargement..." "Vosk model not found. Downloading..."
        mkdir -p "$MODELS_DIR"
        wget -q --show-progress -O "$VOSK_ZIP_FILE" "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip"
        unzip -o "$VOSK_ZIP_FILE" -d "$MODELS_DIR"
        rm "$VOSK_ZIP_FILE"
        say "✅ Modèle Vosk français installé." "✅ French Vosk model installed."
    else
        say "✅ Le modèle Vosk français est déjà présent." "✅ The French Vosk model is already present."
    fi

    say "=== [NOUVEAU] Téléchargement du modèle de reconnaissance vocale anglais (Vosk) ===" "=== Downloading the English speech-recognition model (Vosk) ==="
    VOSK_MODEL_EN_DIR="$MODELS_DIR/vosk-model-small-en-us-0.15"
    VOSK_ZIP_EN_FILE="$MODELS_DIR/vosk-model-en.zip"

    if [ ! -d "$VOSK_MODEL_EN_DIR" ]; then
        say "Modèle Vosk anglais non trouvé. Téléchargement..." "English Vosk model not found. Downloading..."
        mkdir -p "$MODELS_DIR"
        wget -q --show-progress -O "$VOSK_ZIP_EN_FILE" "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
        unzip -o "$VOSK_ZIP_EN_FILE" -d "$MODELS_DIR"
        rm "$VOSK_ZIP_EN_FILE"
        say "✅ Modèle Vosk anglais installé." "✅ English Vosk model installed."
    else
        say "✅ Le modèle Vosk anglais est déjà présent." "✅ The English Vosk model is already present."
    fi
fi

say "=== [7/12] Création de l'arborescence des dossiers nécessaires ===" "=== [7/12] Creating the required directory structure ==="
mkdir -p logs
mkdir -p cache
mkdir -p static/photos
mkdir -p static/prepared
mkdir -p static/pending_uploads
mkdir -p config
say "✅ Arborescence des dossiers créée." "✅ Directory structure created."

# Corriger les permissions même si script lancé avec sudo
# Set correct permissions even when the script is run with sudo.
REAL_USER=$(logname)
sudo chown -R "$REAL_USER:$REAL_USER" static logs cache config
chmod -R u+rwX static logs cache config

say "=== [8/12] Création du fichier d'identification sécurisé ===" "=== [8/12] Creating the secure credentials file ==="
CREDENTIALS_FILE="/boot/firmware/credentials.json"
VENV_PYTHON="venv/bin/python3"

if [ ! -f "$CREDENTIALS_FILE" ]; then
    say "Génération d'un mot de passe aléatoire et création du fichier d'identification..." "Generating a random password and creating the credentials file..."
    # On utilise `sudo` avec le chemin complet vers le python du venv.
    # Use `sudo` with the full path to the virtual environment's Python interpreter.
    # L'option -E de sudo préserve l'environnement, ce qui peut aider.
    # The sudo -E option preserves the environment, which may be helpful.
    # Le script python affichera lui-même le mot de passe généré.
    # The Python script will display the generated password.
    sudo -E "$VENV_PYTHON" utils/create_initial_user.py --output "$CREDENTIALS_FILE"
    
    say "🔑 Configuration des droits sudo (sécurité, redémarrage, arrêt)..." "🔑 Configuring sudo permissions (security, reboot, shutdown)..."
    SUDOERS_CONF="/etc/sudoers.d/pimmich-auth"
    # Autorisations NOPASSWD pour toutes les fonctions critiques (Réseau, Disques, Système)
    # Configure NOPASSWD permissions for critical functions (network, disks, and system).
    COMMANDS="/usr/bin/tee $CREDENTIALS_FILE, /usr/sbin/reboot, /usr/sbin/shutdown, /usr/bin/nmcli, /usr/bin/raspi-config, /usr/bin/mount, /usr/bin/umount, /usr/bin/timedatectl"
    echo "$REAL_USER ALL=(ALL) NOPASSWD: $COMMANDS" | sudo tee "$SUDOERS_CONF" > /dev/null
    sudo chmod 440 "$SUDOERS_CONF"
else
    say "✅ Le fichier d'identification $CREDENTIALS_FILE existe déjà. Aucune modification." "✅ Credentials file $CREDENTIALS_FILE already exists. No changes made."
fi

say "=== [9/12] Configuration du démarrage en mode console (CLI) ===" "=== [9/12] Configuring console-mode startup (CLI) ==="
sudo raspi-config nonint do_boot_behaviour B2
say "✅ Système configuré pour démarrer en mode console avec auto-login." "✅ System configured to start in console mode with auto-login."


say "=== [10/12] Configuration du lancement automatique de Sway ===" "=== [10/12] Configuring Sway to start automatically ==="
# Récupération du dossier home de l'utilisateur réel
# Get the home directory of the actual user.
USER_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
BASH_PROFILE="$USER_HOME/.bash_profile"
if ! grep -q 'exec sway' "$BASH_PROFILE"; then
    echo 'if [[ -z $DISPLAY ]] && [[ $(tty) = /dev/tty1 ]]; then' >> "$BASH_PROFILE"
    echo '  exec sway' >> "$BASH_PROFILE"
    echo 'fi' >> "$BASH_PROFILE"
    say "Ajout du démarrage automatique de Sway dans $BASH_PROFILE" "Added automatic Sway startup to $BASH_PROFILE"
else
    say "✅ Sway est déjà configuré pour se lancer automatiquement." "✅ Sway is already configured to start automatically."
fi

say "=== [11/12] Configuration du lancement automatique de Pimmich dans Sway ===" "=== [11/12] Configuring Pimmich to start automatically in Sway ==="
SWAY_CONFIG_DIR="$USER_HOME/.config/sway"
SWAY_CONFIG_FILE="$SWAY_CONFIG_DIR/config"
mkdir -p "$SWAY_CONFIG_DIR"

# Chemin absolu vers le script de démarrage
# Absolute path to the startup script.
INSTALL_DIR=$(pwd)
START_SCRIPT="$INSTALL_DIR/start_pimmich.sh"

# Rendre exécutable
# Make the startup script executable.
chmod +x "$START_SCRIPT"

# Ajout de l'exec_always si absent
# Add the exec_always command if it is not already present.
if ! grep -q 'start_pimmich.sh' "$SWAY_CONFIG_FILE" 2>/dev/null; then
    echo "exec_always --no-startup-id $START_SCRIPT $APP_LANGUAGE" >> "$SWAY_CONFIG_FILE"
    say "Ajout de start_pimmich.sh dans la configuration Sway (langue : $APP_LANGUAGE)." "Added start_pimmich.sh to the Sway configuration (language: $APP_LANGUAGE)."
else
    sed -i -E "/start_pimmich\\.sh/s#(start_pimmich\\.sh)([[:space:]]+(fr|en))?\$#\\1 $APP_LANGUAGE#" "$SWAY_CONFIG_FILE"
    say "✅ start_pimmich.sh est déjà présent dans la configuration Sway." "✅ start_pimmich.sh is already present in the Sway configuration."
fi

# Configuration des règles de fenêtres pour assurer que les vidéos mpv passent au premier plan
# Configure window rules so mpv videos appear in the foreground.
if ! grep -q 'app_id="mpv"' "$SWAY_CONFIG_FILE" 2>/dev/null; then
    echo 'for_window [app_id="mpv"] floating enable, border none, fullscreen enable' >> "$SWAY_CONFIG_FILE"
    echo 'for_window [class="python3"] floating enable, border none, fullscreen enable' >> "$SWAY_CONFIG_FILE"
fi

say "=== [12/12] Installation terminée ===" "=== [12/12] Installation complete ==="
say "✅ Installation terminée. Redémarrez pour lancer automatiquement Sway et Pimmich." "✅ Installation complete. Restart to launch Sway and Pimmich automatically."
