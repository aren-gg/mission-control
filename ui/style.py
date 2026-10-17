"""A quiet, readable native desktop surface for Mission Control."""
from PySide6.QtGui import QFontDatabase, QPalette, QColor
STYLE = '''
QWidget { background: #F5F6F8; color: #202B35; font-size: 14px; }
QMainWindow, QDialog { background: #F5F6F8; }
QLabel#eyebrow { color: #58717D; font-size: 13px; }
QLabel#title { font-size: 26px; font-weight: 600; color: #17252D; }
QLabel#subtitle, QLabel#muted, QLabel#footer { color: #667580; }
QLabel#section { color: #276C70; font-weight: 600; }
QLabel#badge { color: #45646A; background: #EAF1F1; border: 1px solid #D5E2E3; border-radius: 6px; padding: 9px 13px; }
QTabWidget::pane { border: 0px; background: #F5F6F8; }
QTabBar::tab { color: #667580; background: #F5F6F8; border: 0px; border-bottom: 2px solid #E1E6E9; padding: 13px 18px; }
QTabBar::tab:selected { color: #176B70; border-bottom-color: #176B70; font-weight: 600; }
QTabBar::tab:hover { background: #EDF1F3; }
QPushButton { color: #FFFFFF; background: #236F73; border: 1px solid #236F73; border-radius: 5px; padding: 9px 15px; }
QPushButton:hover { background: #195B5F; border-color: #195B5F; }
QPushButton:focus { border: 2px solid #629EA1; }
QPushButton:disabled { color: #8A969C; background: #E7ECEE; border-color: #DCE3E6; }
QPushButton#secondary { color: #344E59; background: #FFFFFF; border: 1px solid #D5DFE3; }
QPushButton#secondary:disabled { color: #8A969C; background: #EEF1F3; border-color: #DCE3E6; }
QPushButton#secondary:hover { background: #EDF4F4; border-color: #A7C3C5; }
QFrame#agentheader, QFrame#projectbar, QFrame#agentcard, QFrame#summary { background: #FFFFFF; border: 1px solid #DFE5E8; border-radius: 7px; }
QFrame#agentheader QLabel, QFrame#projectbar QLabel, QFrame#agentcard QLabel, QFrame#summary QLabel { background: transparent; border: 0px; }
QPlainTextEdit, QTextBrowser, QLineEdit, QComboBox, QListWidget { color: #243640; background: #FFFFFF; border: 1px solid #D8E1E5; border-radius: 4px; padding: 9px; selection-background-color: #D8EEEE; selection-color: #163D41; }
QTextBrowser { padding: 16px; }
QComboBox { min-height: 22px; }
QComboBox QAbstractItemView { background: #FFFFFF; color: #243640; selection-background-color: #D8EEEE; }
QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus { border: 1px solid #3D8C90; }
QLineEdit:read-only { color: #667580; background: #F5F7F8; }
QListWidget::item { padding: 11px; border-radius: 4px; }
QListWidget::item:selected { background: #E1EFEF; color: #195B5F; }
QScrollArea { border: 0px; }
QScrollBar:vertical { background: #EEF1F3; width: 10px; margin: 0px; }
QScrollBar::handle:vertical { background: #C0CCD1; min-height: 30px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #EEF1F3; }
QScrollBar:horizontal { background: #EEF1F3; height: 10px; }
QScrollBar::handle:horizontal { background: #C0CCD1; min-width: 30px; }
QToolTip { color: #243640; background: #FFFFFF; border: 1px solid #D5DFE3; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #AAC1C5; border-radius: 3px; background: #FFFFFF; }
QCheckBox::indicator:checked { background: #236F73; }
QDialogButtonBox QPushButton { min-width: 80px; }
'''
def apply_style(app):
    font=QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont);font.setPixelSize(14);app.setFont(font);app.setStyle('Fusion')
    palette=QPalette();palette.setColor(QPalette.ColorRole.Window,QColor('#F5F6F8'));palette.setColor(QPalette.ColorRole.Base,QColor('#FFFFFF'));palette.setColor(QPalette.ColorRole.Text,QColor('#243640'));palette.setColor(QPalette.ColorRole.WindowText,QColor('#243640'));palette.setColor(QPalette.ColorRole.ButtonText,QColor('#243640'));palette.setColor(QPalette.ColorRole.PlaceholderText,QColor('#7B8A93'));palette.setColor(QPalette.ColorRole.Highlight,QColor('#D8EEEE'));palette.setColor(QPalette.ColorRole.HighlightedText,QColor('#163D41'));app.setPalette(palette);app.setStyleSheet(STYLE)
