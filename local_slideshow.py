from utils.localization import get_global_language, tr
import os
import random
import time
os.environ["PYGAME_BLEND_ALPHA_SDL2"] = "1"
import pygame
import traceback
import requests
from PIL import Image, ImageOps, ImageFilter, ImageDraw
import signal
import re
import socket
import subprocess, sys
import glob
import collections
import math
from datetime import datetime, timedelta
import json
import qrcode
import psutil
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from utils.text_drawer import draw_text_with_outline
from utils.metadata_utils import get_photo_metadata, load_photo_metadata_cache # Import from new utility
from utils.config_manager import load_config
from utils.tide_format import format_tide_day, format_tide_type

# Helper minimal pour l'extraction des traductions (Pybabel)
# Minimal helper for extracting translations (Pybabel).
def _(text, **kwargs):
    try:
        return text % kwargs if kwargs else text
    except (KeyError, TypeError, ValueError):
        return text

# Définition des chemins
# Define file paths.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREPARED_BASE_DIR = Path(BASE_DIR) / 'static' / 'prepared'
STATUS_FILE = "/tmp/pimmich_slideshow_status.json"
SOUNDS_DIR = Path(BASE_DIR) / 'static' / 'sounds'
CUSTOM_PLAYLIST_FILE = "/tmp/pimmich_custom_playlist.json"
ICONS_DIR = Path(BASE_DIR) / 'static' / 'icons'
NEW_POSTCARD_FLAG = Path(BASE_DIR) / 'cache' / 'new_postcard.flag'
CURRENT_PHOTO_FILE = "/tmp/pimmich_current_photo.txt"
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'config.json')
FAVORITES_PATH = os.path.join(BASE_DIR, 'config', 'favorites.json')
FILTER_STATES_PATH = os.path.join(BASE_DIR, 'config', 'filter_states.json')
TIDES_CACHE_FILE = Path(BASE_DIR) / 'cache' / 'tides.json'
_icon_cache = {} # Cache pour les icônes météo chargées
_envelope_blink_end_time = None # Pour gérer le clignotement de l'icône
_postcard_count_cache = 0
_last_postcard_count_check = 0

# --- Variables globales pour le contrôle du diaporama ---
# --- Global slideshow control variables ---
paused = False
next_photo_requested = False
previous_photo_requested = False

# État interne pour le fichier de statut
# Internal state for the status file.
_current_status = {"paused": False, "is_custom": False}

_current_background_music = None # Pour rejouer après une vidéo
# Chemin et cache pour les codes pays ISO 3166 (drapeaux)
# Path and cache for ISO 3166 country codes (flags).
COUNTRY_CODES_PATH = Path(BASE_DIR) / 'static' / 'flags' / 'country_codes.json'
_country_codes_cache = None  # Cache chargé une fois

LOGS_DIR = Path(__file__).resolve().parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

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

config = load_config()

