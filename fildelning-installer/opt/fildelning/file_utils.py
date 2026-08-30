import os
import urllib.parse
import json
import subprocess


def get_base_url():
    env_url = os.environ.get("FILDELNING_BASE_URL")
    if env_url:
        return env_url.rstrip("/")

    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        dns_name = data["Self"]["DNSName"].rstrip(".")

        if not dns_name:
            raise RuntimeError("Tailscale DNS name is empty")

        return f"https://{dns_name}"

    except Exception as e:
        raise RuntimeError(
            f"Could not determine base URL. Set FILDELNING_BASE_URL "
            f"(e.g. https://files.yourdomain.com or http://82.70.50.231). "
            f"Tailscale fallback also failed: {e}"
        )


def safe_path(root, requested):
    """
    Convert a URL path into a filesystem path while preventing
    access outside root.
    """
    root = os.path.realpath(root)
    requested = urllib.parse.unquote(requested)
    requested = requested.lstrip("/")
    candidate = os.path.realpath(os.path.join(root, requested))

    if candidate != root and not candidate.startswith(root + os.sep):
        raise PermissionError("Path outside shared directory")

    return candidate


def format_size(size):
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size)

    for unit in units:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} EB"


def icon_for(filename, is_directory=False):
    if is_directory:
        return "📁"

    ext = os.path.splitext(filename)[1].lower()

    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}:
        return "🖼️"
    if ext in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        return "🎬"
    if ext in {".zip", ".7z", ".tar", ".gz", ".rar"}:
        return "📦"
    if ext in {".mp3", ".wav", ".flac", ".m4a"}:
        return "🎵"
    if ext in {".pdf"}:
        return "📕"
    if ext in {".txt", ".md"}:
        return "📄"

    return "📄"