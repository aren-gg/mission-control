"""Flat palette styling and a bundled code-derived pixel font."""
from pathlib import Path
from PySide6.QtGui import QFont, QFontDatabase, QPalette, QColor
from sprites import PALETTE

STYLE = '''
QWidget { background: #0B132B; color: #DDEBF0; font-family: "Subsea Pixel"; font-size: 10px; }
QMainWindow { background: #0B132B; }
QLabel#eyebrow, QLabel#section, QLabel#footer { color: #5BC0BE; }
QLabel#title { font-size: 20px; color: #F4F1DE; }
QLabel#subtitle, QLabel#muted { color: #A0AEC0; }
QLabel#badge { color: #F2CC8F; background: #1C2541; border: 1px solid #3A506B; padding: 8px; }
QTabWidget::pane { border: 1px solid #3A506B; background: #0B132B; }
QTabBar::tab { background: #0B132B; color: #A0AEC0; border: 0px; border-bottom: 3px solid #0B132B; padding: 13px 16px; margin-right: 2px; }
QTabBar::tab:selected { background: #1C2541; color: #6FFFE9; border-bottom-color: #6FFFE9; }
QTabBar::tab:hover { color: #F4F1DE; }
QPushButton { color: #0B132B; background: #5BC0BE; border: 1px solid #5BC0BE; padding: 11px 16px; }
QPushButton:hover { background: #6FFFE9; border-color: #6FFFE9; }
QPushButton:focus { border: 2px solid #F2CC8F; }
QPushButton:disabled { color: #A0AEC0; background: #1C2541; border-color: #3A506B; }
QPushButton#agentcard { text-align: left; color: #DDEBF0; background: #1C2541; border: 1px solid #3A506B; padding: 12px; }
QPushButton#agentcard:hover { border-color: #6FFFE9; }
QFrame#agentheader { background: #1C2541; border: 1px solid #3A506B; }
QFrame#agentheader QLabel { background: #1C2541; border: 0px; }
QPlainTextEdit, QTextBrowser { color: #DDEBF0; background: #1C2541; border: 1px solid #3A506B; padding: 12px; selection-background-color: #3A506B; selection-color: #FFFFFF; }
QPlainTextEdit:focus { border: 1px solid #6FFFE9; }
QScrollBar:vertical { background: #1C2541; width: 10px; margin: 0px; }
QScrollBar::handle:vertical { background: #3A506B; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #1C2541; }
QScrollBar:horizontal { background: #1C2541; height: 10px; }
QScrollBar::handle:horizontal { background: #3A506B; min-width: 25px; }
QToolTip { color: #F4F1DE; background: #1C2541; border: 1px solid #5BC0BE; }
'''

def apply_style(app):
    font_path = Path(__file__).resolve().parents[1] / 'assets' / 'pixel-font.ttf'
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    families = QFontDatabase.applicationFontFamilies(font_id)
    font = QFont(families[0] if families else 'Monospace')
    font.setPixelSize(10)
    font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)
    app.setStyle('Fusion')
    palette = QPalette()
    for role in QPalette.ColorRole:
        if role not in (QPalette.ColorRole.NoRole,QPalette.ColorRole.NColorRoles): palette.setColor(role, QColor(PALETTE[1]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText): palette.setColor(role,QColor(PALETTE[14]))
    palette.setColor(QPalette.ColorRole.Highlight,QColor(PALETTE[2]));palette.setColor(QPalette.ColorRole.HighlightedText,QColor(PALETTE[15]))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
