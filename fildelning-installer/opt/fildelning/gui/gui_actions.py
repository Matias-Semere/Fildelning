"""
gui_actions.py
Ansvar: bryggan mellan GUI:t och den befintliga logiken i shares.py
samt Tailscale. Importerar shares.py/file_utils.py direkt (samma
sätt som share och receive gör) istället för att köra CLI:erna som
subprocess och tolka textutskrift.

Viktigt: get_base_url() kräver att Tailscale kör och kastar annars
RuntimeError. Ett CLI-kommando får gärna krascha på det, men ett
GUI-fönster ska inte vägra starta bara för att Tailscale är nere —
därför hämtas BASE_URL lat, per anrop, och felet omvandlas till
CommandError som gui.py redan vet hur man visar.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass

import sys
sys.path.insert(0, "/opt/fildelning")

from shares import (
    create_share,
    create_receive,
    load_shares,
    load_receives,
    remove_share,
    remove_receive,
)
from file_utils import get_base_url


class CommandError(Exception):
    """Kastas när en operation misslyckas, katalogen är ogiltig, eller
    Tailscale inte går att nå. Fail-early istället för att gissa."""


@dataclass
class LinkInfo:
    token: str
    path: str
    url: str
    kind: str  # "share" eller "receive"


@dataclass
class TailscaleStatus:
    active: bool
    hostname: str | None
    funnel_active: bool


def _base_url() -> str:
    try:
        return get_base_url()
    except RuntimeError as error:
        raise CommandError(f"Tailscale är inte tillgängligt: {error}") from error


def _validate_directory(directory: str) -> str:
    absolute = os.path.abspath(os.path.expanduser(directory))
    if not os.path.isdir(absolute):
        raise CommandError(f"Katalogen finns inte:\n{absolute}")
    return absolute


def start_share(directory: str) -> LinkInfo:
    absolute = _validate_directory(directory)
    base_url = _base_url()
    token = create_share(absolute)
    return LinkInfo(token=token, path=absolute, url=f"{base_url}/s/{token}", kind="share")


def start_receive(directory: str) -> LinkInfo:
    absolute = _validate_directory(directory)
    base_url = _base_url()
    token = create_receive(absolute)
    return LinkInfo(token=token, path=absolute, url=f"{base_url}/r/{token}", kind="receive")


def list_shares() -> list[LinkInfo]:
    base_url = _base_url()
    shares = load_shares()
    return [
        LinkInfo(token=token, path=data["directory"], url=f"{base_url}/s/{token}", kind="share")
        for token, data in shares.items()
    ]


def list_receives() -> list[LinkInfo]:
    base_url = _base_url()
    receives = load_receives()
    return [
        LinkInfo(token=token, path=data["directory"], url=f"{base_url}/r/{token}", kind="receive")
        for token, data in receives.items()
    ]


def stop_share(token: str) -> None:
    if not remove_share(token):
        raise CommandError("Token hittades inte.")


def stop_receive(token: str) -> None:
    if not remove_receive(token):
        raise CommandError("Token hittades inte.")


def stop_link(link: LinkInfo) -> None:
    if link.kind == "share":
        stop_share(link.token)
        return
    stop_receive(link.token)


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise CommandError(f"'{' '.join(cmd)}' misslyckades: {message}")
    return result.stdout.strip()


def tailscale_status() -> TailscaleStatus:
    if shutil.which("tailscale") is None:
        return TailscaleStatus(active=False, hostname=None, funnel_active=False)

    try:
        raw = _run(["tailscale", "status", "--json"])
        data = json.loads(raw)
    except (CommandError, json.JSONDecodeError):
        return TailscaleStatus(active=False, hostname=None, funnel_active=False)

    self_node = data.get("Self", {})
    hostname = self_node.get("DNSName", "").rstrip(".") or None
    active = bool(self_node.get("Online", False))

    funnel_active = False
    try:
        serve_output = _run(["tailscale", "serve", "status"])
        funnel_active = "funnel" in serve_output.lower()
    except CommandError:
        funnel_active = False

    return TailscaleStatus(active=active, hostname=hostname, funnel_active=funnel_active)