file_handler = RotatingFileHandler(
    LOGS_DIR / "pimmich.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
level_name = config.get("level_log", "INFO")
level = getattr(logging, level_name.upper(), logging.INFO)

file_handler.setLevel(level)

file_formatter = EmojiFormatter(
    '%(emoji)s🟦%(asctime)s %(message)s',
    datefmt='%d-%m %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

logging.basicConfig(
    level=level,  # niveau global
    handlers=[file_handler, logging.StreamHandler()],
    force=True
)

logger = logging.getLogger(__name__)

def button_callback(channel):
    """Callback exécuté lors de l'appui sur le bouton."""
    logger.info(tr('Bouton physique pressé (GPIO %(value_0)s). Basculement de la veille...', value_0=channel))
    try:
        # Appelle l'API de l'application web pour basculer l'état du diaporama
        # Call the web application's API to toggle the slideshow state.
        requests.post("http://127.0.0.1:5000/api/slideshow/toggle_sleep", timeout=5)
    except requests.RequestException as e:
        logger.error(tr("Impossible de contacter l'API pour la mise en veille: %(value_0)s", value_0=e))


# Messages de démarrage
# Startup messages.
logger.debug(tr("----------------Initialisation local_Slideshow  ----------------"))



def load_country_codes():
    """Charge le mapping ISO → nom pays (pour lookup inverse)"""
    global _country_codes_cache
    if _country_codes_cache is None:
        try:
            with open(COUNTRY_CODES_PATH, 'r', encoding='utf-8') as f:
                codes = json.load(f)
                # Inverse : nom_pays → iso (ex: "France" → "fr")
                # Reverse mapping: country_name → ISO code (e.g. "France" → "fr").
                _country_codes_cache = {name.lower(): iso for iso, name in codes.items()}
        except FileNotFoundError:
            logger.info(tr('⚠️  country_codes.json manquant dans config/'))
            _country_codes_cache = {}
        except Exception as e:
            logger.info(tr('❌ Erreur chargement country_codes.json: %(value_0)s', value_0=e))
            _country_codes_cache = {}
    return _country_codes_cache

def update_status_file(new_fields):
    """Met à jour le fichier de statut JSON en préservant les autres champs."""
    global _current_status
    _current_status.update(new_fields)
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(_current_status, f)
    except IOError as e:
        logger.info(tr('Erreur écriture fichier statut : %(value_0)s', value_0=e))

def signal_handler_next(signum, frame):
    global next_photo_requested
    next_photo_requested = True

def signal_handler_previous(signum, frame):
    global previous_photo_requested
    previous_photo_requested = True

def signal_handler_pause_toggle(signum, frame):
    global paused
    paused = not paused
    update_status_file({"paused": paused})

# NOUVELLE FONCTION POUR GERER LES EVENEMENTS (QUIT, TACTILE)
# NEW FUNCTION TO HANDLE EVENTS (QUIT, TOUCH).
def handle_slideshow_events(screen_width):
    """Gère les événements Pygame comme QUIT et les clics de souris pour le contrôle tactile."""
    global paused, next_photo_requested, previous_photo_requested
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        # --- NOUVEAU : Gestion des clics pour le contrôle tactile ---
        # --- NEW: Handle clicks for touchscreen control ---
        elif event.type == pygame.MOUSEBUTTONDOWN:
            # On ne gère que le clic gauche (bouton 1), qui correspond à un appui sur l'écran tactile
            # Handle only the left click (button 1), which corresponds to a touchscreen tap.
            if event.button == 1:
                pos = pygame.mouse.get_pos()
                if pos[0] < screen_width / 3:
                    logger.info(tr("📸 Zone gauche de l'écran touchée -> Photo précédente"))
                    previous_photo_requested = True
                elif pos[0] > screen_width * 2 / 3:
                    logger.info(tr("📸 Zone droite de l'écran touchée -> Photo suivante"))
                    next_photo_requested = True
                else:
                    logger.info(tr("📸 Zone centrale de l'écran touchée -> Pause/Reprise"))
                    paused = not paused
                    update_status_file({"paused": paused})

def play_background_music(filename):
    """Charge et joue une musique de fond en boucle."""
    if not filename: return
    music_path = Path(BASE_DIR) / 'static' / 'music' / filename
    if music_path.exists():
        try:
            if not pygame.mixer.get_init(): pygame.mixer.init()
            pygame.mixer.music.load(str(music_path))
            pygame.mixer.music.play(-1) # -1 pour boucler à l'infini
            logger.info(tr('🎵 Musique de fond lancée : %(value_0)s', value_0=filename))
        except Exception as e:
            logger.error(tr('❌ Erreur lors de la lecture de la musique : %(value_0)s', value_0=e))

VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv')

def reinit_pygame():
    """Quitte et réinitialise complètement Pygame et les ressources associées."""
    logger.debug(tr('📸 Réinitialisation complète de Pygame...'))
    pygame.quit()
    pygame.display.init()
    pygame.font.init()

    global _icon_cache
    _icon_cache = {}
    logger.debug(tr('📸 Cache des icônes météo vidé.'))

    info = pygame.display.Info()
    width, height = info.current_w, info.current_h
    screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    logger.debug(tr('📸 Pygame entièrement réinitialisé à %(value_0)sx%(value_1)s.', value_0=width, value_1=height))
    return screen, width, height

def load_filter_states():
    """Charge les états des filtres depuis un fichier JSON."""
    if not os.path.exists(FILTER_STATES_PATH):
        return {}
    try:
        with open(FILTER_STATES_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        logger.info(tr("Avertissement: Impossible de lire le fichier d'état des filtres '%(value_0)s'.", value_0=FILTER_STATES_PATH))
        return {}

def load_favorites():
    """Charge la liste des photos favorites et la retourne comme un ensemble (set) pour des recherches rapides."""
    if not os.path.exists(FAVORITES_PATH):
        return set()
    try:
        with open(FAVORITES_PATH, 'r') as f:
            # On s'attend à une liste de chemins dans le JSON
            # Expect a list of paths in the JSON.
            favorites_list = json.load(f)
            if isinstance(favorites_list, list):
                return set(favorites_list)
            else:
                logger.info(tr("Avertissement: Le fichier des favoris '%(value_0)s' ne contient pas une liste. Il sera ignoré.", value_0=FAVORITES_PATH))
                return set()
    except (json.JSONDecodeError, IOError):
        logger.info(tr("Avertissement: Impossible de lire le fichier des favoris '%(value_0)s'.", value_0=FAVORITES_PATH))
        return set()

def get_local_ip():
    """Tente de récupérer l'adresse IP locale de la machine de manière robuste."""
    # Méthode 1: Utiliser `hostname -I` (plus fiable sur Linux/RPi)
    # Method 1: Use `hostname -I` (more reliable on Linux/Raspberry Pi).
    try:
        result = subprocess.run(
            ['hostname', '-I'],
            capture_output=True, text=True, check=True, timeout=2
        )
        # Prend la première adresse IP de la liste
        # Take the first IP address in the list.
        ip = result.stdout.strip().split()[0]
        if ip:
            return ip
    except (FileNotFoundError, subprocess.CalledProcessError, IndexError, subprocess.TimeoutExpired):
        pass # La commande a échoué, on passe à la méthode suivante

    # Méthode 2: Méthode socket (fallback)
    # Method 2: Use a socket (fallback).
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Cette IP n'a pas besoin d'être joignable
        # This IP address does not need to be reachable.
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "xxx.xxx.xxx.xxx" # Fallback
    finally:
        s.close()
    return ip

# NOUVELLE FONCTION
# NEW FUNCTION.
def get_pi_model():
    """Détecte le modèle du Raspberry Pi pour un décodage vidéo optimal."""
    try:
        with open('/proc/device-tree/model', 'r') as f:
            model_str = f.read()
            if 'Raspberry Pi 4' in model_str:
                return 4
            if 'Raspberry Pi 5' in model_str:
                return 5
            if 'Raspberry Pi 3' in model_str:
                return 3
            if 'Raspberry Pi 2' in model_str:
                return 2
            if 'Zero' in model_str:
                return 1
            if 'Raspberry Pi' in model_str:
                return 1
    except FileNotFoundError:
        # Pas un Raspberry Pi ou un système où ce fichier n'existe pas
        # Not a Raspberry Pi, or the file does not exist on this system.
        return None
    except Exception as e:
        logger.info(tr('[Pi Detect] Erreur lors de la détection du modèle de Pi : %(value_0)s', value_0=e))
        return None
    return None # Modèle non reconnu

# Helper function to parse hex colors (including alpha)
def parse_color(hex_color):
    hex_color = str(hex_color).lstrip('#')
    if len(hex_color) == 6: # RRGGBB
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    elif len(hex_color) == 8: # RRGGBBAA
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4, 6))
    else:
        return (255, 255, 255) # Default to white if invalid

# New function to perform a transition between two images
def perform_transition(screen, old_image_surface, new_image_path, duration, screen_width, screen_height, main_font, config, transition_type):
    clock = pygame.time.Clock()
    fps_config = config.get("transition_fps", "auto")
    if fps_config == "30":
        fps = 30
    elif fps_config == "60":
        fps = 60
    else: # "auto"
        fps = 30 if get_pi_model() in [1, 2, 3] else 60
    num_frames = int(duration * fps)
    if num_frames == 0: # Avoid division by zero if duration is too small
        num_frames = 1

    # Load and prepare new image
    try:
        new_pil_image = Image.open(new_image_path)
    except (FileNotFoundError, Image.UnidentifiedImageError) as e:
        logger.info(tr("[Transition] ERREUR: Impossible de charger l'image '%(value_0)s': %(value_1)s", value_0=new_image_path, value_1=e))
        return None # Retourner None pour signaler l'échec
    if new_pil_image.mode != 'RGB': # type: ignore
        new_pil_image = new_pil_image.convert('RGB')

    # Scale new image to fit the screen (maintain aspect ratio, center)
    # This is the base image for the transition, not the pan/zoom scaled one
    new_pil_image_scaled = new_pil_image.copy()
    new_pil_image_scaled.thumbnail((screen_width, screen_height), Image.Resampling.LANCZOS)
    
    # Optimisation majeure : convert() pour aligner le format de pixels sur celui de l'écran
    # Major optimization: use convert() to match the screen's pixel format.
    new_surface_scaled = pygame.Surface((screen_width, screen_height)).convert()
    new_surface_scaled.fill((0,0,0)) # Black background for new image
    
    img_x = (screen_width - new_pil_image_scaled.width) // 2
    img_y = (screen_height - new_pil_image_scaled.height) // 2
    
    # Optimisation majeure : convert() pour aligner le format de pixels de l'image sur celui de l'écran
    # Major optimization: use convert() to match the image pixel format to the screen.
    temp_surf = pygame.image.fromstring(new_pil_image_scaled.tobytes(), new_pil_image_scaled.size, new_pil_image_scaled.mode).convert()
    new_surface_scaled.blit(temp_surf, (img_x, img_y))

    # Récupérer les métadonnées pour l'image en cours de transition
    # Get metadata for the image currently being transitioned to.
    photo_metadata = get_photo_metadata(new_image_path)

    # Pré-calculer l'overlay pour ne pas le redessiner à chaque frame (optimisation performances)
    # Pre-render the overlay so it does not need to be redrawn every frame (performance optimization).
    overlay_surface = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
    draw_overlay(overlay_surface, screen_width, screen_height, config, main_font, photo_metadata)

    # Pi 1, 2, 3 downscaling optimization for transitions
    is_low_end_pi = (get_pi_model() in [1, 2, 3])
    if is_low_end_pi:
        small_width, small_height = screen_width // 2, screen_height // 2
        old_image_small = pygame.transform.scale(old_image_surface, (small_width, small_height)).convert()
        new_surface_small = pygame.transform.scale(new_surface_scaled, (small_width, small_height)).convert()
        temp_surface_small = pygame.Surface((small_width, small_height)).convert()

    for i in range(num_frames + 1):
        progress = i / num_frames # 0.0 to 1.0

        if transition_type == "fade":
            alpha = int(255 * progress)
            if is_low_end_pi:
                new_surface_small.set_alpha(alpha)
                temp_surface_small.blit(old_image_small, (0, 0))
                temp_surface_small.blit(new_surface_small, (0, 0))
                pygame.transform.scale(temp_surface_small, (screen_width, screen_height), screen)
            else:
                # Optimisation majeure : on modifie l'alpha directement sur la surface d'origine sans faire de copie lourde
                # Major optimization: change alpha directly on the original surface instead of making an expensive copy.
                new_surface_scaled.set_alpha(alpha)
                screen.blit(old_image_surface, (0, 0))
                screen.blit(new_surface_scaled, (0, 0))
        elif transition_type.startswith("slide_"):
            # Determine slide direction
            direction = transition_type.split("_")[1]
            
            # Calculate offset for the new image
            offset_x, offset_y = 0, 0
            if direction == "left":
                offset_x = int(screen_width * (1 - progress)) # New image starts off-screen right, slides left
            elif direction == "right":
                offset_x = int(-screen_width * (1 - progress)) # New image starts off-screen left, slides right
            elif direction == "up":
                offset_y = int(screen_height * (1 - progress)) # New image starts off-screen bottom, slides up
            elif direction == "down":
                offset_y = int(-screen_height * (1 - progress)) # New image starts off-screen top, slides down
            
            screen.blit(old_image_surface, (0, 0)) # Draw old image first
            screen.blit(new_surface_scaled, (offset_x, offset_y)) # Draw new image sliding in
        else: # Fallback to fade if unknown type
            screen.blit(old_image_surface, (0, 0))
            screen.blit(new_surface_scaled, (0, 0)) # Just blit new image directly
        
        # Draw overlay during transition
        screen.blit(overlay_surface, (0, 0))

        pygame.display.flip()
        clock.tick(fps)

    # Ensure the new image is fully blitted at the end of the transition
    screen.blit(new_surface_scaled, (0, 0))
    draw_overlay(screen, screen_width, screen_height, config, main_font, photo_metadata)
    pygame.display.flip()

    return new_pil_image

# Vérifie si on est dans les heures actives
# Check whether the current time is within the active hours.
def is_within_active_hours(config):
    now = datetime.now()
    try:
        if now.weekday() >= 5:
            start = config.get("active_start_weekend", config.get("active_start", "07:00"))
            end = config.get("active_end_weekend", config.get("active_end", "22:00"))
        else:
            start = config.get("active_start_weekday", config.get("active_start", "07:00"))
            end = config.get("active_end_weekday", config.get("active_end", "22:00"))
            
        start_time = datetime.strptime(start, "%H:%M").time()
        end_time = datetime.strptime(end, "%H:%M").time()
        now_time = now.time()
    except Exception as e:
        logger.info(tr('Erreur format horaire : %(value_0)s', value_0=e))
        return True

    if start_time <= end_time:
        return start_time <= now_time <= end_time
    else:
        return now_time >= start_time or now_time <= end_time

# --- Gestion de la météo ---
# --- Weather handling ---
_weather_and_forecast_data = None
_last_weather_and_forecast_fetch = None
_weather_warning_printed = False

OPENWEATHER_LANGUAGES = {
    "sq", "af", "ar", "az", "eu", "be", "bg", "ca", "zh_cn", "zh_tw",
    "hr", "cz", "da", "nl", "en", "fi", "fr", "gl", "de", "el", "he",
    "hi", "hu", "is", "id", "it", "ja", "kr", "ku", "la", "lt", "mk",
    "no", "fa", "pl", "pt", "pt_br", "ro", "ru", "sr", "sk", "sl", "es",
    "sv", "th", "tr", "uk", "vi", "zu",
}

def get_weather_and_forecast(config):
    """Récupère la météo actuelle et les prévisions sur 3 jours."""
    global _weather_and_forecast_data, _last_weather_and_forecast_fetch, _weather_warning_printed
    
    api_key = config.get("weather_api_key")
    city = config.get("weather_city")
    units = config.get("weather_units", "metric")
    language = config.get("weather_language", "fr")
    if not isinstance(language, str) or language not in OPENWEATHER_LANGUAGES:
        language = "fr"
    try:
        interval_minutes = int(config.get("weather_update_interval_minutes", 30))
    except (ValueError, TypeError):
        interval_minutes = 30

    if not api_key or not city:
        if not _weather_warning_printed:
            logger.info(tr('[Weather] Clé API ou ville manquante. La météo est désactivée.'))
            _weather_warning_printed = True
        return None

    now = datetime.now()
    if _last_weather_and_forecast_fetch and (now - _last_weather_and_forecast_fetch).total_seconds() < interval_minutes * 60:
        return _weather_and_forecast_data

    logger.info(tr('[Weather] Récupération des prévisions météo...'))
    _last_weather_and_forecast_fetch = now # Mettre à jour pour éviter les appels répétés en cas d'échec

    try:
        # Utilise l'API de prévision 5 jours / 3 heures (disponible en offre gratuite)
        # Use the 5-day / 3-hour forecast API (available on the free plan).
        url = "https://api.openweathermap.org/data/2.5/forecast"
        response = requests.get(
            url,
            params={"q": city, "appid": api_key, "units": units, "lang": language},
            timeout=10,
        )
        response.raise_for_status()
        api_data = response.json()

        # --- Traitement des données pour obtenir une prévision par jour ---
        # --- Process the data to produce a daily forecast ---
        current_weather = api_data['list'][0]
        
        daily_forecasts = collections.defaultdict(lambda: {'temps': [], 'icons': []})
        
        # Grouper les données par jour
        # Group the data by day.
        for forecast in api_data['list']:
            day = datetime.fromtimestamp(forecast['dt']).strftime('%Y-%m-%d')
            daily_forecasts[day]['temps'].append(forecast['main']['temp'])
            daily_forecasts[day]['icons'].append((forecast['weather'][0]['icon'], forecast['dt_txt'], forecast['weather'][0]['description']))

        processed_forecast = []
        # Trier les jours et prendre les 3 prochains jours (en excluant aujourd'hui)
        # Sort the days and select the next 3 days (excluding today).
        today_str = datetime.now().strftime('%Y-%m-%d')
        sorted_days = sorted([day for day in daily_forecasts.keys() if day > today_str])[:3]

        for i, day_str in enumerate(sorted_days):
            day_data = daily_forecasts[day_str]
            # Numeric dates avoid language-specific weekday labels in the forecast.
            day_label = datetime.strptime(day_str, '%Y-%m-%d').strftime('%d/%m')

            min_temp = round(min(day_data['temps']))
            max_temp = round(max(day_data['temps']))
            
            # Choisir une icône représentative (celle la plus proche de 13h)
            # Choose a representative icon (the one closest to 1 p.m.).
            midday_icon = day_data['icons'][0][0] # icon
            midday_desc = day_data['icons'][0][2] # description
            min_hour_diff = 24
            for icon, dt_txt, desc in day_data['icons']:
                hour = int(dt_txt.split(' ')[1].split(':')[0])
                if abs(hour - 13) < min_hour_diff:
                    min_hour_diff = abs(hour - 13)
                    midday_icon = icon
                    midday_desc = desc

            processed_forecast.append({
                'day': day_label,
                'min_temp': min_temp,
                'max_temp': max_temp,
                'icon': midday_icon,
                'description': midday_desc.capitalize()
            })
        
        _weather_and_forecast_data = {'current': current_weather, 'forecast': processed_forecast}
        logger.info(tr('[Weather] Météo et prévisions mises à jour pour %(value_0)s.', value_0=city))
        return _weather_and_forecast_data

    except requests.exceptions.RequestException as e:
        logger.info(tr('[Weather] Erreur réseau lors de la récupération des prévisions : %(value_0)s', value_0=e))
        return None
    except Exception as e:
        logger.info(tr('[Weather] Erreur générale lors de la récupération des prévisions : %(value_0)s', value_0=e))
        traceback.print_exc()
        return None

# --- Gestion des marées ---
# --- Tide handling ---
_tides_data = None
_last_tides_fetch = None
_tides_warning_printed = False

def get_tides(config):
    """Récupère les prochaines marées haute et basse, avec un cache en mémoire et un cache fichier persistant."""
    global _tides_data, _last_tides_fetch, _tides_warning_printed
    api_key = config.get("stormglass_api_key")
    lat = config.get("tide_latitude")
    lon = config.get("tide_longitude")
    # Intervalle de cache de 12 heures pour limiter les appels API à 2 par jour max.
    # Cache for 12 hours to limit API calls to at most 2 per day.
    cache_duration_seconds = 12 * 3600

    if not all([api_key, lat, lon]):
        if not _tides_warning_printed:
            logger.info(tr('[Tides] Clé API StormGlass, latitude ou longitude manquante. Les marées sont désactivées.'))
            _tides_warning_printed = True
        return None

    # 1. Vérifier le cache en mémoire d'abord
    # 1. Check the in-memory cache first.
    now = datetime.now()
    if _last_tides_fetch and (now - _last_tides_fetch).total_seconds() < cache_duration_seconds:
        return _tides_data

    # 2. Le cache mémoire est expiré, on vérifie le cache fichier
    # 2. The in-memory cache has expired, so check the file cache.
    TIDES_CACHE_FILE.parent.mkdir(exist_ok=True)
    if TIDES_CACHE_FILE.exists():
        try:
            with open(TIDES_CACHE_FILE, 'r') as f:
                cache_content = json.load(f)
            
            last_file_fetch_dt = datetime.fromisoformat(cache_content['timestamp'])
            
            if (now - last_file_fetch_dt).total_seconds() < cache_duration_seconds:
                # Si c'est une entrée de cooldown, on ne fait rien et on attend.
                # If this is a cooldown entry, do nothing and wait.
                if cache_content.get('cooldown'):
                    logger.info(tr('[Tides] Cooldown API actif depuis le cache fichier.'))
                    _last_tides_fetch = now # Mettre à jour le timer en mémoire pour respecter le cooldown
                    _tides_data = None
                    return None

                tide_data_from_cache = cache_content.get('data')

                # --- NOUVEAU: Vérification du format du cache pour la compatibilité ascendante ---
                # --- NEW: Check the cache format for backward compatibility ---
                if isinstance(tide_data_from_cache, list):
                    logger.info(tr('[Tides] Données de marée valides (format liste) trouvées dans le cache fichier.'))
                    _tides_data = tide_data_from_cache
                    _last_tides_fetch = now
                    return tide_data_from_cache
                else:
                    logger.info(tr('[Tides] Ancien format de cache détecté (dictionnaire). Le cache sera invalidé et recréé.'))
                    # On laisse l'exécution continuer pour appeler l'API
                    # Continue execution so the API can be called.
        except Exception as e:
            logger.info(tr("[Tides] Erreur lecture du cache fichier, récupération depuis l'API. Erreur: %(value_0)s", value_0=e))

    # 3. Les deux caches sont invalides, appeler l'API
    # 3. Both caches are invalid; call the API.
    logger.info(tr("[Tides] Récupération des données de marée depuis l'API StormGlass..."))
    _last_tides_fetch = now # Mettre à jour pour éviter les appels répétés en cas d'échec

    try:
        start_time_utc = datetime.utcnow()
        end_time_utc = start_time_utc + timedelta(days=7) # --- MODIFICATION: Récupérer 7 jours de données ---

        headers = {'Authorization': api_key}
        params = {'lat': lat, 'lng': lon, 'start': start_time_utc.isoformat(), 'end': end_time_utc.isoformat()}
        
        response = requests.get('https://api.stormglass.io/v2/tide/extremes/point', params=params, headers=headers, timeout=15)
        response.raise_for_status()
        extremes_data = response.json().get('data', [])

        # Filtrer pour ne garder que les marées futures
        # Keep only future tides.
        now_utc = datetime.utcnow().replace(tzinfo=None)
        future_extremes = [e for e in extremes_data if datetime.fromisoformat(e['time'].replace('Z', '+00:00')).replace(tzinfo=None) > now_utc]

        if not future_extremes:
            logger.info(tr("[Tides] Aucune marée future trouvée dans les données de l'API pour les prochaines 24h."))
            return None

        # Sauvegarder la liste complète des marées futures dans le cache
        # Save the full list of future tides in the cache.
        data_to_cache = {'data': future_extremes, 'timestamp': datetime.now().isoformat()}
        
        with open(TIDES_CACHE_FILE, 'w') as f:
            json.dump(data_to_cache, f, indent=2)
        
        logger.info(tr('[Tides] Données de marée mises à jour et cache sauvegardé.'))
        # --- CORRECTION: Mettre à jour le cache en mémoire avant de retourner ---
        # --- FIX: Update the in-memory cache before returning ---
        _tides_data = future_extremes
        return _tides_data
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 402:
            logger.info(tr('[Tides] ERREUR: Quota API StormGlass dépassé. Prochaine tentative dans 12h.'))
            # Écrire un timestamp de cooldown dans le cache pour éviter les re-tentatives si le script redémarre
            # Write a cooldown timestamp to the cache to prevent retries if the script restarts.
            cooldown_data = {'data': {}, 'timestamp': datetime.now().isoformat(), 'cooldown': True}
            try:
                with open(TIDES_CACHE_FILE, 'w') as f:
                    json.dump(cooldown_data, f, indent=2)
                logger.info(tr('[Tides] Timestamp de cooldown écrit dans le cache fichier.'))
            except Exception as write_e:
                logger.info(tr("[Tides] Impossible d'écrire le cooldown dans le cache fichier: %(value_0)s", value_0=write_e))
        else:
            logger.info(tr('[Tides] Erreur HTTP lors de la récupération des marées : %(value_0)s', value_0=e))
        _tides_data = None
        return None
    except Exception as e:
        logger.info(tr('[Tides] Erreur générale lors de la récupération des marées : %(value_0)s', value_0=e))
        traceback.print_exc()
        _tides_data = None # Mettre le cache en mémoire à None pour forcer une nouvelle tentative
        return None

def load_icon(icon_name, size, is_weather_icon=True):
    """
    Charge une icône, la met en cache et la retourne comme une surface Pygame.
    Retourne un carré rouge en cas d'échec pour un débogage visuel.
    """
    if size <= 0:
        logger.info(tr("[Display] AVERTISSEMENT: Taille d'icône invalide (%(value_0)spx) pour '%(value_1)s'.", value_0=size, value_1=icon_name))
        return None

    icon_key = f"{icon_name}_{size}"
    if icon_key in _icon_cache:
        return _icon_cache[icon_key]

    if is_weather_icon:
        icon_dir = PREPARED_BASE_DIR.parent / 'weather_icons'
    else:
        icon_dir = ICONS_DIR
    
    icon_path = icon_dir / f"{icon_name}.png"

    if icon_path.exists():
        try:
            loaded_surface = pygame.image.load(str(icon_path)).convert_alpha()
            icon_surface = pygame.transform.scale(loaded_surface, (size, size))
            _icon_cache[icon_key] = icon_surface
            return icon_surface
        except Exception as e:
            logger.info(tr("[Display] Erreur chargement icône '%(value_0)s': %(value_1)s", value_0=icon_path, value_1=e))
            # Fall through to return placeholder
    else:
        warning_key = f"warn_{icon_name}"
        if warning_key not in _icon_cache:
            logger.info(tr('[Display] AVERTISSEMENT: Fichier icône non trouvé : %(value_0)s', value_0=icon_path))
            _icon_cache[warning_key] = True
    
    # --- Retourner None en cas d'échec ---
    # --- Return None on failure ---
    # Cela permet à la logique d'affichage de simplement ignorer l'icône.
    # This lets the display logic simply skip the icon.
    return None

def draw_pause_icon(screen, screen_width, screen_height):
    """Affiche une icône de pause en bas au centre de l'écran."""
    icon_size = 50 # Taille de l'icône de pause réduite
    # On utilise load_icon qui gère le cache et le chemin static/icons
    # Use load_icon, which handles the cache and the static/icons path.
    pause_icon = load_icon("pause", icon_size, is_weather_icon=False)
    if pause_icon:
        # Positionnée en bas au centre avec une marge de 40 pixels (10 + 30) du bord
        # Positioned at the bottom center, 40 pixels (10 + 30) from the edge.
        rect = pause_icon.get_rect(centerx=screen_width // 2, bottom=screen_height - 40)
        screen.blit(pause_icon, rect)

def draw_postcard_notification_icon(screen, screen_width, screen_height, count, font):
    """Affiche une icône de notification de carte postale avec un compteur en bas au centre."""
    icon_size = 50 
    # Charge postale.png dans static/icons
    # Load postale.png from static/icons.
    postale_icon = load_icon("postale", icon_size, is_weather_icon=False)
    if postale_icon and font:
        text_str = str(count)
        text_color = (255, 255, 255)
        outline_color = (0, 0, 0)
        
        # Calcul de la largeur totale pour centrer le bloc [Icône + Nombre]
        # Calculate the total width to center the [icon + count] group.
        text_surf = font.render(text_str, True, text_color)
        spacing = 10
        total_width = icon_size + spacing + text_surf.get_width()
        
        start_x = (screen_width - total_width) // 2
        icon_rect = postale_icon.get_rect(left=start_x, bottom=screen_height - 40)
        screen.blit(postale_icon, icon_rect)
        
        # Dessin du texte à côté de l'icône (centré verticalement sur l'icône)
        # Draw the text beside the icon, vertically centered against it.
        text_y = icon_rect.top + (icon_size - text_surf.get_height()) // 2
        draw_text_with_outline(screen, text_str, font, text_color, outline_color, (icon_rect.right + spacing, text_y), anchor="topleft")

def get_today_postcard_count():
    """Compte le nombre de cartes postales reçues aujourd'hui."""
    global _postcard_count_cache, _last_postcard_count_check
    if time.time() - _last_postcard_count_check < 60:
        return _postcard_count_cache

    count = 0
    today_date = datetime.now().date()
    telegram_dir = PREPARED_BASE_DIR / 'telegram'

    if not telegram_dir.is_dir():
        return 0

    # On ne compte que les fichiers de cartes postales pour éviter les doublons
    # Count only postcard files to avoid duplicates.
    for f in telegram_dir.glob('*_postcard.jpg'):
        # Utilise une regex pour extraire le timestamp du nom de fichier
        # Use a regular expression to extract the timestamp from the filename.
        match = re.search(r'telegram_(\d+)_', f.name)
        if match:
            try:
                timestamp = int(match.group(1))
                photo_date = datetime.fromtimestamp(timestamp).date()
                if photo_date == today_date:
                    count += 1
            except (ValueError, OSError):
                continue # Ignorer les fichiers avec un timestamp invalide
    
    _postcard_count_cache = count
    _last_postcard_count_check = time.time()
    
    return count

def get_path_to_display(photo_path_obj, source, filter_states):
    """
    Détermine le chemin de fichier correct à afficher en fonction de la source et des filtres.
    """
    relative_path_str = f"{source}/{photo_path_obj.name}"
    active_filter = filter_states.get(relative_path_str, 'none')
    
    # Par défaut, on affiche l'image de base
    # Display the base image by default.
    path_to_display = str(photo_path_obj)

    # Priorité 1: Filtre explicite de l'utilisateur
    # Priority 1: An explicit user filter.
    if active_filter == 'polaroid':
        polaroid_path = photo_path_obj.with_name(f"{photo_path_obj.stem}_polaroid.jpg")
        if polaroid_path.exists():
            path_to_display = str(polaroid_path)
    elif active_filter == 'postcard':
        postcard_path = photo_path_obj.with_name(f"{photo_path_obj.stem}_postcard.jpg")
        if postcard_path.exists():
            path_to_display = str(postcard_path)
    # Priorité 2: Comportement par défaut pour la source Telegram (si aucun filtre n'est actif)
    # Priority 2: Default behavior for the Telegram source (when no filter is active).
    elif source == 'telegram' and active_filter in ['none', 'original']:
        postcard_path = photo_path_obj.with_name(f"{photo_path_obj.stem}_postcard.jpg")
        if postcard_path.exists():
            path_to_display = str(postcard_path)
            
    return path_to_display

def build_playlist(media_list, config, favorites):
    """
    Construit la playlist finale en appliquant les boosts pour les favoris et les photos récentes.
    """
    favorite_boost = int(config.get("favorite_boost_factor", 2))
    telegram_boost_enabled = config.get("telegram_boost_enabled", True)
    telegram_boost_factor = int(config.get("telegram_boost_factor", 4))
    telegram_boost_duration_days = int(config.get("telegram_boost_duration_days", 7))
    anniversary_boost_enabled = config.get("anniversary_boost_enabled", False)
    anniversary_boost_factor = int(config.get("anniversary_boost_factor", 2))

    playlist = []
    for media_path in media_list:
        playlist.append(media_path)
        relative_path = str(Path(media_path).relative_to(PREPARED_BASE_DIR))
        normalized_relative_path = re.sub(r'(_polaroid|_postcard)\.jpg$', '.jpg', relative_path)

        if telegram_boost_enabled and 'telegram' in media_path:
            match = re.search(r'telegram_(\d+)_', Path(media_path).name)
            if match and (datetime.now() - datetime.fromtimestamp(int(match.group(1)))).days < telegram_boost_duration_days:
                for _ in range(telegram_boost_factor): playlist.append(media_path)
        if normalized_relative_path in favorites:
            for _ in range(favorite_boost): playlist.append(media_path)

        # --- Boost d'anniversaire ---
        # --- Birthday boost ---
        if anniversary_boost_enabled:
            photo_metadata = get_photo_metadata(media_path)
            if photo_metadata:
                date_priority = [
                    "subSecDateTimeOriginal", "dateTimeOriginal", "SubSecDateTimeOriginal", "DateTimeOriginal",
                    "subSecCreateDate", "createDate", "SubSecCreateDate", "CreateDate",
                    "subSecModifyDate", "modifyDate", "SubSecModifyDate",
                    "mediaCreateDate", "dateTimeCreated", "MediaCreateDate", "DateTimeCreated",
                    "fileModifiedAt", "fileCreatedAt"
                ]
                date_taken_str = next((photo_metadata.get(field) for field in date_priority if photo_metadata.get(field)), None)
                
                if date_taken_str:
                    try:
                        photo_date = datetime.fromisoformat(date_taken_str.replace('Z', '+00:00'))
                        if photo_date.month == datetime.now().month and photo_date.day == datetime.now().day:
                            logger.debug(tr('📸 Boost anniversaire pour %(value_0)s (prise le %(value_1)s)', value_0=Path(media_path).name, value_1=photo_date.strftime('%d/%m')))
                            for _ in range(anniversary_boost_factor): playlist.append(media_path)
                    except Exception as e:
                        logger.debug(tr('Erreur lors de la lecture de la date pour le boost anniversaire: %(value_0)s', value_0=e))
    return playlist

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM) # Utiliser la numérotation BCM des pins
    GPIO_AVAILABLE = True
except ImportError:
    logger.debug(tr('RPi.GPIO non disponible. Le contrôle du ventilateur est désactivé.'))
    GPIO_AVAILABLE = False

def set_gpio_output(pin, state):
    """
    Définit l'état (HIGH/True ou LOW/False) d'un pin GPIO en sortie.

    Args:
        pin (int): Le numéro du pin GPIO (en numérotation BCM).
        state (bool): True pour HIGH (3.3V), False pour LOW (0V).

    Returns:
        None
    """
    if GPIO_AVAILABLE:
        try:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
        except Exception as e:
            logger.info(tr('Erreur lors de la manipulation du GPIO %(value_0)s: %(value_1)s', value_0=pin, value_1=e))

def control_fan(temperature, threshold=55, pin=14):
    if temperature >= threshold:
        set_gpio_output(pin, True)
        # logger.info(f"Ventilateur activé (température : {temperature}°C, seuil : {threshold}°C)") # Commenté pour réduire le bruit dans les logs
        # logger.info(f"Fan enabled (temperature: {temperature}°C, threshold: {threshold}°C)") # Commented out to reduce log noise.
    else:
        set_gpio_output(pin, False)

# New function to draw the overlay elements (clock, date, weather)
def draw_overlay(screen, screen_width, screen_height, config, main_font, photo_metadata=None):
    now = datetime.now()
    text_color = parse_color(config.get("clock_color", "#FFFFFF"))
    outline_color = parse_color(config.get("clock_outline_color", "#000000"))
    display_telegram_notification_overlay = config.get("display_telegram_notification_overlay", True)
    country_codes = load_country_codes()


    # --- Météo et Prévisions ---
    # --- Weather and forecasts ---
    weather_and_forecast = None
    if config.get("show_weather", False):
        weather_and_forecast = get_weather_and_forecast(config)

    if config.get("show_clock", False):
        separator = "  |  "
        icon_padding = 10

        # --- Préparation des éléments à afficher ---
        # --- Prepare the elements to display ---
        elements = []

        # Heure
        # Time.
        time_str = now.strftime(config.get("clock_format", "%H:%M"))
        elements.append({'type': 'text', 'text': time_str})

        # Date
        # Date.
        if config.get("show_date", False):
            date_str = now.strftime(config.get("date_format", "%A %d %B %Y"))
            elements.append({'type': 'text', 'text': separator + date_str})

        # Météo Actuelle (utilisant les données déjà récupérées)
        # Current weather (using data already retrieved).
        if weather_and_forecast and weather_and_forecast.get('current'):
            try:
                current_weather = weather_and_forecast['current']
                icon_code = current_weather['weather'][0]['icon']
                icon_surface = load_icon(icon_code, main_font.get_height(), is_weather_icon=True)
                if icon_surface:
                    elements.append({'type': 'icon', 'surface': icon_surface, 'padding': icon_padding})

                temp = round(current_weather['main']['temp'])
                description = current_weather['weather'][0]['description'].capitalize()
                weather_str = f"{temp}°C, {description}"
                elements.append({'type': 'text', 'text': " " + weather_str})
            except Exception as e:
                logger.info(tr('[Display] Erreur préparation météo actuelle: %(value_0)s', value_0=e))

        # --- Prévisions sur 3 jours ---
        # --- 3-day forecast ---
        if weather_and_forecast and weather_and_forecast.get('forecast'):
            for forecast_day in weather_and_forecast.get('forecast', []):
                try:
                    elements.append({'type': 'text', 'text': separator})

                    # Icône pour le jour de prévision
                    # Icon for the forecast day.
                    icon_code = forecast_day.get('icon')
                    if icon_code:
                        icon_surface = load_icon(icon_code, main_font.get_height(), is_weather_icon=True)
                        if icon_surface:
                            elements.append({'type': 'icon', 'surface': icon_surface, 'padding': icon_padding})

                    # Texte de la prévision
                    # Forecast text.
                    day_name = forecast_day.get('day', '')
                    temp_str = f"{forecast_day['max_temp']}°/{forecast_day['min_temp']}°"
                    weather_str = f"{day_name}: {temp_str}"
                    elements.append({'type': 'text', 'text': " " + weather_str})
                except (IndexError, KeyError) as e:
                    logger.info(tr('[Display] Erreur préparation météo pour un jour: %(value_0)s', value_0=e))

        if display_telegram_notification_overlay:
            # --- Compteur de cartes postales du jour ---
            # --- Today's postcard count ---
            today_postcard_count = get_today_postcard_count()
            if today_postcard_count > 0:
                elements.append({'type': 'text', 'text': separator})

                # --- Logique de clignotement ---
                # --- Blinking logic ---
                global _envelope_blink_end_time
                is_blinking = _envelope_blink_end_time and datetime.now() < _envelope_blink_end_time
                
                icon_surface = load_icon("postale", main_font.get_height(), is_weather_icon=False)
                if icon_surface:
                    # On ajoute toujours l'icône à la liste pour la largeur, mais on contrôle sa visibilité
                    # Always include the icon when calculating width, but control whether it is visible.
                    should_draw_icon = not is_blinking or (is_blinking and datetime.now().second % 2 == 0)
                    elements.append({'type': 'icon', 'surface': icon_surface, 'padding': icon_padding, 'visible': should_draw_icon})
                
                # Texte du compteur
                # Counter text.
                elements.append({'type': 'text', 'text': f" {today_postcard_count}"})


        # --- Calcul de la taille totale et positionnement du bloc ---
        # --- Calculate the total size and position of the group ---
        total_width = 0
        max_height = 0
        for el in elements:
            if el['type'] == 'text':
                el['surface'] = main_font.render(el['text'], True, text_color)
            total_width += el['surface'].get_width()
            if el.get('padding'):
                total_width += el['padding']
            if el['surface'].get_height() > max_height:
                max_height = el['surface'].get_height()

        offset_x = int(config.get("clock_offset_x", 0))
        offset_y = int(config.get("clock_offset_y", 0))
        position = config.get("clock_position", "center")

        if position == "left":
            block_x = offset_x
        elif position == "right":
            block_x = screen_width - total_width + offset_x
        else: # center
            block_x = (screen_width - total_width) // 2 + offset_x
        
        # Positionner le bloc en haut de l'écran avec un padding de 15px
        # Position the group at the top of the screen with 15 px of padding.
        block_y = 15 + offset_y

        # --- Dessin du fond semi-transparent ---
        # --- Draw the semi-transparent background ---
        if config.get("clock_background_enabled", False):
            bg_color_hex = config.get("clock_background_color", "#00000080")
            bg_color_rgba = parse_color(bg_color_hex)
            
            if len(bg_color_rgba) == 3:
                bg_color_rgba = bg_color_rgba + (128,) # Ajouter une semi-transparence par défaut
            
            bg_surface = pygame.Surface((screen_width, max_height + 20), pygame.SRCALPHA)
            bg_surface.fill(bg_color_rgba)
            screen.blit(bg_surface, (0, block_y - 10))

        # --- Dessin des éléments séquentiellement ---
        # --- Draw the elements in sequence ---
        current_x = block_x
        for el in elements:
            el_y = block_y + (max_height - el['surface'].get_height()) // 2
            
            if el.get('padding'):
                current_x += el['padding']

            # On ne dessine l'élément que s'il est visible (par défaut True)
            # Draw the element only if it is visible (True by default).
            if el.get('visible', True):
                if el['type'] == 'text':
                    draw_text_with_outline(screen, el['text'], main_font, text_color, outline_color, (current_x, el_y), anchor="topleft")
                elif el['type'] == 'icon':
                    screen.blit(el['surface'], (current_x, el_y))
            
            current_x += el['surface'].get_width()

        # --- Bloc du bas pour les marées ---
        # --- Bottom block for tides ---
        if config.get("show_tides", False):
            tides_data = get_tides(config)
            tide_text = None
            font_to_use = main_font

            if tides_data:
                tide_parts = []
                tide_language = config.get("tide_language", "fr")

                # Afficher les 4 prochaines marées pour avoir une bonne visibilité sur les jours à venir
                # Show the next 4 tides to provide a clear view of the coming days.
                for tide in tides_data[:4]:
                    tide_dt = datetime.fromisoformat(tide['time']).astimezone()
                    day_str = format_tide_day(tide_dt, tide_language, compact=True)
                    type_str = format_tide_type(tide['type'], tide_language, compact=True)
                    time_str = tide_dt.strftime('%H:%M')
                    
                    tide_parts.append(f"{day_str} {type_str}: {time_str}")
                
                if tide_parts:
                    tide_text = " | ".join(tide_parts)
            else:
                # Afficher un message si les données ne sont pas disponibles mais que la fonction est activée
                # Show a message if the feature is enabled but data is unavailable.
                tide_text = _("Données de marée non disponibles")
                try:
                    # Utiliser une police légèrement plus petite pour le message d'erreur
                    # Use a slightly smaller font for the error message.
                    font_path = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
                    font_size = int(main_font.get_height() * 0.8) # 80% de la taille de la police principale
                    font_to_use = pygame.font.Font(font_path, font_size)
                except Exception as e:
                    logger.info(tr('[Display] Erreur chargement police pour message marée: %(value_0)s', value_0=e))
                    font_to_use = main_font # Fallback

            if tide_text:
                tide_offset_x = int(config.get("tide_offset_x", 0))
                tide_offset_y = int(config.get("tide_offset_y", 0))

                tide_surface = font_to_use.render(tide_text, True, text_color)
                tide_rect = tide_surface.get_rect(centerx=(screen_width // 2) + tide_offset_x, bottom=(screen_height - 15) + tide_offset_y)

                # --- Ajout du fond pour les marées ---
                # --- Add the background for the tides ---
                if config.get("clock_background_enabled", False):
                    bg_color_hex = config.get("clock_background_color", "#00000080")
                    bg_color_rgba = parse_color(bg_color_hex)

                    if len(bg_color_rgba) == 3:
                        bg_color_rgba = bg_color_rgba + (128,)

                    # Créer une surface de fond sur toute la largeur de l'écran
                    # Create a background surface spanning the full screen width.
                    bg_height = tide_rect.height + 10  # Ajouter 5px de padding en haut et en bas
                    bg_surface = pygame.Surface((screen_width, bg_height), pygame.SRCALPHA)
                    bg_surface.fill(bg_color_rgba)
                    # Positionner le fond verticalement pour qu'il encadre le texte
                    # Position the background vertically so it frames the text.
                    screen.blit(bg_surface, (0, tide_rect.top - 5))

                draw_text_with_outline(screen, tide_text, font_to_use, text_color, outline_color, tide_rect.topleft, anchor="topleft")


    # --- Modification Sigalou 25/01/2026 - Affichage des métadonnées photo en bas de l'écran ---
    # --- Sigalou change 25/01/2026 - Show photo metadata at the bottom of the screen ---
    # Ce bloc affiche la date de prise de vue et/ou la localisation de la photo
    # This block displays the photo's capture date and/or location
    # si ces informations sont disponibles dans les métadonnées Immich
    # when this information is available in the Immich metadata.
    has_any_date = False
    if photo_metadata is not None:
        has_any_date = any(photo_metadata.get(field) for field in [
            "SubSecDateTimeOriginal", "DateTimeOriginal", "SubSecCreateDate", 
            "CreateDate", "SubSecModifyDate", "MediaCreateDate", "DateTimeCreated", 
            "subSecDateTimeOriginal", "dateTimeOriginal", "subSecCreateDate", "createDate",
            "subSecModifyDate", "modifyDate", "mediaCreateDate", "dateTimeCreated",
            "fileModifiedAt", "fileCreatedAt"
        ])

    if photo_metadata and (has_any_date or config.get("show_photo_location", False)):
    
    
    
        metadata_elements = []
        metadata_separator = "  •  "

        # Récupérer la police personnalisée pour les métadonnées
        # Get the custom font for the metadata.
        metadata_font_path = config.get("photo_metadata_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        metadata_font_size = int(config.get("photo_metadata_font_size", 23))

        try:
            metadata_font = pygame.font.Font(metadata_font_path, metadata_font_size)
        except Exception as e:
            logger.info(tr('[Display] Erreur chargement police métadonnées : %(value_0)s.', value_0=e))
            metadata_font = main_font

        # Couleurs personnalisées pour les métadonnées
        # Custom colors for the metadata.
        metadata_text_color = parse_color(config.get("photo_metadata_color", "#ffffff"))
        metadata_outline_color = parse_color(config.get("photo_metadata_outline_color", "#000000"))
        
        # Extraction de la date de prise de vue (priorité 16 champs)
        # Extract the capture date (check 16 fields in priority order).
        date_priority = [
            "subSecDateTimeOriginal", "dateTimeOriginal", "SubSecDateTimeOriginal", "DateTimeOriginal",
            "subSecCreateDate", "createDate", "SubSecCreateDate", "CreateDate",
            "subSecModifyDate", "modifyDate", "SubSecModifyDate",
            "mediaCreateDate", "dateTimeCreated", "MediaCreateDate", "DateTimeCreated",
            "fileModifiedAt", "fileCreatedAt"
        ]
        date_candidates = [photo_metadata.get(field) for field in date_priority]
        date_taken_str = next((d for d in date_candidates if d), None)

        # Affichage de la date de prise de vue
        # Display the capture date.
        if config.get("show_photo_date", False) and date_taken_str:
            try:
                photo_date = datetime.fromisoformat(date_taken_str.replace('Z', '+00:00'))
                photo_date_format = config.get("photo_date_format", "%d %B %Y")
                metadata_elements.append(photo_date.strftime(photo_date_format))
            except Exception as e:
                logger.info(tr('[Display] Erreur formatage date : %(value_0)s', value_0=e))

        # Mention "Anniversaire" (Il y a X ans)
        # Add an "On this day" note (X years ago).
        if config.get("anniversary_boost_enabled", True) and date_taken_str:
            try:
                p_date = datetime.fromisoformat(date_taken_str.replace('Z', '+00:00'))
                now = datetime.now()
                if p_date.month == now.month and p_date.day == now.day:
                    years_ago = now.year - p_date.year
                    if years_ago > 0:
                        msg = _("(Anniversaire) Il y a %(num)d an") if years_ago == 1 else _("(Anniversaire) Il y a %(num)d ans")
                        metadata_elements.append(msg % {"num": years_ago})
            except:
                pass

        # Localisation
        # Location.
        if config.get("show_photo_location", False):
            location_format = config.get("photo_location_format", "city_country")

            if location_format == "city":
                location_str = photo_metadata.get("city", "")
            elif location_format == "country":
                location_str = photo_metadata.get("country", "")
            else:  # city_country (par défaut)
                city = photo_metadata.get("city", "")
                country = photo_metadata.get("country", "")
                if city and country:
                    location_str = f"{city}, {country}"
                else:
                    location_str = city or country

            if location_str:
                metadata_elements.append(location_str)

        # Assembler et afficher les métadonnées
        # Assemble and display the metadata.
        if metadata_elements:
            metadata_text = metadata_separator.join(metadata_elements)
            metadata_surface = metadata_font.render(metadata_text, True, metadata_text_color)

            # Offsets optionnels
            # Optional offsets.
            metadata_offset_x = int(config.get("photo_metadata_offset_x", 0))
            metadata_offset_y = int(config.get("photo_metadata_offset_y", 0))

            # Position selon la configuration
            # Position according to the configuration.
            position = config.get("photo_metadata_position", "bottom_left")

            if position == "bottom_left":
                metadata_rect = metadata_surface.get_rect(
                    left=15 + metadata_offset_x,
                    bottom=(screen_height - 15) + metadata_offset_y
                )
            elif position == "bottom_right":
                metadata_rect = metadata_surface.get_rect(
                    right=(screen_width - 15) + metadata_offset_x,
                    bottom=(screen_height - 15) + metadata_offset_y
                )
            elif position == "bottom_center":
                metadata_rect = metadata_surface.get_rect(
                    centerx=(screen_width // 2) + metadata_offset_x,
                    bottom=(screen_height - 15) + metadata_offset_y
                )
            elif position == "top_left":
                metadata_rect = metadata_surface.get_rect(
                    left=15 + metadata_offset_x,
                    top=15 + metadata_offset_y
                )
            elif position == "top_right":
                metadata_rect = metadata_surface.get_rect(
                    right=(screen_width - 15) + metadata_offset_x,
                    top=15 + metadata_offset_y
                )
            else:  # Fallback
                metadata_rect = metadata_surface.get_rect(
                    left=15 + metadata_offset_x,
                    bottom=(screen_height - 15) + metadata_offset_y
                )

            # Dessiner le fond si activé
            # Draw the background if enabled.
            if config.get("photo_metadata_background_enabled", True):
                bg_color_hex = config.get("photo_metadata_background_color", "#00000080")
                bg_color_rgba = parse_color(bg_color_hex)

                if len(bg_color_rgba) == 3:
                    bg_color_rgba = bg_color_rgba + (128,)

                bg_width = metadata_rect.width + 20
                bg_height = metadata_rect.height + 10
                bg_surface = pygame.Surface((bg_width, bg_height), pygame.SRCALPHA)
                bg_surface.fill(bg_color_rgba)
                screen.blit(bg_surface, (metadata_rect.left - 10, metadata_rect.top - 5))

            # Dessiner le texte avec contour
            # Draw the text with an outline.
            draw_text_with_outline(
                screen, 
                metadata_text, 
                metadata_font, 
                metadata_text_color, 
                metadata_outline_color, 
                metadata_rect.topleft, 
                anchor="topleft"
            )
    # --- Fin Modification Sigalou 25/01/2026 ---
    # --- End of Sigalou change 25/01/2026 ---

        # --- DRAPEAU PAYS en haut à droite (ajout Sigalou 29/01/2026) ---
        # --- COUNTRY FLAG at the top right (added by Sigalou 29/01/2026) ---
        if photo_metadata and config.get("show_country_flag", True):
            
            if country:
                iso_code = country_codes.get(country.lower())
                iso_code_country_flag_url = None   

                if iso_code:
                    iso_code_country_flag_url = f"{iso_code}.png"
                #else:
                    #flag_url = None A VOIR SI ON AJOUTE UN DRAPEAU QUI DIT QUE C EST INCONNU
                    #flag_url = None TO REVIEW IF WE ADD A FLAG INDICATING AN UNKNOWN COUNTRY.
                    try:
                        import requests
                        from PIL import Image
                        from io import BytesIO
                        
                        flag_size = config.get("country_flag_size", "128x96")
                        flag_url = f"https://flagcdn.com/{flag_size}/{iso_code_country_flag_url}"
                            
                        response = requests.get(flag_url, timeout=1.5)
                        if response.status_code == 200:
                            flag_pil = Image.open(BytesIO(response.content)).convert('RGBA')
                            
                            
                            # --- AJOUT : Appliquer une opacité au drapeau ---
                            # --- ADD: Apply opacity to the flag ---
                            opacity = config.get("country_flag_opacity", 0.7)
                            # Séparer les canaux RGBA
                            # Separate the RGBA channels.
                            r, g, b, a = flag_pil.split()
                            # Réduire l'opacité du canal alpha
                            # Reduce the opacity of the alpha channel.
                            a = a.point(lambda p: int(p * opacity))
                            # Recombiner les canaux
                            # Combine the channels again.
                            flag_pil = Image.merge('RGBA', (r, g, b, a))
                            # --- FIN AJOUT ---
                            # --- END ADDITION ---
                            
                            flag_surf = pygame.image.fromstring(
                                flag_pil.tobytes(), flag_pil.size, flag_pil.mode
                            )
                            
                            # Positionnement du drapeau
                            # Position the flag.
                            flag_position = config.get("country_flag_position", "top_right")
                            flag_offset_x = int(config.get("country_flag_offset_x", 15))
                            flag_offset_y = int(config.get("country_flag_offset_y", 15))

                            if flag_position == "top_left":
                                flag_rect = flag_surf.get_rect(topleft=(flag_offset_x, flag_offset_y))
                            elif flag_position == "bottom_left":
                                flag_rect = flag_surf.get_rect(bottomleft=(flag_offset_x, screen_height - flag_offset_y))
                            elif flag_position == "bottom_right":
                                flag_rect = flag_surf.get_rect(bottomright=(screen_width - flag_offset_x, screen_height - flag_offset_y))
                            else: # top_right (default)
                                flag_rect = flag_surf.get_rect(topright=(screen_width - flag_offset_x, flag_offset_y))
                            
                            screen.blit(flag_surf, flag_rect)
                            
                    except ImportError:
                        logger.info(tr('[Display] pip install requests pillow'))
                    except Exception as e:
                        pass  # Silencieux
        # --- Fin DRAPEAU ---
        # --- End of flag section ---

def display_title_slide(screen, screen_width, screen_height, title, duration, config, photos_for_slide=None):
    """Affiche un écran titre avec le nom de la playlist et un pêle-mêle de photos."""
    logger.info(tr("📸 Affichage de l'écran titre : '%(value_0)s'", value_0=title))
 
    # --- NOUVEAU: Charger les images des punaises en tant qu'images PIL ---
    # --- NEW: Load the pushpin images as PIL images ---
    thumbtack_pil_images = []
    try:
        icons_dir = Path(BASE_DIR) / 'static' / 'icons'
        # On cherche des punaises de différentes couleurs
        # Look for pushpins in different colors.
        thumbtack_paths = list(icons_dir.glob('thumbtack_*.png'))
        if thumbtack_paths:
            for tack_path in thumbtack_paths:
                tack_img = Image.open(str(tack_path)).convert("RGBA")
                # Redimensionner à une taille raisonnable (ex: 40x40 pixels)
                # Resize to a reasonable size (e.g. 40 x 40 pixels).
                tack_img.thumbnail((40, 40), Image.Resampling.LANCZOS)
                thumbtack_pil_images.append(tack_img)
        else:
            logger.info(tr('[Title Slide] Avertissement: Aucune image de punaise (thumbtack_*.png) trouvée dans static/icons/.'))
    except Exception as e:
        logger.info(tr('[Title Slide] Avertissement: Impossible de charger les punaises: %(value_0)s', value_0=e))

    # Créer une surface temporaire pour dessiner tous les éléments avant de les afficher
    # Create a temporary surface to draw all elements before displaying them.
    # Cela évite les problèmes de rafraîchissement et garantit que tout est dessiné dans le bon ordre.
    # This prevents refresh issues and ensures everything is drawn in the correct order.
    temp_surface = pygame.Surface((screen_width, screen_height))

    try:
        cork_bg_path = Path(BASE_DIR) / 'static' / 'backgrounds' / 'cork_background.jpg'
        if cork_bg_path.exists():
            cork_bg_img = pygame.image.load(str(cork_bg_path)).convert()
            # --- NOUVEAU: Logique de redimensionnement et de centrage du fond ---
            # --- NEW: Background scaling and centering logic ---
            screen_height_percent = int(config.get("screen_height_percent", "100"))
            
            # Calculer la hauteur utile pour le fond
            # Calculate the usable height for the background.
            new_bg_height = int(screen_height * (screen_height_percent / 100.0))

            # Redimensionner l'image de fond pour qu'elle remplisse la zone utile sans être déformée.
            # Resize the background image to fill the usable area without distortion.
            original_bg_width, original_bg_height = cork_bg_img.get_size()
            bg_aspect_ratio = original_bg_width / original_bg_height
            
            # On scale pour que la largeur corresponde à la largeur de l'écran
            # Scale the image so its width matches the screen width.
            scaled_w = screen_width
            scaled_h = int(scaled_w / bg_aspect_ratio)
            
            # Si l'image est devenue moins haute que la zone utile, on la scale par la hauteur
            # If the image is shorter than the usable area, scale it to match the height.
            if scaled_h < new_bg_height:
                scaled_h = new_bg_height
                scaled_w = int(scaled_h * bg_aspect_ratio)

            scaled_cork_bg = pygame.transform.smoothscale(cork_bg_img, (scaled_w, scaled_h))

            # On va rogner l'image de fond si elle est plus grande que la zone utile
            # Crop the background image if it is larger than the usable area.
            crop_area = pygame.Rect(
                (scaled_w - screen_width) // 2,
                (scaled_h - new_bg_height) // 2,
                screen_width,
                new_bg_height
            )

            # Position de la zone utile sur l'écran final
            # Position the usable area on the final screen.
            bg_y = (screen_height - new_bg_height) // 2
            
            temp_surface.fill((0, 0, 0)) # Remplir le fond de l'écran en noir (pour les bords)
            temp_surface.blit(scaled_cork_bg, (0, bg_y), crop_area) # Dessiner la partie rognée et centrée
        else:
            # Fallback sur une couleur unie si l'image n'est pas trouvée
            # Fall back to a solid color if the image is not found.
            logger.info(tr("[Title Slide] Avertissement: Image de fond non trouvée à %(value_0)s. Utilisation d'une couleur unie.", value_0=cork_bg_path))
            temp_surface.fill((181, 136, 99)) # Une couleur proche du liège
    except Exception as e:
        logger.info(tr("[Title Slide] Erreur lors du chargement du fond : %(value_0)s. Utilisation d'une couleur unie.", value_0=e))
        temp_surface.fill((181, 136, 99))

    # --- Pêle-mêle de photos ---
    # --- Photo collage ---
    if photos_for_slide:
        num_photos = min(len(photos_for_slide), 4)
        if num_photos > 0:
            selected_paths = random.sample(photos_for_slide, num_photos)

            photo_surfaces = []
            for path in selected_paths:
                try:
                    # Charger l'image avec PIL
                    # Load the image with PIL.
                    img = Image.open(path)
                    # Créer une miniature
                    # Create a thumbnail.
                    img.thumbnail((400, 400), Image.Resampling.LANCZOS)
                    # Ajouter une bordure blanche pour l'effet polaroid
                    # Add a white border for the Polaroid effect.
                    img_with_border = ImageOps.expand(img, border=20, fill='white')
                    
                    image_to_rotate = img_with_border.convert("RGBA")

                    # --- NOUVEAU: Ajouter la punaise sur une toile plus grande AVANT la rotation ---
                    # --- NEW: Add the pushpin to a larger canvas BEFORE rotating ---
                    if thumbtack_pil_images:
                        tack_img = random.choice(thumbtack_pil_images)
                        
                        # Créer une nouvelle toile plus grande pour inclure la punaise qui dépasse
                        # Create a larger canvas to include the protruding pushpin.
                        new_height = image_to_rotate.height + tack_img.height // 2
                        composite_canvas = Image.new('RGBA', (image_to_rotate.width, new_height), (0, 0, 0, 0))
                        
                        # Coller la photo sur la toile, en laissant de l'espace en haut
                        # Paste the photo onto the canvas, leaving space at the top.
                        composite_canvas.paste(image_to_rotate, (0, tack_img.height // 2))
                        
                        # Coller la punaise en haut au centre
                        # Paste the pushpin at the top center.
                        tack_x = (composite_canvas.width - tack_img.width) // 2
                        composite_canvas.paste(tack_img, (tack_x, 0), tack_img)
                        
                        image_to_rotate = composite_canvas
                        
                    # Inclinaison aléatoire
                    # Random rotation.
                    angle = random.uniform(-15, 15)
                    rotated_img = image_to_rotate.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
                    
                    py_surface = pygame.image.fromstring(rotated_img.tobytes(), rotated_img.size, rotated_img.mode).convert_alpha()
                    photo_surfaces.append(py_surface)
                except Exception as e:
                    logger.info(tr("[Title Slide] Erreur lors de la préparation de l'image %(value_0)s: %(value_1)s", value_0=path, value_1=e))

            # Ligne de débogage pour vérifier si des photos ont été traitées
            # Debug line to check how many photos were processed.
            logger.info(tr('[Title Slide] DEBUG: Nombre de surfaces photos préparées : %(value_0)s', value_0=len(photo_surfaces)))

            # Positionner les photos de manière aléatoire mais répartie
            # Position the photos randomly but spread them out.
            base_positions = [
                (screen_width * 0.25, screen_height * 0.25),
                (screen_width * 0.75, screen_height * 0.35),
                (screen_width * 0.30, screen_height * 0.75),
                (screen_width * 0.70, screen_height * 0.80)
            ]
            random.shuffle(base_positions)

            for i, surface in enumerate(photo_surfaces):
                pos_x = base_positions[i][0] + random.randint(-50, 50)
                pos_y = base_positions[i][1] + random.randint(-50, 50)
                rect = surface.get_rect(center=(pos_x, pos_y))
                temp_surface.blit(surface, rect)

    # --- Titre de la playlist ---
    # --- Playlist title ---
    text_color = parse_color(config.get("clock_color", "#FFFFFF"))
    outline_color = parse_color(config.get("clock_outline_color", "#000000"))

    try:
        # Utiliser une police cursive et plus grande pour le titre
        # Use a larger cursive font for the title.
        font_path = str(Path(BASE_DIR) / "static" / "fonts" / "Caveat-Regular.ttf")
        # Augmenter la taille de la police pour un meilleur impact visuel
        # Increase the font size for greater visual impact.
        title_font_size = int(config.get("clock_font_size", 72) * 2.5)
        title_font = pygame.font.Font(font_path, title_font_size)
    except Exception as e:
        logger.info(tr("Erreur chargement police pour l'écran titre: %(value_0)s", value_0=e))
        title_font = pygame.font.SysFont("Arial", 150, bold=True)

    # Dessiner le titre au centre, par-dessus les photos
    # Draw the title centered over the photos.
    draw_text_with_outline(temp_surface, title, title_font, text_color, outline_color, (screen_width // 2, screen_height // 2), anchor="center")

    # Afficher la surface finale sur l'écran principal
    # Display the final surface on the main screen.
    screen.blit(temp_surface, (0, 0))
    pygame.display.flip()

    # Boucle d'attente pour rester réactif aux signaux (ex: QUIT)
    # Wait in a loop so the program remains responsive to signals (e.g. QUIT).
    start_sleep = time.time()
    while time.time() - start_sleep < duration:
        handle_slideshow_events(screen_width)
        time.sleep(0.1)

# Fonction pour afficher une image et l'heure
# Function to display an image and the time.

def display_photo_with_pan_zoom(screen, pil_image, screen_width, screen_height, config, main_font, photo_path=None, ignore_postcard_flag=False):
    """
    Affiche une image préparée avec un effet de pan/zoom et gère les contrôles (pause, suivant, précédent).
    """
    global paused, next_photo_requested, previous_photo_requested
    # Modification Sigalou 25/01/2026 - Récupération des métadonnées de la photo
    # Sigalou change 25/01/2026 - Retrieve the photo metadata.
    photo_metadata = get_photo_metadata(photo_path) if photo_path else None
    # Fin Modification Sigalou 25/01/2026
    # End of Sigalou change 25/01/2026.

    # Préparer l'image et les métadonnées dès le début pour éviter les erreurs de définition (NameError)
    # Prepare the image and metadata up front to avoid undefined-name errors (NameError).
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    pygame_image_base = pygame.image.fromstring(pil_image.tobytes(), pil_image.size, pil_image.mode)


    # Boucle de pause : si le diaporama est en pause, on attend ici.
    # Pause loop: wait here while the slideshow is paused.
    while paused:
        config = load_config() # Recharger pour réagir au changement de notification immédiat
        handle_slideshow_events(screen_width)
        if next_photo_requested or previous_photo_requested: return
        
        ticks = pygame.time.get_ticks()
        p_count = get_today_postcard_count() if config.get("display_telegram_notification_overlay", True) else 0
        if (ticks // 500) % 2 == 0:
            draw_pause_icon(screen, screen_width, screen_height)
        elif p_count > 0:
            draw_postcard_notification_icon(screen, screen_width, screen_height, p_count, main_font)
            
        pygame.display.flip()
        time.sleep(0.1) # Évite de surcharger le CPU pendant la pause

    """Affiche une image préparée et l'heure sur l'écran."""
    try:
        # Ensure it's in a compatible mode for Pygame (RGB is generally safe)
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')

        pan_zoom_enabled = config.get("pan_zoom_enabled", False)
        display_duration = config.get("display_duration", 10)
        logger.info(tr('⏳ Pause de %(value_0)s secondes.', value_0=display_duration)) # Debug print
        
        # Always blit the base image first (this will be overwritten by animation if enabled)
        pygame_image_base = pygame.image.fromstring(pil_image.tobytes(), pil_image.size, pil_image.mode)
        screen.blit(pygame_image_base, (0, 0))
        
        if not pan_zoom_enabled: # If pan/zoom is disabled, just show static image
            # Affichage statique : blit une fois et attendre la durée
            # Static display: blit once, then wait for the duration.
            draw_overlay(screen, screen_width, screen_height, config, main_font, photo_metadata)
            pygame.display.flip()
            # Boucle d'attente pour rester réactif aux signaux
            # Wait in a loop to remain responsive to signals.
            start_sleep = time.time()
            while time.time() - start_sleep < display_duration:
                handle_slideshow_events(screen_width)
                # Vérification en temps réel de l'arrivée d'une nouvelle carte postale
                # Check in real time for an incoming postcard.
                if not ignore_postcard_flag and NEW_POSTCARD_FLAG.exists(): return

                if next_photo_requested or previous_photo_requested: return
                was_paused = False
                while paused:
                    config = load_config() # Recharger pour réaction immédiate au bouton
                    was_paused = True
                    handle_slideshow_events(screen_width)
                    if next_photo_requested or previous_photo_requested: return

                    # Redessiner le fond pour effacer l'icône de la phase précédente
                    # Redraw the background to clear the icon from the previous phase.
                    screen.blit(pygame_image_base, (0, 0))
                    draw_overlay(screen, screen_width, screen_height, config, main_font, photo_metadata)

                    # Logique de clignotement/alternance (Pause / Nouvelle Postale)
                    # Blinking and alternation logic (paused / new postcard).
                    ticks = pygame.time.get_ticks()
                    # Vérifier l'option de notification même en pause
                    # Check the notification setting even while paused.
                    p_count = get_today_postcard_count() if config.get("display_telegram_notification_overlay", True) else 0
                    if (ticks // 500) % 2 == 0: draw_pause_icon(screen, screen_width, screen_height)
                    elif p_count > 0: draw_postcard_notification_icon(screen, screen_width, screen_height, p_count, main_font)
                    
                    pygame.display.flip()
                    time.sleep(0.1)
                    start_sleep += 0.1

                # Gestion du clignotement de l'icône postale pendant la lecture statique
                # Handle postcard icon blinking during static display.
                config = load_config() # Rafraîchir la config ici aussi
                ticks = pygame.time.get_ticks()
                p_count = get_today_postcard_count() if config.get("display_telegram_notification_overlay", True) else 0
                if was_paused or p_count > 0:
                    screen.blit(pygame_image_base, (0, 0))
                    draw_overlay(screen, screen_width, screen_height, config, main_font, photo_metadata)
                    if p_count > 0 and (ticks // 500) % 2 != 0:
                        draw_postcard_notification_icon(screen, screen_width, screen_height, p_count, main_font)
                    pygame.display.flip()

                time.sleep(0.1)
        else:
            # Logique de l'effet Pan/Zoom
            # Pan/Zoom effect logic.
            zoom_factor = float(config.get("pan_zoom_factor", 1.15)) # Récupérer le facteur de zoom de la config
            
            # Calculate scaled image dimensions
            scaled_width = int(screen_width * zoom_factor)
            scaled_height = int(screen_height * zoom_factor)

            # Scale the image once using PIL for quality, then convert to Pygame surface
            scaled_pil_image = pil_image.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
            scaled_pygame_image = pygame.image.fromstring(scaled_pil_image.tobytes(), scaled_pil_image.size, scaled_pil_image.mode)

            # --- NOUVELLE LOGIQUE DE PANNING AMÉLIORÉE ---
            # --- NEW IMPROVED PANNING LOGIC ---
            max_x_offset = scaled_width - screen_width
            max_y_offset = scaled_height - screen_height

            # S'assurer que les offsets ne sont pas négatifs (si l'image est plus petite que l'écran)
            # Ensure the offsets are not negative (when the image is smaller than the screen).
            max_x_offset = max(0, max_x_offset)
            max_y_offset = max(0, max_y_offset)

            def get_random_edge_point(max_x, max_y):
                """Génère un point aléatoire sur l'un des quatre bords du rectangle de rognage."""
                edge = random.choice(['top', 'bottom', 'left', 'right'])
                if edge == 'top':
                    return (random.randint(0, max_x), 0)
                elif edge == 'bottom':
                    return (random.randint(0, max_x), max_y)
                elif edge == 'left':
                    return (0, random.randint(0, max_y))
                else: # right
                    return (max_x, random.randint(0, max_y))

            # Générer un point de départ et un point d'arrivée qui ne sont pas identiques
            # Generate distinct start and end points.
            start_offset = get_random_edge_point(max_x_offset, max_y_offset)
            end_offset = get_random_edge_point(max_x_offset, max_y_offset)
            while end_offset == start_offset:
                end_offset = get_random_edge_point(max_x_offset, max_y_offset)

            start_x, start_y = start_offset
            end_x, end_y = end_offset

            clock = pygame.time.Clock()
            start_animation_time = time.time()

            while time.time() - start_animation_time < display_duration:
                elapsed_animation_time = time.time() - start_animation_time

                handle_slideshow_events(screen_width)
                # Vérification en temps réel de l'arrivée d'une nouvelle carte postale
                # Check in real time for an incoming postcard.
                if not ignore_postcard_flag and NEW_POSTCARD_FLAG.exists(): return

                # Vérifier les signaux à chaque image de l'animation
                # Check for signals on every animation frame.
                if next_photo_requested or previous_photo_requested: return
                
                # Appliquer une fonction d'accélération/décélération (ease-in-out) pour un mouvement plus doux
                # Apply an ease-in-out function for smoother motion.
                raw_progress = min(1.0, elapsed_animation_time / display_duration)
                eased_progress = 0.5 * (1 - math.cos(raw_progress * math.pi))

                # Calculate current pan position
                current_x = int(start_x + (end_x - start_x) * eased_progress)
                current_y = int(start_y + (end_y - start_y) * eased_progress)

                # Blit the portion of the scaled image onto the screen
                screen.blit(scaled_pygame_image, (0, 0), (current_x, current_y, screen_width, screen_height))

                # Draw overlay (clock/date/weather)
                draw_overlay(screen, screen_width, screen_height, config, main_font, photo_metadata)

                # Gestion de la pause et des notifications (Enveloppe / Pause)
                # Handle pause and notifications (envelope / pause).
                ticks = pygame.time.get_ticks()
                p_count = get_today_postcard_count() if config.get("display_telegram_notification_overlay", True) else 0
                
                if paused:
                    # En pause : Alternance entre l'icône de pause et l'enveloppe
                    # Paused: alternate between the pause icon and the envelope.
                    config = load_config() # Recharger pendant la pause de l'animation
                    p_count = get_today_postcard_count() if config.get("display_telegram_notification_overlay", True) else 0
                    if (ticks // 500) % 2 == 0:
                        draw_pause_icon(screen, screen_width, screen_height)
                    elif p_count > 0:
                        draw_postcard_notification_icon(screen, screen_width, screen_height, p_count, main_font)
                    
                    pygame.display.flip()
                    time.sleep(0.1)
                    start_animation_time += 0.1 # On décale le temps pour ne pas "sauter" l'animation
                    continue # On recommence la boucle sans avancer l'image

                # En lecture : Clignotement de l'enveloppe seule si p_count > 0
                # Playing: blink only the envelope when p_count > 0.
                if p_count > 0 and (ticks // 500) % 2 != 0:
                    draw_postcard_notification_icon(screen, screen_width, screen_height, p_count, main_font)

                pygame.display.flip()
                clock.tick(60) # Limit frame rate to 60 FPS for smoother animation
                
    except Exception as e:
        logger.info(tr('Erreur affichage photo avec pan/zoom : %(value_0)s', value_0=e))
        traceback.print_exc()

def fade_to_black(screen, previous_surface, duration, clock):
    """Effectue un fondu au noir sur la surface donnée."""
    num_frames = int(duration * 60)
    if num_frames == 0: num_frames = 1
    
    black_surface = pygame.Surface(screen.get_size()).convert()
    black_surface.fill((0, 0, 0))

    for i in range(num_frames + 1):
        progress = i / num_frames
        alpha = int(255 * progress)
        black_surface.set_alpha(alpha)
        
        screen.blit(previous_surface, (0, 0))
        screen.blit(black_surface, (0, 0))
        pygame.display.flip()
        clock.tick(60)

def draw_loading_banner(screen, text, width, height, font):
    """Affiche un écran noir avec un message au centre pour informer l'utilisateur."""
    try:
        screen.fill((0, 0, 0))
        text_surface = font.render(text, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=(width // 2, height // 2))
        screen.blit(text_surface, text_rect)
        pygame.display.flip()
    except Exception as e:
        logger.warning(tr('Erreur lors du dessin du bandeau : %(value_0)s', value_0=e))

def display_video(screen, video_path, screen_width, screen_height, config, main_font, previous_surface, clock):
    """Affiche une vidéo en plein écran en utilisant le lecteur externe mpv."""
    global _current_background_music
    audio_enabled = config.get("video_audio_enabled", False)
    audio_output = config.get("video_audio_output", "auto")
    audio_volume = int(config.get("video_audio_volume", 100))
    transition_duration = float(config.get("transition_duration", 1.0))
    hwdec_enabled = config.get("video_hwdec_enabled", True)
    pi_model = get_pi_model()

    # 1. Afficher un bandeau de chargement avant le lancement (avec symbole sablier unicode supporté par la police)
    # 1. Show a loading banner before launch (using an hourglass symbol supported by the font).
    if main_font:
        draw_loading_banner(screen, tr("⌛ Chargement de la vidéo..."), screen_width, screen_height, main_font)
        time.sleep(0.5)

    # Pour éviter les conflits de surface graphique (CMA et Wayland scanout) entre Pygame et mpv,
    # To avoid graphics surface conflicts (CMA and Wayland scanout) between Pygame and mpv,
    # on ferme proprement Pygame avant le lancement de mpv sur TOUS les modèles de Raspberry Pi (1/2/3/4/5).
    # cleanly close Pygame before launching mpv on ALL Raspberry Pi models (1/2/3/4/5).
    # Sur ces cartes, laisser Pygame ouvert crée un conflit de ressources EGL sur le GPU, bloquant mpv indéfiniment.
    # On these boards, leaving Pygame open causes an EGL resource conflict on the GPU and can block mpv indefinitely.
    # On ajoute une pause de 0.8 seconde après la fermeture pour laisser le temps au compositeur Wayland
    # Wait 0.8 seconds after closing it to give the Wayland compositor time
    # de libérer la surface d'affichage.
    # to release the display surface.
    if pi_model in [1, 2, 3, 4, 5]:
        logger.info(tr('📸 [Pi %(value_0)s] Closing Pygame to release graphics overlay context for mpv.', value_0=pi_model))
        pygame.quit()
        time.sleep(0.8)
    elif audio_enabled:
        if pygame.mixer.get_init(): pygame.mixer.quit()

    try:
        # 1. Fondu au noir avant de lancer la vidéo (Uniquement si Pygame n'est pas déjà fermé)
        # 1. Fade to black before starting the video (only if Pygame is not already closed).
        if previous_surface and pi_model not in [1, 2, 3, 4, 5]:
            fade_to_black(screen, previous_surface, transition_duration / 2, clock)
        
        logger.info(tr('📸 Lancement de la vidéo avec mpv : %(value_0)s', value_0=video_path))
        # On réaffiche la souris au cas où l'utilisateur voudrait interagir avec mpv (barre de progression, etc.)
        # Show the mouse again in case the user wants to interact with mpv (seek bar, etc.).
        if pi_model not in [1, 2, 3, 4, 5]:
            pygame.mouse.set_visible(True)
        
        # --- NOUVELLE APPROCHE : Retour à MPV avec une configuration robuste ---
        # --- NEW APPROACH: Return to MPV with a robust configuration ---
        command = [
            'mpv',
            '--no-config',
            '--no-terminal',
            '--fs', '--no-osc', '--no-osd-bar', '--loop=no'
        ]
        
        # Si on est sur Pi 3, on ne met pas --ontop (bug Wayland).
        # Do not set --ontop on a Pi 3 (Wayland bug).
        # Pour tous les autres modèles (Pi 1/2 où Pygame tourne en dessous, ou Pi 4/5), on force --ontop au premier plan.
        # On all other models (Pi 1/2 with Pygame underneath, or Pi 4/5), force --ontop to keep mpv in front.
        if pi_model != 3:
            command.append('--ontop')

        if hwdec_enabled:
            # Pour tous les modèles de Raspberry Pi (1/2/3/4/5), on essaie en premier le mode DMABUF Haute Performance.
            # On all Raspberry Pi models (1/2/3/4/5), try High-Performance DMABUF mode first.
            # C'est le seul mode matériel direct (zéro-copie) qui évite les saccades de bande passante et l'écran noir de 15s.
            # It is the only direct hardware (zero-copy) mode that avoids bandwidth stutter and a 15-second black screen.
            if pi_model in [1, 2, 3, 4, 5]:
                logger.info(tr('[Video Playback] Raspberry Pi %(value_0)s détecté. Mode DMABUF Haute Performance.', value_0=pi_model))
                command.extend(['-v', '--hwdec=v4l2m2m', '--vo=dmabuf-wayland', '--wayland-app-id=mpv', '--log-file=/tmp/mpv_pimmich.log'])
            else:
                # Fallback pour les autres systèmes ou si la détection échoue
                # Fall back on other systems or if detection fails.
                logger.info(tr("[Video Playback] Modèle de Pi non spécifique détecté. Utilisation de '--hwdec=auto'."))
                command.extend(['--hwdec=auto', '--vo=gpu'])
            # --- FIN MODIFICATION ---
            # --- END OF CHANGE ---
        else:
            # Mode logiciel par défaut (plus stable sur certains systèmes mais plus lent)
            # Default software mode (more stable on some systems, but slower).
            logger.info(tr('[Video Playback] Décodage matériel désactivé. Utilisation du mode logiciel.'))
            # MODIFICATION: Sur Pi 4/5, x11 est trop lent. On utilise gpu même en mode logiciel.
            # CHANGE: X11 is too slow on Pi 4/5, so use GPU output even in software mode.
            if pi_model in [4, 5]:
                command.extend(['--hwdec=no', '--vo=gpu'])
            else:
                command.extend(['--hwdec=no', '--vo=x11'])

        command.append(video_path)

        if audio_enabled:
            # Régler le volume système avec amixer pour une meilleure compatibilité
            # Set the system volume with amixer for better compatibility.
            try:
                subprocess.run(['amixer', 'sset', 'Master', f'{audio_volume}%', 'unmute'], check=False, capture_output=True, text=True)
                logger.info(tr('[Audio] Volume système réglé à %(value_0)s%% via amixer.', value_0=audio_volume))
            except FileNotFoundError:
                logger.info(tr("[Audio] AVERTISSEMENT: 'amixer' non trouvé. Le volume ne peut pas être réglé."))
                   # Passer le volume à mpv également
                   # Set the volume in mpv as well.
            command.extend([f'--volume={audio_volume}', '--no-mute'])
        else:
             command.append('--no-audio')

        
        # Si on est sur un Raspberry Pi (1/2/3/4/5), on essaie d'abord le mode DMABUF Haute Performance.
        # On a Raspberry Pi (1/2/3/4/5), try High-Performance DMABUF mode first.
        # Si cela échoue, on se rabat sur le mode de compatibilité GPU (avec cache de shaders).
        # If that fails, fall back to GPU compatibility mode (with a shader cache).
        commands_to_try = [command]
        if hwdec_enabled and pi_model in [1, 2, 3, 4, 5]:
            shader_cache_dir = os.path.join(BASE_DIR, "cache", "mpv_shaders")
            os.makedirs(shader_cache_dir, exist_ok=True)
            cmd_fallback = [
                'mpv',
                '--no-config',
                '--no-terminal',
                '--fs', '--no-osc', '--no-osd-bar', '--loop=no',
                '-v',
                '--profile=fast',
                '--hwdec=v4l2m2m-copy',
                '--vo=gpu',
                '--gpu-context=wayland',
                '--gpu-shader-cache=yes',
                f'--gpu-shader-cache-dir={shader_cache_dir}',
                '--scale=bilinear',
                '--cscale=bilinear',
                '--dscale=bilinear',
                '--vd-lavc-dr=yes',
                '--wayland-app-id=mpv',
                '--log-file=/tmp/mpv_pimmich.log',
                video_path
            ]
            if pi_model != 3:
                cmd_fallback.append('--ontop')
            if audio_enabled:
                cmd_fallback.extend([f'--volume={audio_volume}', '--no-mute'])
            else:
                cmd_fallback.append('--no-audio')
            
            commands_to_try = [command, cmd_fallback]
        
        success = False
        last_error = None
        
        # Watchdog (timeout de sécurité) fixe de 90 secondes pour éviter de bloquer le diaporama si mpv freeze.
        # Pas d'appel ffprobe dynamique pour optimiser la réactivité au démarrage.
        # Do not call ffprobe dynamically; this keeps startup responsive.
        timeout_limit = 90.0

        for idx, cmd_to_run in enumerate(commands_to_try):
            logger.info(tr('📸 Executing mpv command (try %(value_0)s/%(value_1)s): %(value_2)s', value_0=idx+1, value_1=len(commands_to_try), value_2=' '.join(cmd_to_run)))
        # Très courte pause pour laisser le système se caler
        # Pause briefly to let the system settle.
            time.sleep(0.1)
            
            try:
                result = subprocess.run(
                    cmd_to_run, 
                    check=True, 
                    env=os.environ.copy(), 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT, 
                    text=True,
                    timeout=timeout_limit
                )
                success = True
                break
            except subprocess.TimeoutExpired:
                logger.warning(tr('⏱️ Le lecteur vidéo mpv a dépassé la limite de temps de sécurité (%(value_0)ss). Processus tué.', value_0=timeout_limit))
                break
            except subprocess.CalledProcessError as e:
                last_error = e
                logger.info(tr("⚠️ Échec du mode d'affichage de l'essai %(value_0)s. Tentative suivante...", value_0=idx+1))
                
        if not success:
            logger.info(tr("Erreur lors de l'exécution de mpv pour la vidéo %(value_0)s. mpv a retourné un code d'erreur.", value_0=video_path))
            
            # Extraction du log de diagnostic réel
            # Extract the actual diagnostic log.
            log_content = ""
            if os.path.exists("/tmp/mpv_pimmich.log"):
                try:
                    with open("/tmp/mpv_pimmich.log", "r") as f:
                        # On ne prend que les 50 dernières lignes pour ne pas saturer le log Pimmich
                        # Keep only the last 50 lines to avoid overwhelming the Pimmich log.
                        log_content = "".join(f.readlines()[-50:])
                except Exception: 
                    pass
            
            combined_output = last_error.stdout if (last_error and last_error.stdout and last_error.stdout.strip()) else (log_content if log_content.strip() else "Aucun message d'erreur capturé.")
            logger.info(tr("Détails de l'erreur mpv :\n%(value_0)s", value_0=combined_output))
    except Exception as e:
        logger.info(tr('Erreur inattendue lors de la lecture de la vidéo %(value_0)s: %(value_1)s', value_0=video_path, value_1=e))
    finally:
        # --- Ré-initialiser le mixer de Pygame après la lecture vidéo ---
        # --- Reinitialize the Pygame mixer after video playback ---
        # C'est crucial pour que Pygame puisse potentiellement jouer des sons plus tard,
        # This is essential so Pygame can play sounds later,
        # et pour maintenir un état cohérent.
        # and to keep its state consistent.
        if audio_enabled and pi_model not in [1, 2, 3, 4, 5]:
            logger.info(tr('📸 Re-initializing pygame.mixer.'))
            try:
                pygame.mixer.init()
            except pygame.error as e:
                logger.info(tr('AVERTISSEMENT: Impossible de réinitialiser pygame.mixer: %(value_0)s', value_0=e))
        
        # Relancer la musique de fond de la playlist si nécessaire
        # Restart the playlist background music if needed.
        if _current_background_music and pi_model not in [1, 2, 3, 4, 5]:
            play_background_music(_current_background_music)


# Boucle principale du diaporama
# Main slideshow loop.
def start_slideshow():
    pi_model = get_pi_model()
    global _current_background_music
    try:
        logger.debug(tr('📸 Starting slideshow initialization.'))
        config = load_config()
        logger.debug(tr('📸 Config loaded. show_clock: %(value_0)s, show_weather: %(value_1)s', value_0=config.get('show_clock'), value_1=config.get('show_weather')))
        
      
        
        time.sleep(2)
        logger.debug(tr('📸 Attente de 2s pour stabilisation '))
        
        # ✅ NOUVEAU : Initialiser uniquement les modules d'affichage et de police pour économiser du CPU (éviter d'init le mixer)
        # ✅ NEW: Initialize only the display and font modules to save CPU (avoid initializing the mixer).
        pygame.display.init()
        pygame.font.init()
        logger.debug(tr('📸 Pygame display and font modules initialized.'))
        
        # ✅ FORCER l'initialisation du module display
        # ✅ FORCE initialization of the display module.
        pygame.display.init()
        logger.debug(tr('📸 pygame.display.init() appelé explicitement'))
        
        # Vérifier les infos d'environnement
        # Check the environment information.
        logger.debug(tr('📸 Environment check:'))
        logger.debug(tr('   DISPLAY=%(value_0)s', value_0=os.environ.get('DISPLAY', 'NOT SET')))
        logger.debug(tr('   WAYLAND_DISPLAY=%(value_0)s', value_0=os.environ.get('WAYLAND_DISPLAY', 'NOT SET')))
        logger.debug(tr('   XDG_RUNTIME_DIR=%(value_0)s', value_0=os.environ.get('XDG_RUNTIME_DIR', 'NOT SET')))
        logger.debug(tr('   SDL_VIDEODRIVER=%(value_0)s', value_0=os.environ.get('SDL_VIDEODRIVER', 'NOT SET')))
        
        # ✅ NOUVEAU : Vérifier que pygame.display.get_driver() fonctionne
        # ✅ NEW: Check that pygame.display.get_driver() works.
        try:
            driver = pygame.display.get_driver()
            logger.debug(tr('📸 Driver vidéo détecté: %(value_0)s', value_0=driver))
        except Exception as e:
            logger.error(tr('❌ Impossible de détecter le driver: %(value_0)s', value_0=e))
        
        info = pygame.display.Info()
        SCREEN_WIDTH, SCREEN_HEIGHT = info.current_w, info.current_h
        logger.debug(tr('📸 Screen resolution detected: %(value_0)sx%(value_1)s', value_0=SCREEN_WIDTH, value_1=SCREEN_HEIGHT))
        
        # Si résolution invalide, forcer 1920x1080
        # If the resolution is invalid, force 1920x1080.
        if SCREEN_WIDTH == 0 or SCREEN_HEIGHT == 0:
            logger.warning(tr('❌ Résolution invalide détectée (0x0), utilisation de 1920x1080 par défaut'))
            SCREEN_WIDTH, SCREEN_HEIGHT = 1920, 1080
        
        # Création de l'écran
        # Create the screen.
        logger.debug(tr("📸 Tentative de création de l'écran %(value_0)sx%(value_1)s...", value_0=SCREEN_WIDTH, value_1=SCREEN_HEIGHT))
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
        logger.info(tr('✅ Écran créé avec succès : %(value_0)s', value_0=screen.get_size()))
        
        pygame.mouse.set_visible(False)
        logger.debug(tr('📸 Mouse cursor hidden.'))


        # --- Enregistrement des gestionnaires de signaux ---
        # --- Register signal handlers ---
        signal.signal(signal.SIGUSR1, signal_handler_next)      # Pour "suivant"
        signal.signal(signal.SIGUSR2, signal_handler_previous)   # Pour "précédent"
        signal.signal(signal.SIGTSTP, signal_handler_pause_toggle) # Pour "pause/reprendre"
        logger.debug(tr('📸 Signal handlers registered.'))

        # Initialiser le fichier de statut
        # Initialize the status file.
        update_status_file({"paused": False})

        import locale
        language_locales = {
            "fr": "fr_FR.UTF-8",
            "en": "C",
            "es": "es_ES.UTF-8",
            "de": "de_DE.UTF-8",
            "ja": "ja_JP.UTF-8",
        }
        date_locale = language_locales.get(get_global_language(), "C")
        try:
            locale.setlocale(locale.LC_TIME, date_locale)
        except locale.Error:
            # English locale is always available and avoids French date names as a fallback.
            locale.setlocale(locale.LC_TIME, "C")

        # --- Gestion du bouton physique ---
        # --- Physical button handling ---
        button_enabled = config.get("button_enabled", False)
        button_pin = int(config.get("button_pin", 23)) # GPIO 23 par défaut

        if GPIO_AVAILABLE and button_enabled:
            try:
                # Nettoyage d'une éventuelle configuration précédente du pin
                # Clean up any previous pin configuration.
                GPIO.remove_event_detect(button_pin)
                # Configuration du pin en entrée avec une résistance de pull-up interne.
                # Configure the pin as input with an internal pull-up resistor.
                # Le bouton doit connecter le pin au GND.
                # The button should connect the pin to GND.
                GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                
                # Ajout de la détection d'événement sur front descendant (appui sur le bouton)
                # Detect a falling edge event (button press).
                # bouncetime évite les détections multiples pour un seul appui.
                # bouncetime prevents multiple detections for a single press.
                GPIO.add_event_detect(button_pin, GPIO.FALLING, callback=button_callback, bouncetime=500)
                logger.info(tr('✅ Bouton physique activé sur le pin GPIO %(value_0)s.', value_0=button_pin))
            except Exception as e:
                logger.error(tr("❌ Erreur lors de l'initialisation du bouton GPIO %(value_0)s: %(value_1)s", value_0=button_pin, value_1=e))
        # --- FIN : Gestion du bouton physique ---
        # --- END: Physical button handling ---

        logger.debug(tr('📸 Entering main slideshow loop.'))
        
        # --- Initialisation de la surface précédente pour la transition ---
        # --- Initialize the previous surface for transitions ---
        previous_photo_surface = None

        # --- Vérification et chargement de la playlist personnalisée (une seule fois) ---
        # --- Check for and load a custom playlist (once) ---
        custom_playlist = None
        playlist_name = None
        is_custom_run = False # Drapeau pour indiquer un cycle de playlist unique
        if os.path.exists(CUSTOM_PLAYLIST_FILE):
            try:
                with open(CUSTOM_PLAYLIST_FILE, 'r') as f:
                    playlist_data = json.load(f)
                
                if isinstance(playlist_data, dict) and 'name' in playlist_data and 'photos' in playlist_data:
                    playlist_name = playlist_data['name']
                    custom_playlist_paths = playlist_data['photos']
                else:
                    # Fallback pour l'ancienne structure (juste une liste de chemins)
                    # Fallback for the old structure (a list of paths only).
                    custom_playlist_paths = playlist_data
                
                    # Convertir les chemins relatifs en chemins absolus
                    # Convert relative paths to absolute paths.
                custom_playlist = [str(Path(BASE_DIR) / 'static' / 'prepared' / p) for p in custom_playlist_paths]
                
                # Gestion de la musique
                # Music handling.
                _current_background_music = playlist_data.get('music_file')
                if _current_background_music:
                    play_background_music(_current_background_music)

                logger.info(tr("📸 Playlist personnalisée '%(value_0)s' chargée avec %(value_1)s photos.", value_0=playlist_name or 'Sans nom', value_1=len(custom_playlist)))
                is_custom_run = True # On active le drapeau pour le premier passage
                update_status_file({"is_custom": True})
                os.remove(CUSTOM_PLAYLIST_FILE) # Supprimer pour ne pas la réutiliser au prochain démarrage
            except Exception as e:
                logger.info(tr('📸 Erreur chargement playlist personnalisée: %(value_0)s. Utilisation de la playlist par défaut.', value_0=e))

        # Afficher l'écran titre si une playlist personnalisée est lancée
        # Show the title screen if a custom playlist is running.
        if playlist_name:
            # Utiliser une durée spécifique pour les écrans d'info, configurable
            # Use a configurable duration for information screens.
            info_duration = int(config.get("info_display_duration", 5))
            display_title_slide(screen, SCREEN_WIDTH, SCREEN_HEIGHT, playlist_name, info_duration, config, photos_for_slide=custom_playlist)
            previous_photo_surface = screen.copy() # Capturer l'écran titre pour la première transition

        while True:
            config = load_config() # Recharger la config à chaque itération

            # --- CORRECTION: Charger les paramètres de transition ici pour qu'ils soient toujours définis ---
            # --- FIX: Load the transition settings here so they are always defined ---
            # Auparavant, ils n'étaient définis que si aucune playlist personnalisée n'était utilisée.
            # Previously, they were only defined when no custom playlist was in use.
            transition_type = config.get("transition_type", "fade")
            transition_enabled = config.get("transition_enabled", True)
            transition_duration = float(config.get("transition_duration", 1.0))

            # --- Vérification et affichage immédiat de nouvelle carte postale ---
            # --- Check for and immediately display a new postcard ---
            if NEW_POSTCARD_FLAG.exists():
                logger.info(tr('📸 Nouvelle carte postale détectée.'))
                
                # Déclencher le clignotement de l'icône pour 30 secondes
                # Make the icon blink for 30 seconds.
                global _envelope_blink_end_time
                _envelope_blink_end_time = datetime.now() + timedelta(seconds=30)

                new_postcard_path_str = ""
                try:
                    # 1. Lire le chemin de la nouvelle photo
                    # 1. Read the path to the new photo.
                    with open(NEW_POSTCARD_FLAG, 'r') as f:
                        new_postcard_path_str = f.read().strip()
                    
                    new_postcard_path = Path(new_postcard_path_str)

                    if new_postcard_path.exists():
                        # 2. Jouer le son
                        # 2. Play the sound.
                        lang = config.get('language', 'fr') # Récupérer la langue, avec 'fr' comme défaut
                        
                        # Construire le chemin du son spécifique à la langue
                        # Build the path to the language-specific sound.
                        lang_sound_path = SOUNDS_DIR / f'notification_{lang}.wav'
                        
                        # Utiliser le son spécifique s'il existe, sinon le son par défaut
                        # Use the language-specific sound if available; otherwise, use the default.
                        notification_sound_path = lang_sound_path if lang_sound_path.exists() else SOUNDS_DIR / 'notification.wav'
                        
                        if notification_sound_path.exists():
                            if not pygame.mixer.get_init(): # S'assurer que le mixer est initialisé
                                pygame.mixer.init()
                            # Appliquer le volume configuré
                            # Apply the configured volume.
                            volume = int(config.get('notification_sound_volume', 80)) / 100.0
                            pygame.mixer.music.set_volume(volume)
                            notification_sound = pygame.mixer.Sound(str(notification_sound_path))
                            notification_sound.play()
                        
                        # 3. Afficher immédiatement la nouvelle carte postale
                        # 3. Display the new postcard immediately.
                        logger.info(tr('📸 Affichage immédiat de la nouvelle carte postale : %(value_0)s', value_0=new_postcard_path))
                        
                        # Recharger la police pour l'overlay
                        # Reload the overlay font.
                        font_path_config = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
                        clock_font_size_config = int(config.get("clock_font_size", 72))
                        try:
                            main_font_loaded = pygame.font.Font(font_path_config, clock_font_size_config)
                        except Exception as e:
                            main_font_loaded = pygame.font.SysFont("Arial", clock_font_size_config)

                        pil_image = Image.open(new_postcard_path)

                        # Afficher avec pan/zoom pour la durée configurée
                        # Display with pan/zoom for the configured duration.
                        display_photo_with_pan_zoom(screen, pil_image, SCREEN_WIDTH, SCREEN_HEIGHT, config, main_font_loaded, ignore_postcard_flag=True, photo_path=None)
                        
                        # Mettre à jour la surface précédente pour la transition suivante
                        # Update the previous surface for the next transition.
                        previous_photo_surface = screen.copy()
                    else:
                        logger.info(tr("📸 Erreur: le chemin '%(value_0)s' dans le fichier drapeau n'existe pas.", value_0=new_postcard_path_str))

                except Exception as e:
                    logger.info(tr('📸 Erreur lors du traitement de la nouvelle carte postale: %(value_0)s', value_0=e))
                    traceback.print_exc()
                finally:
                    # 4. Supprimer le drapeau pour ne pas rejouer
                    # 4. Remove the flag so the postcard is not shown again.
                    if NEW_POSTCARD_FLAG.exists():
                        NEW_POSTCARD_FLAG.unlink()

            # --- Construction de la playlist ---
            # --- Build the playlist ---
            if is_custom_run:
                playlist = custom_playlist
            else:
                # Construction de la playlist par défaut
                # Build the default playlist.
                filter_states = load_filter_states()
                favorites = load_favorites()
                display_sources = config.get("display_sources", ["immich"])
                slideshow_video_enabled = config.get("slideshow_video_enabled", True)
                
                all_media = []
                for source in display_sources:
                    source_dir = PREPARED_BASE_DIR / source
                    if source_dir.is_dir():
                        base_photos = [f for f in source_dir.iterdir() if f.is_file() and (f.suffix.lower() in ('.jpg', '.jpeg', '.png') or f.suffix.lower() in VIDEO_EXTENSIONS) and not f.name.endswith(('_polaroid.jpg', '_thumbnail.jpg', '_postcard.jpg'))]
                        for photo_path_obj in base_photos:
                            # Filtrer les vidéos si l'option est désactivée
                            # Filter out videos if the option is disabled.
                            if photo_path_obj.suffix.lower() in VIDEO_EXTENSIONS and not slideshow_video_enabled:
                                continue
                                
                            path_to_display = get_path_to_display(photo_path_obj, source, filter_states)
                            all_media.append(path_to_display)
                
                playlist = build_playlist(all_media, config, favorites)
                random.shuffle(playlist)
            
            # --- Chargement de la police à chaque itération ---
            # --- Load the font on every iteration ---
            # C'est plus robuste, surtout après une réinitialisation de l'affichage.
            # This is more robust, especially after a display reset.
            font_path_config = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
            clock_font_size_config = int(config.get("clock_font_size", 72))
            try:
                main_font_loaded = pygame.font.Font(font_path_config, clock_font_size_config)
            except Exception as e:
                logger.info(tr('Erreur chargement police : %(value_0)s. Utilisation de la police système.', value_0=e))
                main_font_loaded = pygame.font.SysFont("Arial", clock_font_size_config)
            # --- Fin du chargement de la police ---
            # --- End of font loading ---
            
            if not playlist:
                logger.info(tr('Aucune photo trouvée dans les sources activées. Vérification dans 60 secondes.'))
                
                screen.fill((0, 0, 0))
                
                text_color = parse_color(config.get("clock_color", "#FFFFFF"))
                outline_color = parse_color(config.get("clock_outline_color", "#000000"))
                
                try:
                    font_path = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
                    font_size = int(config.get("clock_font_size", 72) * 0.6) # Augmenté de 0.5
                    message_font = pygame.font.Font(font_path, font_size)
                    ip_font_size = int(config.get("clock_font_size", 72) * 0.8) # Augmenté de 0.65
                    ip_font = pygame.font.Font(font_path, ip_font_size)
                    small_font_size = int(config.get("clock_font_size", 72) * 0.4) # Augmenté de 0.35
                    small_font = pygame.font.Font(font_path, small_font_size)
                except Exception:
                    message_font = pygame.font.SysFont("Arial", 48)
                    ip_font = pygame.font.SysFont("Arial", 64)
                    small_font = pygame.font.SysFont("Arial", 32)

                # --- Logo ---
                logo_surface, logo_height, logo_spacing = None, 0, 30
                try:
                    logo_path = Path(BASE_DIR) / 'static' / 'pimmich_logo.png'
                    if logo_path.exists():
                        logo_img = pygame.image.load(str(logo_path)).convert_alpha()
                        original_width, original_height = logo_img.get_size()
                        new_width = 300
                        new_height = int(new_width * (original_height / original_width))
                        logo_surface = pygame.transform.smoothscale(logo_img, (new_width, new_height))
                        logo_height = logo_surface.get_height()
                except Exception as e:
                    logger.info(tr('Erreur chargement du logo : %(value_0)s', value_0=e))

                # --- Génération du QR Code ---
                # --- Generate the QR code ---
                qr_surface, qr_height, qr_spacing = None, 0, 30
                try:
                    ip_address_for_qr = get_local_ip()
                    url = f"http://{ip_address_for_qr}"
                    qr_img_pil = qrcode.make(url, box_size=8).convert('RGB')
                    qr_surface = pygame.image.fromstring(qr_img_pil.tobytes(), qr_img_pil.size, qr_img_pil.mode)
                    qr_height = qr_surface.get_height()
                except Exception as e:
                    logger.info(tr('Erreur génération QR code : %(value_0)s', value_0=e))

                ip_address = get_local_ip()
                messages = [
                    (message_font, _("Aucune photo trouvée.")),
                    (ip_font, _("Configurez sur : http://%(ip)s", ip=ip_address)),
                    (small_font, _("(Identifiants dans credentials.json à la racine de la SD)")),
                    (message_font, _("Résolution de l'écran : [%(w)s x %(h)s]", w=SCREEN_WIDTH, h=SCREEN_HEIGHT)),
                    (message_font, _("Nouvelle tentative dans 60 secondes..."))
                ]
                
                line_spacing = 20
                text_block_height = sum(font.get_height() for font, _ in messages) + (len(messages) - 1) * line_spacing
                
                # Calcul de la hauteur totale pour un centrage parfait
                # Calculate the total height for precise centering.
                total_height = text_block_height
                if logo_surface: total_height += logo_height + logo_spacing
                if qr_surface: total_height += qr_height + qr_spacing + small_font.get_height() + 10
                current_y = (SCREEN_HEIGHT - total_height) // 2

                if logo_surface:
                    logo_rect = logo_surface.get_rect(centerx=SCREEN_WIDTH // 2, top=current_y)
                    screen.blit(logo_surface, logo_rect)
                    current_y += logo_height + logo_spacing

                for font, txt in messages:
                    text_surface = font.render(txt, True, text_color)
                    text_rect = text_surface.get_rect(centerx=SCREEN_WIDTH // 2, top=current_y)
                    draw_text_with_outline(screen, txt, font, text_color, outline_color, text_rect.topleft, anchor="topleft")
                    current_y += font.get_height() + line_spacing

                # Affichage du QR Code
                # Display the QR code.
                if qr_surface:
                    current_y += qr_spacing - line_spacing # Ajuster l'espacement avant le QR
                    qr_title_text = _("Scannez pour configurer")
                    qr_title_surface = small_font.render(qr_title_text, True, text_color)
                    qr_title_rect = qr_title_surface.get_rect(centerx=SCREEN_WIDTH // 2, top=current_y)
                    draw_text_with_outline(screen, qr_title_text, small_font, text_color, outline_color, qr_title_rect.topleft, anchor="topleft")
                    current_y += qr_title_surface.get_height() + 10
                    qr_rect = qr_surface.get_rect(centerx=SCREEN_WIDTH // 2, top=current_y)
                    screen.blit(qr_surface, qr_rect)
                
                pygame.display.flip()

                time.sleep(60)
                continue

            playlist_index = 0
            while 0 <= playlist_index < len(playlist):
                # Vérifier si une carte postale est arrivée pour sortir de la boucle et la traiter immédiatement
                # Check for an incoming postcard; if found, exit the loop and process it immediately.
                if NEW_POSTCARD_FLAG.exists():
                    break

                photo_path = playlist[playlist_index]
                
                # Réinitialiser les requêtes de changement de photo
                # Reset photo-change requests.
                global next_photo_requested, previous_photo_requested
                next_photo_requested = False
                previous_photo_requested = False

                logger.info(tr('🖼️ Affichage de la photo: %(value_0)s', value_0=photo_path))
                
                # --- Contrôle du ventilateur ---
                # --- Fan control ---
                if GPIO_AVAILABLE:
                    try:
                        temp = psutil.sensors_temperatures()['cpu_thermal'][0].current
                        control_fan(temp)
                    except Exception as e:
                        logger.debug(tr('Erreur lors de la lecture de la température ou du contrôle du ventilateur : %(value_0)s', value_0=e))

                # --- CORRECTIF: Vérifier si le fichier existe avant de tenter de l'afficher ---
                # --- FIX: Check whether the file exists before trying to display it ---
                if not os.path.exists(photo_path):
                    logger.warning(tr('🖼️ Fichier non trouvé (probablement supprimé) : %(value_0)s. Passage au suivant.', value_0=photo_path))
                    playlist_index += 1
                    continue

                # Vérifier si le fichier est une vidéo ou une image
                # Check whether the file is a video or an image.
                is_video = any(photo_path.lower().endswith(ext) for ext in VIDEO_EXTENSIONS)

                # Écrire le chemin de la photo actuelle dans le fichier d'état
                # Write the current photo path to the status file.
                try:
                    with open(CURRENT_PHOTO_FILE, "w") as f:
                        path_to_write = Path(photo_path)
                        if is_video:
                            # Pour une vidéo, on écrit le chemin de sa vignette pour l'aperçu live
                            # For a video, write the thumbnail path for the live preview.
                            thumbnail_path = path_to_write.with_name(f"{path_to_write.stem}_thumbnail.jpg")
                            if thumbnail_path.exists():
                                path_to_write = thumbnail_path

                        # Convertir le chemin absolu en chemin relatif au dossier 'static'
                        # Convert the absolute path to one relative to the 'static' directory.
                        relative_path = path_to_write.relative_to(Path(BASE_DIR) / 'static')
                        f.write(str(relative_path))
                except Exception as e:
                    logger.info(tr('Erreur écriture fichier photo actuelle : %(value_0)s', value_0=e))

                if is_video:
                    display_video(screen, photo_path, SCREEN_WIDTH, SCREEN_HEIGHT, config, main_font_loaded, previous_photo_surface, pygame.time.Clock())
                    
                    # Si Pygame a été fermé pour la vidéo (sur tous les Raspberry Pi), on ré-initialise l'affichage.
                    # If Pygame was closed for video playback (on all Raspberry Pi models), reinitialize the display.
                    # On laisse 0.8 seconde de pause pour laisser Wayland détruire la surface mpv avant de relancer Pygame.
                    # Wait 0.8 seconds so Wayland can destroy the mpv surface before restarting Pygame.
                    if pi_model in [1, 2, 3, 4, 5]:
                        logger.info(tr("📸 Attente de 0.8s de stabilisation avant réinitialisation d'affichage..."))
                        time.sleep(0.8)
                        screen, SCREEN_WIDTH, SCREEN_HEIGHT = reinit_pygame()
                        # Recharger la police car pygame.quit() l'a invalidée
                        # Reload the font because pygame.quit() invalidated it.
                        font_path_config = config.get("clock_font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
                        clock_font_size_config = int(config.get("clock_font_size", 72))
                        try:
                            main_font_loaded = pygame.font.Font(font_path_config, clock_font_size_config)
                        except Exception:
                            main_font_loaded = pygame.font.SysFont("Arial", clock_font_size_config)
                        # Relancer la musique si elle était active
                        # Restart the music if it was playing.
                        if _current_background_music:
                            play_background_music(_current_background_music)
                    else:
                        # Cas général (PC de bureau)
                        # General case (desktop PC).
                        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
                        pygame.mouse.set_visible(False)
                        
                    # Afficher le bandeau de reprise après la lecture de la vidéo (avec symbole flèche circulaire unicode supportée)
                    # Show the resume banner after video playback (using a supported Unicode circular arrow).
                    if main_font_loaded:
                        draw_loading_banner(screen, tr("↻ Reprise du diaporama..."), SCREEN_WIDTH, SCREEN_HEIGHT, main_font_loaded)
                        time.sleep(0.5)
                else: # C'est une image
                    current_pil_image = None # Initialize to None to ensure it's always defined
                    try:
                        # Perform transition if it's not the first photo and transition is enabled
                        if previous_photo_surface is not None and transition_enabled and transition_duration > 0 and transition_type != "none": # Added transition_type check
                            current_pil_image = perform_transition(screen, previous_photo_surface, photo_path, transition_duration, SCREEN_WIDTH, SCREEN_HEIGHT, main_font_loaded, config, transition_type)
                            # Si la transition a échoué (ex: fichier non trouvé), on passe au suivant
                            # If the transition failed (e.g. the file was not found), move to the next item.
                            if current_pil_image is None:
                                previous_photo_surface = None # Réinitialiser pour ne pas tenter de transitionner depuis une surface vide
                                playlist_index += 1
                                continue
                        else:
                            # For the first image or no transition, just load and blit it directly
                            current_pil_image = Image.open(photo_path)
                            if current_pil_image.mode != 'RGB': current_pil_image = current_pil_image.convert('RGB')
                            # For the first image, we need to blit it directly before pan/zoom takes over
                            # This blit is only for the initial display, not part of pan/zoom animation
                            screen.blit(pygame.image.fromstring(current_pil_image.tobytes(), current_pil_image.size, current_pil_image.mode), (0,0)) # type: ignore
                            draw_overlay(screen, SCREEN_WIDTH, SCREEN_HEIGHT, config, main_font_loaded, None)
                            pygame.display.flip()
                    except Exception as e:
                        logger.info(tr('🖼️ Error loading or transitioning to photo %(value_0)s: %(value_1)s', value_0=photo_path, value_1=e))
                        traceback.print_exc()
                        current_pil_image = None # Explicitly set to None on error
                        playlist_index += 1
                        continue

                    if current_pil_image: # Only proceed if image was successfully loaded
                        display_photo_with_pan_zoom(screen, current_pil_image, SCREEN_WIDTH, SCREEN_HEIGHT, config, main_font_loaded, photo_path)
                        previous_photo_surface = screen.copy()
                    else:
                        logger.info(tr('🖼️ Skipping photo %(value_0)s due to loading error.', value_0=photo_path))

                # --- Logique de navigation ---
                # --- Navigation logic ---
                if next_photo_requested:
                    playlist_index += 1
                elif previous_photo_requested:
                    playlist_index -= 1
                else: # Comportement normal
                    playlist_index += 1

                # Gérer le bouclage de la playlist
                # Handle playlist looping.
                if playlist_index >= len(playlist): playlist_index = 0
                if playlist_index < 0: playlist_index = len(playlist) - 1

            # --- Logique de fin de playlist personnalisée ---
            # --- Custom playlist end logic ---
            if is_custom_run:
                logger.info(tr('🖼️ Playlist personnalisée terminée. Retour au diaporama standard.'))
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.fadeout(2000)
                _current_background_music = None
                is_custom_run = False # Le prochain tour de boucle while True construira la playlist par défaut.
                update_status_file({"is_custom": False})
                playlist = [] # Vider la playlist pour forcer la reconstruction.
    except KeyboardInterrupt:
        logger.info(tr('Arrêt manuel du diaporama.'))
    except Exception as e:
        logger.info(tr('FATAL ERROR IN SLIDESHOW: %(value_0)s', value_0=e))
        traceback.print_exc() # Print full traceback for any unhandled error
    finally:
        # --- MODIFICATION SIGALOU 30/01/2026 ---
        # --- SIGALOU CHANGE 30/01/2026 ---
        # La gestion de l'alimentation de l'écran est maintenant centralisée dans le `slideshow_manager`.
        # Display power management is now centralized in `slideshow_manager`.
        # On retire l'appel ici pour éviter les doubles appels et les conditions de concurrence
        # The call is removed here to avoid duplicate calls and race conditions
        # qui pouvaient empêcher la prise connectée de s'éteindre correctement.
        # that could prevent the smart plug from switching off correctly.
        # from utils.display_manager import set_display_power
        # set_display_power(False)
        # Nettoyer le fichier d'état à la sortie
        # Clean up the status file on exit.
        if os.path.exists(CURRENT_PHOTO_FILE):
            os.remove(CURRENT_PHOTO_FILE)
        if os.path.exists(STATUS_FILE):
            os.remove(STATUS_FILE)
        pygame.quit()
        if GPIO_AVAILABLE:
            GPIO.cleanup()
        logger.info(tr('🖼️ Pygame exited cleanly.'))

if __name__ == "__main__":
    start_slideshow()
