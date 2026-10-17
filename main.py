"""Launch Mission Control: python main.py."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from workspace import WorkspaceStore
from ui.style import apply_style
from ui.window import MainWindow

def main(argv=None):
    parser=argparse.ArgumentParser(description='Mission Control desktop workspace')
    parser.add_argument('--screenshot',metavar='PNG',help='Save Dashboard, conversations, team editor, and Setup Guide, then exit')
    args=parser.parse_args(argv)
    app=QApplication.instance() or QApplication(sys.argv[:1]);app.setApplicationName('Mission Control');app.setOrganizationName('Mission Control');apply_style(app)
    workspace=WorkspaceStore(Path(__file__).resolve().parent);window=MainWindow(workspace=workspace)
    if args.screenshot:window.resize(1200,920)
    window.show()
    if args.screenshot:
        def capture():
            exit_code=0
            try:
                for path in window.save_screenshots(args.screenshot):print(f'Saved {path}')
            except Exception as error:
                print(f'Screenshot failed: {error}',file=sys.stderr);exit_code=1
            finally:window.close();app.exit(exit_code)
        QTimer.singleShot(1200,capture)
    return app.exec()

if __name__=='__main__':raise SystemExit(main())
