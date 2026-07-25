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

import shutil
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

        transfer_row = QHBoxLayout()
        self._export_btn = QPushButton("Export Cache…")
        self._export_btn.setToolTip(
            "Save the current cache file to copy onto another machine's\n"
            "install, instead of regenerating it there from that machine's\n"
            "own X-Plane install."
        )
        self._export_btn.clicked.connect(self._export)
        transfer_row.addWidget(self._export_btn)
        self._import_btn = QPushButton("Import Cache…")
        self._import_btn.setToolTip(
            "Load a cache file exported from another machine, replacing\n"
            "whatever cache already exists here."
        )
        self._import_btn.clicked.connect(self._import)
        transfer_row.addWidget(self._import_btn)
        layout.addLayout(transfer_row)

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

    def _export(self):
        if not navdata.CACHE_PATH.is_file():
            QMessageBox.warning(self, "Navigation Data", "No cache built yet — nothing to export.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export Navigation Data Cache", "navdata_cache.json", "JSON files (*.json)",
        )
        if not dest:
            return
        try:
            shutil.copy2(navdata.CACHE_PATH, dest)
        except OSError as exc:
            QMessageBox.critical(self, "Navigation Data", f"Failed to export cache:\n{exc}")
            return
        QMessageBox.information(self, "Navigation Data", f"Exported to {dest}")

    def _import(self):
        src, _ = QFileDialog.getOpenFileName(
            self, "Import Navigation Data Cache", str(Path.home()), "JSON files (*.json)",
        )
        if not src:
            return
        data = navdata.load_cache(Path(src))
        if data is None or not any(k in data for k in ("airports", "navaids", "waypoints")):
            QMessageBox.critical(
                self, "Navigation Data",
                "That file doesn't look like a navigation data cache — expected the "
                "JSON exported via this same dialog's Export button.",
            )
            return
        if navdata.CACHE_PATH.is_file() and QMessageBox.question(
            self, "Navigation Data",
            "This will replace the existing cache on this machine. Continue?",
        ) != QMessageBox.Yes:
            return
        try:
            navdata.save_cache(data)
        except OSError as exc:
            QMessageBox.critical(self, "Navigation Data", f"Failed to import cache:\n{exc}")
            return
        navdata.reset_index()
        self._refresh_status()
        QMessageBox.information(self, "Navigation Data", "Cache imported.")
