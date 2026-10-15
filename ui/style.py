"""Readable native desktop controls; pixel art remains confined to the Office."""
from PySide6.QtGui import QFontDatabase, QPalette, QColor
from sprites import PALETTE

STYLE = '''
QWidget { background: #0B132B; color: #DDEBF0; font-size: 14px; }
QMainWindow { background: #0B132B; }
QLabel#eyebrow, QLabel#section, QLabel#footer { color: #5BC0BE; }
QLabel#title { font-size: 24px; font-weight: 600; color: #F4F1DE; }
QLabel#subtitle, QLabel#muted { color: #A0AEC0; }
QLabel#badge { color: #F2CC8F; background: #1C2541; border: 1px solid #3A506B; padding: 10px; }
QTabWidget::pane { border: 1px solid #3A506B; background: #0B132B; }
QTabBar::tab { background: #0B132B; color: #A0AEC0; border: 0px; border-bottom: 3px solid #0B132B; padding: 12px 16px; margin-right: 2px; }
QTabBar::tab:selected { background: #1C2541; color: #6FFFE9; border-bottom-color: #6FFFE9; }
QTabBar::tab:hover { color: #F4F1DE; }
QPushButton { color: #0B132B; background: #5BC0BE; border: 1px solid #5BC0BE; padding: 10px 14px; }
QPushButton:hover { background: #6FFFE9; border-color: #6FFFE9; }
QPushButton:focus { border: 2px solid #F2CC8F; }
QPushButton:disabled { color: #A0AEC0; background: #1C2541; border-color: #3A506B; }
QPushButton#secondary { color: #DDEBF0; background: #1C2541; border: 1px solid #3A506B; }
QPushButton#agentcard { text-align: left; color: #DDEBF0; background: #1C2541; border: 1px solid #3A506B; padding: 10px; }
QPushButton#agentcard:hover { border-color: #6FFFE9; }
QFrame#agentheader, QFrame#projectbar { background: #1C2541; border: 1px solid #3A506B; }
QFrame#agentheader QLabel, QFrame#projectbar QLabel { background: #1C2541; border: 0px; }
QPlainTextEdit, QTextBrowser, QLineEdit, QComboBox, QListWidget { color: #DDEBF0; background: #1C2541; border: 1px solid #3A506B; padding: 9px; selection-background-color: #3A506B; selection-color: #FFFFFF; }
QComboBox { min-height: 22px; }
QComboBox QAbstractItemView { background: #1C2541; color: #DDEBF0; selection-background-color: #3A506B; }
QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus { border: 1px solid #6FFFE9; }
QLineEdit:read-only { color: #A0AEC0; }
QListWidget::item { padding: 10px; }
QListWidget::item:selected { background: #3A506B; color: #FFFFFF; }
QScrollBar:vertical { background: #1C2541; width: 12px; margin: 0px; }
QScrollBar::handle:vertical { background: #3A506B; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #1C2541; }
QScrollBar:horizontal { background: #1C2541; height: 12px; }
QScrollBar::handle:horizontal { background: #3A506B; min-width: 25px; }
QToolTip { color: #F4F1DE; background: #1C2541; border: 1px solid #5BC0BE; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #5BC0BE; background: #1C2541; }
QCheckBox::indicator:checked { background: #5BC0BE; }
QDialogButtonBox QPushButton { min-width: 80px; }
'''

def apply_style(app):
    font=QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont);font.setPixelSize(14);app.setFont(font);app.setStyle('Fusion')
    palette=QPalette()
    for role in QPalette.ColorRole:
        if role not in (QPalette.ColorRole.NoRole,QPalette.ColorRole.NColorRoles):palette.setColor(role,QColor(PALETTE[1]))
    for role in (QPalette.ColorRole.Text,QPalette.ColorRole.WindowText,QPalette.ColorRole.ButtonText):palette.setColor(role,QColor(PALETTE[14]))
    palette.setColor(QPalette.ColorRole.PlaceholderText,QColor(PALETTE[13]));palette.setColor(QPalette.ColorRole.Highlight,QColor(PALETTE[2]));palette.setColor(QPalette.ColorRole.HighlightedText,QColor(PALETTE[15]));app.setPalette(palette);app.setStyleSheet(STYLE)
