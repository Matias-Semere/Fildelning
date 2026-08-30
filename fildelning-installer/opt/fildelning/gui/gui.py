"""
gui.py
Ansvar: bygga och rendera fönstret. All logik mot share/receive/
Tailscale ligger i gui_actions.py — den här filen anropar bara
funktioner och uppdaterar widgets. Fungerar lika bra på Plasma
Bigscreen som på ett vanligt skrivbord (ingen TV-specifik layout).

Notera 1: filväljaren använder uteslutande Qt:s egen inbyggda dialog
(DontUseNativeDialog). Plasma Bigscreen har en instabil
xdg-desktop-portal-kde-session (känt KDE-buggnummer 513595) som gör
att kdialog, zenity och native GTK/KDE-dialoger kan hänga sig eller
krascha. Qt:s inbyggda dialog ritas helt inom processen och går
aldrig via portalen, så den påverkas inte av det problemet.

Notera 2: utseendet bygger på Fusion-stilen + Qt:s inbyggda
colorScheme(). Kortens bakgrundsfärg räknas ut från fönstrets
faktiska luminans, så kontrasten blir rätt i både ljust och mörkt
läge. Knapparna har en lätt gradient + outset/inset-kant för en
"tryckbar" 3D-känsla, och accent-knappar kan färgas individuellt
(t.ex. grön för WhatsApp) via ett CSS-property.
"""

from __future__ import annotations

import sys
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import gui_actions as actions
from gui_actions import CommandError, LinkInfo
from dir_picker import pick_directory

OUTER_MARGIN = 40
SECTION_SPACING = 22
CARD_PADDING = 22
TAILSCALE_ADMIN_URL = "https://login.tailscale.com/admin"
WHATSAPP_URL = "https://web.whatsapp.com"
FACEBOOK_URL = "https://www.facebook.com"


def _is_dark_mode() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def _luminance(color: QColor) -> float:
    return 0.2126 * color.redF() + 0.7152 * color.greenF() + 0.0722 * color.blueF()


def _card_background(palette: QPalette) -> QColor:
    """Räknar ut en kortbakgrund som alltid skiljer sig synligt från
    fönstrets bakgrund, oavsett ljust eller mörkt tema. Trappar upp
    skillnaden tills luminanskontrasten är tydlig, istället för att
    gissa en fast procentsats som kan bli osynlig i vissa teman."""
    base = palette.color(QPalette.Window)
    dark = _is_dark_mode()

    color = QColor(base)
    for _ in range(6):
        candidate = color.lighter(112) if dark else color.darker(106)
        if abs(_luminance(candidate) - _luminance(base)) >= 0.04:
            return candidate
        color = candidate
    return color


def _border_color(palette: QPalette) -> QColor:
    base = palette.color(QPalette.Window)
    return base.lighter(140) if _is_dark_mode() else base.darker(118)


def _apply_shadow(widget: QWidget) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(28)
    shadow.setOffset(0, 5)
    shadow.setColor(QColor(0, 0, 0, 130 if _is_dark_mode() else 45))
    widget.setGraphicsEffect(shadow)


def _pick_directory(parent: QWidget, title: str, start_dir: str) -> str:
    """Qt:s egen inbyggda filväljare. DontUseNativeDialog gör att Qt
    ritar dialogen själv istället för att fråga skrivbordsmiljön via
    xdg-desktop-portal, vilket kringgår portal-instabiliteten helt."""
    return QFileDialog.getExistingDirectory(
        parent,
        title,
        start_dir,
        QFileDialog.ShowDirsOnly | QFileDialog.DontUseNativeDialog,
    )


