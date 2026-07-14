"""Dialog for pointing at an X-Plane install and (re)building the local
moving-map nav data cache (airports/VORs/NDBs/waypoints) used by
VectorCompassRose's `moving_map`.

The X-Plane install path is a machine-local preference (QSettings, not
config.yaml) — this project's config.yaml is git-tracked and synced across
the user's own multiple PCs, and an install path is specific to whichever
machine the designer happens to be running on.

The cache itself never touches the repo: `gauge_core.navdata.CACHE_PATH`
lives under the user's home directory, well outside any git working tree
(see that module's docstring for why — earth_nav.dat's Navigraph/Jeppesen
copyright notice, on a public repo).
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox,
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
)
from PySide6.QtCore import QSettings, Qt

from gauge_core import navdata

_SETTINGS_KEY = "navdata/xplaneInstallPath"


class NavDataDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Navigation Data")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "The moving map (VectorCompassRose's <code>moving_map</code>) needs a "
            "local cache of airport/VOR/NDB positions, built from your own X-Plane "
            "install. This is generated on this machine only — never bundled with "
            "the app or committed to the project."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("X-Plane install folder:"))
        self._path_edit = QLineEdit(QSettings().value(_SETTINGS_KEY, ""))
        path_row.addWidget(self._path_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status_lbl)
        self._refresh_status()

        self._regen_btn = QPushButton("Regenerate Cache")
        self._regen_btn.clicked.connect(self._regenerate)
        layout.addWidget(self._regen_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

    def _browse(self):
        start = self._path_edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select X-Plane Install Folder", start)
        if chosen:
            self._path_edit.setText(chosen)
            QSettings().setValue(_SETTINGS_KEY, chosen)

    def _refresh_status(self):
        cache = navdata.load_cache()
        if cache is None:
            self._status_lbl.setText("No cache built yet.")
            return
        self._status_lbl.setText(
            f"Cache built {cache.get('generated', '?')} from "
            f"{cache.get('xplane_root', '?')} — "
            f"{len(cache.get('airports', []))} airports, "
            f"{len(cache.get('navaids', []))} navaids, "
            f"{len(cache.get('waypoints', []))} waypoints. "
            f"Saved to {navdata.CACHE_PATH}"
        )

    def _regenerate(self):
        root = self._path_edit.text().strip()
        if not root or not Path(root).is_dir():
            QMessageBox.warning(self, "Navigation Data", "Choose a valid X-Plane install folder first.")
            return
        QSettings().setValue(_SETTINGS_KEY, root)
        self._regen_btn.setEnabled(False)
        self._status_lbl.setText("Building cache — this can take a few seconds for apt.dat…")
        self.setCursor(Qt.WaitCursor)
        try:
            data = navdata.build_cache(root)
            if not data["airports"] and not data["navaids"] and not data["waypoints"]:
                QMessageBox.warning(
                    self, "Navigation Data",
                    "No apt.dat, earth_nav.dat, or earth_fix.dat found under that "
                    "folder — check it's the X-Plane install root."
                )
                return
            navdata.save_cache(data)
        except Exception as exc:
            QMessageBox.critical(self, "Navigation Data", f"Failed to build cache:\n{exc}")
            return
        finally:
            self.unsetCursor()
            self._regen_btn.setEnabled(True)
        self._refresh_status()
