"""Safe extraction of image and video albums from uploaded ZIP files."""

import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

from werkzeug.utils import secure_filename

from .localization import tr


MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
MAX_EXTRACTED_BYTES = 4 * 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEDIA_FILES = 10_000
CHUNK_SIZE = 1024 * 1024

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif",
    ".mp4", ".mov", ".avi", ".mkv",
}


class AlbumArchiveError(Exception):
    """The uploaded ZIP is invalid or exceeds supported limits."""


def _album_prefix(album_name, archive_name, archive_digest):
    label = secure_filename(album_name or Path(archive_name).stem)[:48].strip("._-") or "album"
    return f"{label}_{archive_digest[:8]}"


def extract_album_zip(uploaded_file, archive_name, destination_dir, album_name=""):
    """Save supported ZIP media to a flat source directory and return filenames."""
    if Path(archive_name or "").suffix.lower() != ".zip":
        raise AlbumArchiveError(tr("Choisissez une archive ZIP."))

    temporary_archive = None
    try:
        with tempfile.NamedTemporaryFile(prefix="pimmich_album_", suffix=".zip", delete=False) as archive_file:
            temporary_archive = Path(archive_file.name)
            uploaded_file.save(archive_file)
    except Exception:
        if temporary_archive is not None:
            temporary_archive.unlink(missing_ok=True)
        raise

    staging_dir = None
    try:
        archive_size = temporary_archive.stat().st_size
        if archive_size > MAX_UPLOAD_BYTES:
            raise AlbumArchiveError(tr("Le fichier ZIP dépasse la limite d'envoi de 1 Go."))

        archive_digest = hashlib.sha256()
        with temporary_archive.open("rb") as archive_file:
            for chunk in iter(lambda: archive_file.read(CHUNK_SIZE), b""):
                archive_digest.update(chunk)

        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(tempfile.mkdtemp(prefix=".album-import-", dir=destination_dir))
        prefix = _album_prefix(album_name, archive_name, archive_digest.hexdigest())

        try:
            with zipfile.ZipFile(temporary_archive) as archive:
                media_members = []
                declared_total = 0
                for index, info in enumerate(archive.infolist()):
                    if info.is_dir():
                        continue
                    normalized_name = info.filename.replace("\\", "/")
                    member_path = PurePosixPath(normalized_name)
                    if member_path.is_absolute() or ".." in member_path.parts or not member_path.parts:
                        continue
                    if member_path.parts[0] == "__MACOSX" or any(part.startswith(".") for part in member_path.parts):
                        continue
                    if stat.S_ISLNK(info.external_attr >> 16):
                        continue

                    extension = Path(member_path.name).suffix.lower()
                    if extension not in SUPPORTED_EXTENSIONS:
                        continue
                    if info.flag_bits & 0x1:
                        raise AlbumArchiveError(tr("Les archives ZIP protégées par mot de passe ne sont pas prises en charge."))
                    if info.file_size > MAX_MEMBER_BYTES:
                        raise AlbumArchiveError(tr("Un élément de l'archive est trop volumineux : %(value_0)s", value_0=member_path.name))

                    declared_total += info.file_size
                    if declared_total > MAX_EXTRACTED_BYTES:
                        raise AlbumArchiveError(tr("Le contenu de l'archive dépasse la limite d'extraction de 4 Go."))
                    if len(media_members) >= MAX_MEDIA_FILES:
                        raise AlbumArchiveError(tr("L'archive contient plus de 10 000 fichiers média pris en charge."))

                    member_key = hashlib.sha256(f"{index}:{normalized_name}".encode("utf-8", "replace")).hexdigest()[:10]
                    safe_stem = secure_filename(Path(member_path.name).stem)[:60] or "media"
                    output_name = f"{prefix}_{member_key}_{safe_stem}{extension}"
                    media_members.append((info, output_name))

                if not media_members:
                    raise AlbumArchiveError(tr("L'archive ZIP ne contient aucune photo ou vidéo prise en charge."))

                extracted_total = 0
                staged_files = []
                for info, output_name in media_members:
                    staged_path = staging_dir / output_name
                    member_bytes = 0
                    with archive.open(info, "r") as source, staged_path.open("wb") as destination:
                        while True:
                            chunk = source.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            member_bytes += len(chunk)
                            extracted_total += len(chunk)
                            if member_bytes > info.file_size or member_bytes > MAX_MEMBER_BYTES:
                                raise AlbumArchiveError(tr("Un élément de l'archive dépasse la taille déclarée : %(value_0)s", value_0=info.filename))
                            if extracted_total > MAX_EXTRACTED_BYTES:
                                raise AlbumArchiveError(tr("Le contenu de l'archive dépasse la limite d'extraction de 4 Go."))
                            destination.write(chunk)
                    if member_bytes != info.file_size:
                        raise AlbumArchiveError(tr("La taille d'un élément de l'archive ne correspond pas : %(value_0)s", value_0=info.filename))
                    staged_files.append(staged_path)

            final_paths = []
            for staged_path in staged_files:
                final_path = destination_dir / staged_path.name
                os.replace(staged_path, final_path)
                final_paths.append(final_path)
            return final_paths
        except AlbumArchiveError:
            raise
        except Exception as e:
            raise AlbumArchiveError(tr("Impossible de lire l'archive ZIP : %(value_0)s", value_0=e)) from e
    finally:
        if staging_dir is not None:
            shutil.rmtree(staging_dir, ignore_errors=True)
        temporary_archive.unlink(missing_ok=True)
