#!/usr/bin/env python3
from .localization import tr
import os
import shutil
import subprocess
import time
import json
import glob
import requests
import logging
from pathlib import Path
from .config_manager import load_config

# ============================================================
# Configuration du logging avec émojis
# ============================================================
LOGSDIR = Path(__file__).resolve().parent.parent / "logs"
LOGSDIR.mkdir(exist_ok=True)

class EmojiFormatter(logging.Formatter):
    """Formatter personnalisé avec émojis selon le niveau."""
    EMOJI_MAP = {
        "DEBUG": "🔍",
        "INFO": "ℹ️",
        "WARNING": "😒",
        "ERROR": "❌",
        "CRITICAL": "🔥"
    }
    
    def format(self, record):
        emoji = self.EMOJI_MAP.get(record.levelname, "")
        record.emoji = emoji
        return super().format(record)


# Charger la configuration
config = load_config()

# Créer un logger spécifique pour ce module
logger = logging.getLogger("pimmich.display_manager")

# Récupérer le niveau de log depuis la configuration
level_name = config.get("level_log", "INFO")
level = getattr(logging, level_name.upper(), logging.INFO)
logger.setLevel(level)
logger.propagate = False

# Handler fichier avec rotation (10 Mo max, 3 backups)
from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler(
    LOGSDIR / "pimmich.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
file_handler.setLevel(level)
file_formatter = EmojiFormatter(
    '%(emoji)s🟩%(asctime)s %(message)s',
    datefmt='%d-%m %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

# Ajouter le handler (éviter doublons si module réimporté)
if not logger.handlers:
    logger.addHandler(file_handler)

# Messages de démarrage
logger.debug(tr("--------------------Lancement de Display_Manager----------------------"))
logger.info(tr('Le mode de log actif est : %(value_0)s', value_0=level_name))
logger.debug(tr("🔍=Debug"))
logger.info(tr("ℹ️=Info"))
logger.warning(tr("😒=Warning"))
logger.error(tr("❌=Error"))
logger.info(tr("🟨=App"))
logger.info(tr("🟪=Slideshow_Manager"))
logger.info(tr("🟦=Local_Slideshow"))
logger.info(tr("🟩=Display_Manager"))

# ============================================================
# Fonctions du module
# ============================================================

def get_display_output_name():
    """Trouve le nom de la sortie HDMI active (Wayfire/Sway)."""
    #logger.info("get_display_output_name() LANCÉ")
    
    try:
        # Test wlr-randr (Wayfire/Pi OS)
        logger.debug(tr("🖥 Test wlr-randr..."))
        try:
            result = subprocess.run(
                ["wlr-randr"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # wlr-randr is optional; continue to the Sway fallback if unavailable or unresponsive.
            result = None
        #logger.debug(f"🖥 wlr-randr RC={result.returncode} STDOUT={result.stdout}")
        
        if result and result.returncode == 0:
            for line in result.stdout.splitlines():
                if line and not line[0].isspace():
                    output = line.split()[0]
                    logger.info(tr('✅ Output détecté: %(value_0)s', value_0=output))
                    #print(f"SORTIE: {output}")  # Info user
                    return output
        
        # Fallback Sway
        logger.debug(tr("🖥 Fallback sway..."))
        env = os.environ.copy()
        if "SWAYSOCK" not in env:
            uid = os.getuid()
            socks = glob.glob(f"/run/user/{uid}/sway-ipc.*")
            if socks:
                env["SWAYSOCK"] = socks[0]
        
        result = subprocess.run(
            ["swaymsg", "-t", "get_outputs"],
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
            check=False
        )
        
        if result.returncode == 0:
            outputs = json.loads(result.stdout)
            logger.debug(tr('🖥 sway: %(value_0)s outputs', value_0=len(outputs)))
            
            for o in outputs:
                name = o.get("name", "?")
                active = o.get("active", False)
                logger.debug(tr('sway: %(value_0)s active=%(value_1)s', value_0=name, value_1=active))
                
                if active or o.get("current_mode"):
                    logger.info(tr('✅ SWAY HDMI: %(value_0)s', value_0=name))
                    return name
        
        logger.warning(tr("😒 0x0 - AUCUNE SORTIE"))
        return None
        
    except Exception as e:
        logger.error(tr('❌ ERREUR: %(value_0)s', value_0=e))
        return None


def send_smart_plug_command(url):
    """Envoi commande HTTP à la prise connectée."""
    if not url:
        return False, "Pas d'URL"
    
    try:
        logger.info(tr('Envoi commande prise: %(value_0)s', value_0=url))
        r = requests.post(url, timeout=5)
        logger.debug(tr('Prise réponse: %(value_0)s', value_0=r.status_code))
        
        if 200 <= r.status_code < 300:
            print(f"Commande prise envoyée: {url}")
            logger.info(tr("✅ Commande prise OK"))
            return True, "OK"
        
        logger.warning(tr('😒 Erreur HTTP: %(value_0)s', value_0=r.status_code))
        return False, f"Erreur {r.status_code}"
        
    except Exception as e:
        logger.error(tr('❌ Exception requête: %(value_0)s', value_0=e))
        return False, str(e)


def set_display_power(on=True):
    """Allume/éteint l'écran (prise ou logiciel)."""
    logger.info(tr('⏻ set_display_power(%(value_0)s)', value_0=on))
    config = load_config()
    
    if config.get("smart_plug_enabled"):
        if on:
            # Allumage prise
            on_url = config.get("smart_plug_on_url")
            success, msg = send_smart_plug_command(on_url)
            
            if not success:
                logger.error(tr('❌ Échec prise: %(value_0)s', value_0=msg))
                return False, f"Échec prise: {msg}"
            
            delay = int(config.get("smart_plug_on_delay", 5))
            logger.info(tr('⏳ Attente %(value_0)ss pour init écran...', value_0=delay))
            time.sleep(delay)
            
            # Reboot pour HDMI stable
            flag_path = LOGSDIR / "pimmich_reboot_flag.tmp"
            flag_path.parent.mkdir(exist_ok=True)
            flag_path.touch()
            logger.info(tr("✅ ⏻ Reboot pour résolution HDMI..."))
            subprocess.run(["sudo", "-n", "reboot"], check=False)
            return True, "Reboot initié"
        else:
            # Extinction DPMS puis prise
            logger.info(tr("⏻ Extinction DPMS puis prise"))
            set_software_display_power(False)
            time.sleep(1)
            
            off_url = config.get("smart_plug_off_url")
            success, msg = send_smart_plug_command(off_url)
            
            if success:
                logger.info(tr("✅ Prise éteinte OK"))
            else:
                logger.warning(tr('😒 Échec extinction prise: %(value_0)s', value_0=msg))
            
            return success, msg
    else:
        logger.info(tr("⏻ Pas de prise, DPMS uniquement."))
        return set_software_display_power(on)


def set_software_display_power(on=True):
    """Active/désactive DPMS via wlr-randr/swaymsg."""
    #logger.info(f"set_software_display_power({on})")
    output = get_display_output_name()
    
    if not output:
        logger.warning(tr("🖥😒 Pas de HDMI."))
        return False, "Pas de HDMI"
    
    state = "on" if on else "off"
    
    try:
        if shutil.which("wlr-randr"):
            cmd = ["wlr-randr", "--output", output, f"--{state}"]
            logger.info(tr('🖥️ Commande: %(value_0)s', value_0=' '.join(cmd)))
            result = subprocess.run(
                cmd,
                timeout=5,
                capture_output=True,
                text=True,
                check=False
            )
            logger.debug(tr('🖥️ wlr DPMS: RC=%(value_0)s STDOUT=%(value_1)s ERR=%(value_2)s', value_0=result.returncode, value_1=result.stdout.strip(), value_2=result.stderr.strip()))
            if result.returncode == 0:
                logger.info(tr('🖥️✅ Écran %(value_0)s -> %(value_1)s via wlr-randr.', value_0=output, value_1=state))
                return True, "OK"
        
        # Fallback swaymsg
        logger.info(tr("🖥️Fallback swaymsg DPMS..."))
        result = subprocess.run(
            ["swaymsg", "output", output, "dpms", state],
            timeout=5,
            capture_output=True,
            text=True
        )
        logger.debug(tr('🖥️sway DPMS: RC=%(value_0)s', value_0=result.returncode))
        
        if result.returncode == 0:
            logger.info(tr('🖥️✅ Écran %(value_0)s -> %(value_1)s via swaymsg.', value_0=output, value_1=state))
            return True, "OK"
        else:
            logger.warning(tr('🖥️😒 Échec swaymsg DPMS: RC=%(value_0)s', value_0=result.returncode))
            return False, "Échec DPMS"
            
    except Exception as e:
        err_msg = f"🖥️Erreur DPMS: {e}"
        logger.error(tr('❌ %(value_0)s', value_0=err_msg))
        return False, err_msg
