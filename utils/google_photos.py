"""Small REST client for the Google Photos Picker API."""

from pathlib import Path
import mimetypes
import re

import requests
from werkzeug.utils import secure_filename


OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
PICKER_API_URL = "https://photospicker.googleapis.com/v1"


class GooglePhotosError(Exception):
    """A Google Photos OAuth or Picker API request failed."""


def _response_json(response):
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.ok:
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            message = error.get("message") or error.get("status")
        else:
            message = error
        raise GooglePhotosError(message or f"Google Photos returned HTTP {response.status_code}")
    return payload


def exchange_authorization_code(client_id, client_secret, code, redirect_uri):
    response = requests.post(
        OAUTH_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    return _response_json(response)


def get_access_token(config):
    refresh_token = config.get("google_photos_refresh_token")
    client_id = config.get("google_photos_client_id")
    client_secret = config.get("google_photos_client_secret")
    if not refresh_token or not client_id or not client_secret:
        raise GooglePhotosError("Google Photos is not connected. Configure OAuth and authorize an account first.")

    response = requests.post(
        OAUTH_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    token = _response_json(response)
    access_token = token.get("access_token")
    if not access_token:
        raise GooglePhotosError("Google did not return an access token.")
    return access_token


def picker_request(access_token, method, path, **kwargs):
    response = requests.request(
        method,
        f"{PICKER_API_URL}/{path.lstrip('/')}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
        **kwargs,
    )
    if response.status_code == 204:
        return {}
    return _response_json(response)


def list_session_media(access_token, session_id):
    media_items = []
    page_token = None
    while True:
        params = {"sessionId": session_id, "pageSize": 100}
        if page_token:
            params["pageToken"] = page_token
        payload = picker_request(access_token, "GET", "mediaItems", params=params)
        media_items.extend(payload.get("mediaItems", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            return media_items


def download_picked_media(access_token, item, destination_dir):
    media_file = item.get("mediaFile", {})
    base_url = media_file.get("baseUrl")
    mime_type = media_file.get("mimeType", "")
    if not base_url:
        raise GooglePhotosError("A selected Google Photos item has no download URL.")
    if not (mime_type.startswith("image/") or mime_type.startswith("video/")):
        raise GooglePhotosError(f"Unsupported Google Photos media type: {mime_type or 'unknown'}")

    is_video = mime_type.startswith("video/")
    url_suffix = "=dv" if is_video else "=d"
    original_name = secure_filename(media_file.get("filename") or "")
    extension = Path(original_name).suffix.lower()
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".mp4", ".mov", ".avi", ".mkv"}
    if extension not in allowed_extensions:
        extension = mimetypes.guess_extension(mime_type) or (".mp4" if is_video else ".jpg")
    if is_video and extension not in {".mp4", ".mov", ".avi", ".mkv"}:
        extension = ".mp4"
    if not is_video and extension not in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
        extension = ".jpg"

    item_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(item.get("id", "")))[:120]
    if not item_id:
        raise GooglePhotosError("A selected Google Photos item has no identifier.")
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{item_id}{extension}"
    temporary_destination = destination.with_name(destination.name + ".part")

    response = requests.get(
        f"{base_url}{url_suffix}",
        headers={"Authorization": f"Bearer {access_token}"},
        stream=True,
        timeout=(20, 180),
    )
    if not response.ok:
        _response_json(response)
    try:
        with temporary_destination.open("wb") as output_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output_file.write(chunk)
        temporary_destination.replace(destination)
    except Exception:
        temporary_destination.unlink(missing_ok=True)
        raise
    return destination
