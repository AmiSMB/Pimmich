#!/bin/bash

# Usage : ./start_pimmich.sh [fr|en|es|de|ja]
# Usage: ./start_pimmich.sh [fr|en|es|de|ja]
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_LANGUAGE="${1:-$(python3 -c 'import json, pathlib, sys; p=pathlib.Path(sys.argv[1]); c=json.loads(p.read_text()) if p.exists() else {}; print(c.get("ui_language", "fr"))' "$APP_DIR/config/config.json" 2>/dev/null)}"
case "$APP_LANGUAGE" in
    fr|en|es|de|ja) ;;
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

# Ce script est le point d'entrée principal de Pimmich, géré par Sway.
# This script is the main entry point for Pimmich, managed by Sway.
# Il assure qu'une seule instance de l'application est en cours et gère les redémarrages.
# It ensures that only one application instance runs and handles restarts.

# Code de sortie spécial pour demander un redémarrage
# Special exit code used to request a restart.
RESTART_CODE=42

# Empêcher les instances multiples
# Prevent multiple instances from running.
LOCK_FILE="/tmp/pimmich_app.lock"
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    if ps -p "$PID" > /dev/null; then
        say "📟📟$(date +'%d-%m %H:%M:%S') 📟 ❌ Instance déjà en cours (PID: $PID). Abandon." "📟📟$(date +'%d-%m %H:%M:%S') 📟 ❌ Instance already running (PID: $PID). Exiting." >> logs/pimmich.log
        exit 1
    fi
fi
echo $$ > "$LOCK_FILE"

# Se placer dans le répertoire du script pour que les chemins relatifs fonctionnent
# Change to the script directory so relative paths work.
cd "$APP_DIR" || exit 1

# S'assurer que le dossier de logs existe
# Ensure the log directory exists.
mkdir -p logs

cleanup() {
    say "📟📟$(date +'%d-%m %H:%M:%S') 📟 🧹 Nettoyage des processus Pimmich existants..." "📟📟$(date +'%d-%m %H:%M:%S') 📟 🧹 Cleaning up existing Pimmich processes..." >> logs/pimmich.log
    # Tuer le processus de contrôle vocal s'il est en cours
    # Stop the voice-control process if it is running.
    if [ -f /tmp/pimmich_voice_control.pid ]; then
        pkill -F /tmp/pimmich_voice_control.pid 2>/dev/null || true
        rm -f /tmp/pimmich_voice_control.pid
    fi
    # Tuer le processus du diaporama s'il est en cours
    # Stop the slideshow process if it is running.
    if [ -f /tmp/pimmich_slideshow.pid ]; then
        pkill -F /tmp/pimmich_slideshow.pid 2>/dev/null || true
        rm -f /tmp/pimmich_slideshow.pid
    fi
    # Tuer toute instance précédente de l'application Flask (app.py)
    # Stop any previous Flask application process (app.py).
    # Utilisation de pkill -f pour plus de robustesse
    # Use pkill -f for more reliable process matching.
    pkill -f "python3 -u app.py" 2>/dev/null || true
    pkill -f "python3 app.py" 2>/dev/null || true
    pkill -f ffmpeg 2>/dev/null || true
    sleep 1 # Laisser le temps aux processus de se terminer
    # Give the processes time to exit.
}

while true; do
    # Nettoyer avant chaque lancement
    # Clean up before each launch.
    cleanup

		echo "📟📟$(date +'%d-%m %H:%M:%S') 📟 ================================================================" >> logs/pimmich.log
		say "📟📟$(date +'%d-%m %H:%M:%S') 📟 🚀 Lancement de l'application Pimmich... 🚀🚀🚀🚀🚀🚀🚀🚀🚀" "📟📟$(date +'%d-%m %H:%M:%S') 📟 🚀 Starting the Pimmich application... 🚀🚀🚀🚀🚀🚀🚀🚀🚀" >> logs/pimmich.log
		echo "📟📟$(date +'%d-%m %H:%M:%S') 📟 ================================================================" >> logs/pimmich.log
    
    # Vérifier et activer l'environnement virtuel
    # Check for and activate the virtual environment.
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        say "$(date +'%d-%m %H:%M:%S') ❌ Environnement virtuel 'venv' introuvable !" "$(date +'%d-%m %H:%M:%S') ❌ Virtual environment 'venv' not found!" >> logs/pimmich.log
        sleep 10
        continue
    fi

    # Lancer l'application
    # Start the application.
    python3 -u app.py >> logs/pimmich.log 2>&1

    exit_code=$?
    say "📟📟$(date +'%d-%m %H:%M:%S') 📟 🛑 Application terminée avec code $exit_code" "📟📟$(date +'%d-%m %H:%M:%S') 📟 🛑 Application exited with code $exit_code" >> logs/pimmich.log

    if [ $exit_code -eq 0 ]; then
        say "📟📟$(date +'%d-%m %H:%M:%S') 📟 ✅ Arrêt normal (code 0)" "📟📟$(date +'%d-%m %H:%M:%S') 📟 ✅ Normal shutdown (code 0)" >> logs/pimmich.log
        break
    fi

    if [ $exit_code -ne $RESTART_CODE ]; then
        say "📟📟$(date +'%d-%m %H:%M:%S') 📟 🔄 Redémarrage demandé dans 5 secondes..." "📟📟$(date +'%d-%m %H:%M:%S') 📟 🔄 Restarting in 5 seconds..." >> logs/pimmich.log
        sleep 5 # Pause de sécurité pour éviter une boucle rapide en cas de crash
        # Safety pause to avoid a rapid restart loop after a crash.
        continue
    fi

    say "[start_pimmich] Redémarrage demandé. Relance de l'application dans 2 secondes..." "[start_pimmich] Restart requested. Relaunching the application in 2 seconds..." >> logs/pimmich.log
    sleep 2
done
