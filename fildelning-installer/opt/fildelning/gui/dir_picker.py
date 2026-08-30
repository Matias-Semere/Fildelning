"""
dir_picker.py
Ansvar: välja en mapp via en dialog. Försöker zenity först (nu
bekräftat fungerande på Plasma Bigscreen efter portal-cache-rensning
och portals.conf-uppdatering), med Qt:s inbyggda DontUseNativeDialog
som garanterad fallback om zenity saknas, avbryts av fel, eller
kraschar (t.ex. om KDE-buggnummer 513595 återkommer).

Notera: zenity-fönstret kan hamna bakom huvudfönstret på grund av en
känd KWin-fokusbugg (fönsterregel med "Skydd mot fokusstöld" satt
till Ingen + "Initial placement" Centrerad rekommenderas i Fönster-
regler-inställningarna för att lösa detta på systemnivå). Timeouten
här är en sista säkerhetsspärr, inte den primära lösningen - om
zenity ofta hamnar bakom andra fönster, fixa KWin-regeln istället
för att bara höja timeouten.
"""

from __future__ import annotations

import shutil
import subprocess

from PySide6.QtWidgets import QFileDialog, QWidget

ZENITY_TIMEOUT_SECONDS = 90


def _pick_directory_zenity(title: str, start_dir: str) -> str | None:
    """Returnerar vald sökväg, eller None om zenity saknas, användaren
    avbryter, eller anropet misslyckas/timeoutar på något sätt."""
    if shutil.which("zenity") is None:
        return None

    cmd = [
        "zenity",
        "--file-selection",
        "--directory",
        f"--title={title}",
        "--width=800",
        "--height=600",
    ]
    if start_dir:
        cmd.append(f"--filename={start_dir.rstrip('/')}/")

    process = None
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, _stderr = process.communicate(timeout=ZENITY_TIMEOUT_SECONDS)
    except (FileNotFoundError, OSError):
        return None
    except subprocess.TimeoutExpired:
        # Döda processen ordentligt istället för att lämna den kvar
        # spökande i bakgrunden om den fortfarande hänger dold.
        if process is not None:
            process.kill()
            process.communicate()
        return None

    # 0 = OK, 1 = Avbryt/Stäng, allt annat = fel eller krasch i zenity/portalen
    if process.returncode != 0:
        return None

    path = stdout.strip()
    return path or None


def _pick_directory_qt(parent: QWidget, title: str, start_dir: str) -> str:
    """Qt:s egen inbyggda filväljare, kringgår portalen helt."""
    return QFileDialog.getExistingDirectory(
        parent,
        title,
        start_dir,
        QFileDialog.ShowDirsOnly | QFileDialog.DontUseNativeDialog,
    )


def pick_directory(parent: QWidget, title: str, start_dir: str) -> str:
    """Publikt anrop som ersätter den gamla _pick_directory() i gui.py.
    Försöker zenity först, faller tillbaka till Qt-dialogen vid minsta
    tveksamhet. Returnerar alltid en sträng (tom vid avbrutet val),
    exakt som den gamla funktionen gjorde."""
    result = _pick_directory_zenity(title, start_dir)
    if result is not None:
        return result
    return _pick_directory_qt(parent, title, start_dir)