class Card(QFrame):
    """En 'kort'-yta med rundade hörn, mjuk bakgrund, tunn kantlinje
    och skugga."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        self._refresh_style()
        _apply_shadow(self)

    def _refresh_style(self) -> None:
        background = _card_background(self.palette())
        border = _border_color(self.palette())
        self.setStyleSheet(f"""
            #card {{
                background-color: {background.name()};
                border: 1px solid {border.name()};
                border-radius: 16px;
            }}
        """)


class FolderRow(Card):
    """Ett kort med sökväg, 'Välj mapp'-knapp och en start-knapp."""

    def __init__(self, title: str, start_label: str, on_start):
        super().__init__()
        self._on_start = on_start

        title_label = QLabel(f"<b>{title}</b>")
        title_label.setStyleSheet("font-size: 15pt;")

        self.path_field = QLineEdit()
        self.path_field.setMinimumHeight(42)

        browse_button = QPushButton("Välj mapp")
        browse_button.setMinimumHeight(42)
        browse_button.clicked.connect(self._browse)

        start_button = QPushButton(start_label)
        start_button.setMinimumHeight(42)
        start_button.setProperty("accent", "blue")
        start_button.clicked.connect(self._start)

        path_row = QHBoxLayout()
        path_row.setSpacing(12)
        path_row.addWidget(self.path_field)
        path_row.addWidget(browse_button)

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.addWidget(title_label)
        layout.addLayout(path_row)
        layout.addWidget(start_button, alignment=Qt.AlignRight)
        self.setLayout(layout)

    def _browse(self) -> None:
        start_dir = self.path_field.text().strip() or ""
        folder = pick_directory(self, "Välj mapp", start_dir)
        if not folder:
            return
        self.path_field.setText(folder)

    def _start(self) -> None:
        folder = self.path_field.text().strip()
        if not folder:
            QMessageBox.warning(self, "Ingen mapp vald", "Välj en mapp först.")
            return
        self._on_start(folder)


class LinkRow(Card):
    """Ett kort per aktiv länk, med kopiera- och stopp-knapp."""

    def __init__(self, link: LinkInfo, on_stop, on_copy):
        super().__init__()
        icon = "📤" if link.kind == "share" else "📥"

        info_label = QLabel(f"{icon} {link.path}\n{link.url}")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-size: 12pt;")

        copy_button = QPushButton("Kopiera")
        copy_button.setMinimumHeight(38)
        copy_button.setProperty("accent", "blue")
        copy_button.clicked.connect(lambda: on_copy(link.url))

        stop_button = QPushButton("Stoppa")
        stop_button.setMinimumHeight(38)
        stop_button.setProperty("accent", "red")
        stop_button.clicked.connect(lambda: on_stop(link))

        layout = QHBoxLayout()
        layout.setSpacing(12)
        layout.addWidget(info_label, stretch=1)
        layout.addWidget(copy_button)
        layout.addWidget(stop_button)
        self.setLayout(layout)


class LinksCard(Card):
    def __init__(self):
        super().__init__()
        self.container = QVBoxLayout()
        self.container.setSpacing(14)

        title_label = QLabel("<b>Aktiva länkar</b>")
        title_label.setStyleSheet("font-size: 15pt;")

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.addWidget(title_label)
        layout.addLayout(self.container)
        self.setLayout(layout)


class TailscaleCard(Card):
    def __init__(self, on_refresh, on_settings, on_close, on_whatsapp, on_facebook):
        super().__init__()

        title_label = QLabel("<b>Tailscale</b>")
        title_label.setStyleSheet("font-size: 15pt;")

        self.status_label = QLabel("Okänd status")
        self.status_label.setStyleSheet("font-size: 12pt;")

        refresh_button = QPushButton("Uppdatera")
        refresh_button.setMinimumHeight(42)
        refresh_button.setProperty("accent", "blue")
        refresh_button.clicked.connect(on_refresh)

        settings_button = QPushButton("Inställningar")
        settings_button.setMinimumHeight(42)
        settings_button.clicked.connect(on_settings)

        close_button = QPushButton("Stäng")
        close_button.setMinimumHeight(42)
        close_button.setProperty("accent", "red")
        close_button.clicked.connect(on_close)

        row_one = QHBoxLayout()
        row_one.setSpacing(12)
        row_one.addWidget(refresh_button)
        row_one.addWidget(settings_button)
        row_one.addWidget(close_button)

        whatsapp_button = QPushButton("💬 WhatsApp Web")
        whatsapp_button.setMinimumHeight(42)
        whatsapp_button.setProperty("accent", "green")
        whatsapp_button.clicked.connect(on_whatsapp)

        facebook_button = QPushButton("📘 Facebook")
        facebook_button.setMinimumHeight(42)
        facebook_button.setProperty("accent", "blue")
        facebook_button.clicked.connect(on_facebook)

        row_two = QHBoxLayout()
        row_two.setSpacing(12)
        row_two.addWidget(whatsapp_button)
        row_two.addWidget(facebook_button)

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.addWidget(title_label)
        layout.addWidget(self.status_label)
        layout.addLayout(row_one)
        layout.addLayout(row_two)
        self.setLayout(layout)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fildelning")
        self.setMinimumSize(660, 620)

        self.links_card = LinksCard()
        self.tailscale_card = TailscaleCard(
            on_refresh=self.refresh_tailscale,
            on_settings=self._open_tailscale_admin,
            on_close=self.close,
            on_whatsapp=self._open_whatsapp,
            on_facebook=self._open_facebook,
        )

        scroll_content = QWidget()
        scroll_content.setLayout(self._build_layout())

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(scroll_content)

        self.setCentralWidget(scroll_area)

        self._setup_shortcuts()

        self.refresh_links()
        self.refresh_tailscale()

    def _setup_shortcuts(self) -> None:
        quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_shortcut.activated.connect(self.close)

    def _build_layout(self) -> QVBoxLayout:
        share_row = FolderRow("📤 Dela en mapp", "🔗 Starta delning", self.start_share)
        receive_row = FolderRow("📥 Ta emot filer", "🔗 Starta mottagning", self.start_receive)

        outer = QVBoxLayout()
        outer.setContentsMargins(OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN)
        outer.setSpacing(SECTION_SPACING)

        header = QLabel("Fildelning")
        header.setStyleSheet("font-size: 24pt; font-weight: 600;")
        outer.addWidget(header)

        outer.addWidget(share_row)
        outer.addWidget(receive_row)
        outer.addWidget(self.links_card)
        outer.addWidget(self.tailscale_card)
        outer.addStretch()
        return outer

    def start_share(self, folder: str) -> None:
        self._run_and_refresh(lambda: actions.start_share(folder))

    def start_receive(self, folder: str) -> None:
        self._run_and_refresh(lambda: actions.start_receive(folder))

    def stop_link(self, link: LinkInfo) -> None:
        self._run_and_refresh(lambda: actions.stop_link(link))

    def copy_url(self, url: str) -> None:
        QApplication.clipboard().setText(url)

    def refresh_links(self) -> None:
        self._clear_links_container()
        try:
            links = actions.list_shares() + actions.list_receives()
        except CommandError as error:
            self._show_error(error)
            return

        if not links:
            empty_label = QLabel("Inga aktiva länkar.")
            empty_label.setStyleSheet("font-size: 12pt;")
            self.links_card.container.addWidget(empty_label)
            return

        for link in links:
            self.links_card.container.addWidget(LinkRow(link, self.stop_link, self.copy_url))

    def refresh_tailscale(self) -> None:
        try:
            status = actions.tailscale_status()
        except CommandError as error:
            self.tailscale_card.set_status("Kunde inte hämta status")
            self._show_error(error)
            return

        state = "● Funnel aktiv" if status.funnel_active else "○ Funnel inaktiv"
        host = status.hostname or "okänd host"
        self.tailscale_card.set_status(f"{state}\n{host}")

    def _open_tailscale_admin(self) -> None:
        webbrowser.open(TAILSCALE_ADMIN_URL)

    def _open_whatsapp(self) -> None:
        webbrowser.open(WHATSAPP_URL)

    def _open_facebook(self) -> None:
        webbrowser.open(FACEBOOK_URL)

    def _run_and_refresh(self, action) -> None:
        try:
            action()
        except CommandError as error:
            self._show_error(error)
            return
        self.refresh_links()

    def _clear_links_container(self) -> None:
        container = self.links_card.container
        while container.count():
            item = container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_error(self, error: CommandError) -> None:
        QMessageBox.critical(self, "Fel", str(error))


ACCENT_COLORS = {
    "blue": ("#4a90e2", "#3a78c9", "#2f63a8"),
    "green": ("#3fb765", "#2f9e52", "#268044"),
    "red": ("#e05a4e", "#c9483d", "#a83b32"),
}


def _accent_stylesheet(name: str, top: str, mid: str, bottom: str) -> str:
    return f"""
        QPushButton[accent="{name}"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {top}, stop:1 {mid});
            border: 1px solid {bottom};
            border-style: outset;
            color: white;
            font-weight: 600;
        }}
        QPushButton[accent="{name}"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {top}, stop:1 {bottom});
        }}
        QPushButton[accent="{name}"]:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {bottom}, stop:1 {mid});
            border-style: inset;
        }}
    """


def build_stylesheet(palette: QPalette) -> str:
    base = palette.color(QPalette.Button)
    top = base.lighter(115).name()
    mid = base.name()
    bottom = base.darker(115).name()

    stylesheet = f"""
        QPushButton {{
            padding: 10px 18px;
            font-size: 13pt;
            border-radius: 9px;
            border: 1px solid {bottom};
            border-style: outset;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {top}, stop:1 {mid});
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {top}, stop:1 {bottom});
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {bottom}, stop:1 {mid});
            border-style: inset;
        }}
        QLineEdit {{
            padding: 8px 12px;
            font-size: 13pt;
            border-radius: 7px;
        }}
        QLabel {{
            font-size: 13pt;
        }}
        QScrollArea {{
            border: none;
        }}
    """

    for name, (accent_top, accent_mid, accent_bottom) in ACCENT_COLORS.items():
        stylesheet += _accent_stylesheet(name, accent_top, accent_mid, accent_bottom)

    return stylesheet


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet(app.palette()))

    default_font = app.font()
    default_font.setPointSize(default_font.pointSize() + 2)
    app.setFont(default_font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
