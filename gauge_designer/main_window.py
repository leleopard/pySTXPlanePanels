import yaml
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QTabWidget, QPushButton,
)
from PySide6.QtCore import QSettings, Qt, QSize
from PySide6.QtGui import QAction

from gauge_core.panel import iter_leaf_instrument_entries
from gauge_designer.instrument_view import InstrumentView
from gauge_designer.panel_view import PanelView
from gauge_designer.preview import PreviewBar
from gauge_designer.ui_utils import make_svg_icon

_MAX_RECENT = 8
_TAB_GAUGE = 0
_TAB_PANEL = 1


def _find_instruments_root(yaml_path: str) -> str:
    """Walk up from the YAML's directory to find an ancestor named 'instruments'."""
    p = Path(yaml_path).parent.resolve()
    candidate = p
    while candidate != candidate.parent:
        if candidate.name.lower() == "instruments":
            return str(candidate)
        candidate = candidate.parent
    return str(p)


def _find_panels_root(yaml_path: str) -> str:
    """Walk up from the YAML's directory to find an ancestor named 'panels'."""
    p = Path(yaml_path).parent.resolve()
    candidate = p
    while candidate != candidate.parent:
        if candidate.name.lower() == "panels":
            return str(candidate)
        candidate = candidate.parent
    return str(p)


def _has_instrument_ref(data: dict, ref_rel: str) -> bool:
    """Return True if any instrument entry in data references ref_rel."""
    return any(
        inst.get("file", "").replace("\\", "/") == ref_rel
        for inst in iter_leaf_instrument_entries(data.get("instruments", []))
    )


def _filter_instrument_refs(entries: list[dict], ref_rel: str) -> list[dict]:
    """Recursively drop any leaf entry referencing ref_rel. Grid/container
    wrappers are kept (even if emptied out) with their own instruments list
    filtered the same way, at any nesting depth."""
    result = []
    for entry in entries:
        if "grid" in entry:
            entry["grid"]["instruments"] = _filter_instrument_refs(
                entry["grid"].get("instruments", []), ref_rel)
            result.append(entry)
        elif "container" in entry:
            entry["container"]["instruments"] = _filter_instrument_refs(
                entry["container"].get("instruments", []), ref_rel)
            result.append(entry)
        elif entry.get("file", "").replace("\\", "/") != ref_rel:
            result.append(entry)
    return result


def _remove_instrument_refs(data: dict, ref_rel: str) -> None:
    """Remove all instrument entries referencing ref_rel from data (in-place)."""
    data["instruments"] = _filter_instrument_refs(data.get("instruments", []), ref_rel)


def _rewrite_refs(data: dict, old_rel: str, new_rel: str) -> bool:
    """Replace matching instrument file references in a panel data dict (in-place).

    Handles both exact file matches and prefix matches for directory moves.
    Returns True if any reference was changed.
    """
    changed = False
    for inst in iter_leaf_instrument_entries(data.get("instruments", [])):
        current = inst.get("file", "").replace("\\", "/")
        if current == old_rel:
            inst["file"] = new_rel
            changed = True
        elif current.startswith(old_rel + "/"):
            inst["file"] = new_rel + current[len(old_rel):]
            changed = True
    return changed


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pyXplane Panels Designer")
        self.setWindowIcon(make_svg_icon("turbine", size=64))
        self.resize(1060, 640)

        self._settings = QSettings()

        # Per-tab file state
        self._gauge_path: str | None = None
        self._gauge_data: dict = {}
        self._gauge_dirty = False

        self._panel_path: str | None = None
        self._panel_data: dict = {}
        self._panel_dirty = False

        # Widgets
        self._gauge_view = InstrumentView()
        self._gauge_view.changed.connect(self._mark_gauge_dirty)
        self._gauge_view.open_requested.connect(
            lambda p: (self._tabs.setCurrentIndex(_TAB_GAUGE), self._load_gauge(p))
        )

        self._panel_view = PanelView()
        self._panel_view.changed.connect(self._mark_panel_dirty)
        self._panel_view.open_requested.connect(
            lambda p: (self._tabs.setCurrentIndex(_TAB_PANEL), self._load_panel(p))
        )

        self._preview = PreviewBar(self)
        self._gauge_view.test_running.connect(self._on_test_running)
        self._preview.running_changed.connect(self._on_test_running)
        self._gauge_view.live_running.connect(self._on_live_running)
        self._preview.live_running_changed.connect(self._on_live_running)
        self._gauge_view.instrument_moved.connect(self._on_instrument_moved)
        self._gauge_view.delete_requested.connect(self._on_instrument_delete_requested)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._gauge_view, "Instruments")
        self._tabs.addTab(self._panel_view, "Panels")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.setStyleSheet(
            "QTabBar::tab { padding: 4px 16px; }"
            "QTabBar::tab:selected { color: black; font-weight: bold;"
            " border-bottom: 2px solid #6682c5; }"
        )
        self.setCentralWidget(self._tabs)

        self._build_menu()
        self._build_toolbar()
        self._wire_ctx_actions()
        self.statusBar().showMessage("Open a gauge or panel YAML to begin.")

        geometry = self._settings.value("windowGeometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.showMaximized()
        self._gauge_view.restore_state(self._settings)
        self._panel_view.restore_state(self._settings)

    # ── Menu ─────────────────────────────────────────────────────────────

    def _build_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")

        self._open_gauge_act = QAction("Open &Gauge…", self)
        self._open_gauge_act.setShortcut("Ctrl+O")
        self._open_gauge_act.triggered.connect(self._open_gauge_dialog)
        file_menu.addAction(self._open_gauge_act)

        self._open_panel_act = QAction("Open &Panel…", self)
        self._open_panel_act.setShortcut("Ctrl+Shift+O")
        self._open_panel_act.triggered.connect(self._open_panel_dialog)
        file_menu.addAction(self._open_panel_act)

        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._refresh_recent_menu()

        file_menu.addSeparator()

        self._save_act = QAction("&Save", self)
        self._save_act.setShortcut("Ctrl+S")
        self._save_act.setEnabled(False)
        self._save_act.triggered.connect(self._save)
        file_menu.addAction(self._save_act)

        save_as_act = QAction("Save &As…", self)
        save_as_act.setShortcut("Ctrl+Shift+S")
        save_as_act.triggered.connect(self._save_as)
        file_menu.addAction(save_as_act)

        file_menu.addSeparator()
        quit_act = QAction("&Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        edit_menu = menu.addMenu("&Edit")

        self._ctx_add_act = QAction("&Add", self)
        self._ctx_add_act.setEnabled(False)
        edit_menu.addAction(self._ctx_add_act)

        self._ctx_delete_act = QAction("&Delete", self)
        self._ctx_delete_act.setEnabled(False)
        edit_menu.addAction(self._ctx_delete_act)

        self._ctx_duplicate_act = QAction("D&uplicate", self)
        self._ctx_duplicate_act.setEnabled(False)
        edit_menu.addAction(self._ctx_duplicate_act)

        edit_menu.addSeparator()

        self._ctx_copy_act = QAction("&Copy", self)
        self._ctx_copy_act.setShortcut("Ctrl+C")
        self._ctx_copy_act.setEnabled(False)
        edit_menu.addAction(self._ctx_copy_act)

        self._ctx_paste_act = QAction("&Paste", self)
        self._ctx_paste_act.setShortcut("Ctrl+V")
        self._ctx_paste_act.setEnabled(False)
        edit_menu.addAction(self._ctx_paste_act)

        self._ctx_add_folder_act = QAction("New &Folder", self)
        self._ctx_add_folder_act.setEnabled(False)
        edit_menu.addAction(self._ctx_add_folder_act)

        settings_menu = menu.addMenu("&Settings")

        xplane_act = QAction("X-Plane &Network Settings…", self)
        xplane_act.triggered.connect(self._open_xplane_settings)
        settings_menu.addAction(xplane_act)

        aa_act = QAction("&Antialiasing…", self)
        aa_act.triggered.connect(self._open_antialiasing)
        settings_menu.addAction(aa_act)

        navdata_act = QAction("&Navigation Data…", self)
        navdata_act.triggered.connect(self._open_navdata)
        settings_menu.addAction(navdata_act)

        settings_menu.addSeparator()

        prefs_act = QAction("&Preferences…", self)
        prefs_act.setShortcut("Ctrl+,")
        prefs_act.triggered.connect(self._open_preferences)
        settings_menu.addAction(prefs_act)

    def _open_navdata(self):
        from gauge_designer.navdata_dialog import NavDataDialog
        NavDataDialog(self).exec()

    def _open_antialiasing(self):
        from gauge_designer.antialiasing_dialog import AntialiasingDialog
        AntialiasingDialog(self).exec()

    def _open_xplane_settings(self):
        from gauge_designer.xplane_settings_dialog import XPlaneSettingsDialog
        root = self._project_root()
        dlg = XPlaneSettingsDialog(root, parent=self)
        dlg.exec()

    def _project_root(self) -> str:
        if self._gauge_view._instruments_root:
            return str(Path(self._gauge_view._instruments_root).parent)
        if self._panel_view._panels_root:
            return str(Path(self._panel_view._panels_root).parent)
        return str(Path.cwd())

    def _open_preferences(self):
        from gauge_designer.preferences_dialog import PreferencesDialog
        dlg = PreferencesDialog(self)
        if dlg.exec():
            self._on_prefs_changed()

    def _on_prefs_changed(self):
        idx = self._tabs.currentIndex()
        if idx == _TAB_GAUGE:
            self._gauge_view.refresh_form()
        else:
            self._panel_view.refresh_form()

    # ── Toolbar ───────────────────────────────────────────────────────────

    _ICON_GREY = "#888888"

    def _build_toolbar(self):
        tb = self.addToolBar("Tools")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(36, 36))

        _btn_style = (
            "QPushButton {"
            "  padding: 0px; border: 1px solid transparent;"
            "  border-radius: 5px; background: transparent;"
            "}"
            "QPushButton:hover {"
            "  border: 1px solid #6682c5;"
            "  background: rgba(102, 130, 197, 0.18);"
            "}"
            "QPushButton:pressed {"
            "  background: rgba(102, 130, 197, 0.35);"
            "}"
        )

        self._save_btn = QPushButton()
        self._save_btn.setIcon(make_svg_icon("content-save-outline", self._ICON_GREY, size=36))
        self._save_btn.setIconSize(QSize(36, 36))
        self._save_btn.setFixedSize(48, 48)
        self._save_btn.setStyleSheet(_btn_style)
        self._save_btn.setToolTip("Save (Ctrl+S)")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save)
        tb.addWidget(self._save_btn)

        self._save_all_btn = QPushButton()
        self._save_all_btn.setIcon(make_svg_icon("content-save-all-outline", self._ICON_GREY, size=36))
        self._save_all_btn.setIconSize(QSize(36, 36))
        self._save_all_btn.setFixedSize(48, 48)
        self._save_all_btn.setStyleSheet(_btn_style)
        self._save_all_btn.setToolTip("Save All")
        self._save_all_btn.setEnabled(False)
        self._save_all_btn.clicked.connect(self._save_all)
        tb.addWidget(self._save_all_btn)

        tb.addSeparator()

        for icon, tip, act, attr in (
            ("plus-circle-outline",          "Add",       self._ctx_add_act,       "_ctx_add_btn"),
            ("trash-can-outline",            "Delete",    self._ctx_delete_act,    "_ctx_delete_btn"),
            ("plus-circle-multiple-outline", "Duplicate", self._ctx_duplicate_act, "_ctx_duplicate_btn"),
            ("content-copy",                 "Copy",      self._ctx_copy_act,      "_ctx_copy_btn"),
            ("content-paste",                "Paste",     self._ctx_paste_act,     "_ctx_paste_btn"),
            ("folder-plus-outline",          "New Folder", self._ctx_add_folder_act, "_ctx_add_folder_btn"),
        ):
            btn = QPushButton()
            btn.setIcon(make_svg_icon(icon, self._ICON_GREY, size=36))
            btn.setIconSize(QSize(36, 36))
            btn.setFixedSize(48, 48)
            btn.setStyleSheet(_btn_style)
            btn.setToolTip(tip)
            btn.setEnabled(False)
            btn.clicked.connect(act.trigger)
            setattr(self, attr, btn)
            tb.addWidget(btn)

        tb.addSeparator()

        self._add_container_btn = QPushButton()
        self._add_container_btn.setIcon(make_svg_icon("file-table-box-outline", self._ICON_GREY, size=36))
        self._add_container_btn.setIconSize(QSize(36, 36))
        self._add_container_btn.setFixedSize(48, 48)
        self._add_container_btn.setStyleSheet(_btn_style)
        self._add_container_btn.setToolTip("Add Container")
        self._add_container_btn.setEnabled(False)
        self._add_container_btn.clicked.connect(self._on_add_container_clicked)
        tb.addWidget(self._add_container_btn)

        tb.addSeparator()

        self._script_btn = QPushButton()
        self._script_btn.setIcon(make_svg_icon("script-text-play-outline", self._ICON_GREY, size=36))
        self._script_btn.setIconSize(QSize(36, 36))
        self._script_btn.setFixedSize(48, 48)
        self._script_btn.setStyleSheet(_btn_style)
        self._script_btn.setToolTip("Create launch script for this panel")
        self._script_btn.setEnabled(False)
        self._script_btn.clicked.connect(self._on_script_clicked)
        tb.addWidget(self._script_btn)

        tb.addSeparator()

        self._play_btn = QPushButton()
        self._play_btn.setIcon(make_svg_icon("bug-play", self._ICON_GREY, size=36))
        self._play_btn.setIconSize(QSize(36, 36))
        self._play_btn.setFixedSize(48, 48)
        self._play_btn.setStyleSheet(_btn_style)
        self._play_btn.setToolTip("Launch test / preview (mock, no X-Plane)")
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self._on_play_clicked)
        tb.addWidget(self._play_btn)

        self._run_btn = QPushButton()
        self._run_btn.setIcon(make_svg_icon("play-circle-outline", self._ICON_GREY, size=36))
        self._run_btn.setIconSize(QSize(36, 36))
        self._run_btn.setFixedSize(48, 48)
        self._run_btn.setStyleSheet(_btn_style)
        self._run_btn.setToolTip("Launch live — connect to X-Plane")
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._on_run_clicked)
        tb.addWidget(self._run_btn)

    def _update_save_btn(self, dirty: bool):
        from gauge_designer.ui_utils import _HEADER_COLOR
        has_file = (
            (self._tabs.currentIndex() == _TAB_GAUGE and self._gauge_path is not None)
            or (self._tabs.currentIndex() == _TAB_PANEL and self._panel_path is not None)
        )
        enabled = has_file and dirty
        self._save_btn.setEnabled(enabled)
        color = _HEADER_COLOR if enabled else self._ICON_GREY
        self._save_btn.setIcon(make_svg_icon("content-save-outline", color, size=36))
        self._save_act.setEnabled(enabled)

    def _update_play_btn(self):
        from gauge_designer.ui_utils import _HEADER_COLOR
        idx = self._tabs.currentIndex()
        has_file = (
            (idx == _TAB_GAUGE and self._gauge_path is not None)
            or (idx == _TAB_PANEL and self._panel_path is not None)
        )
        busy = (idx == _TAB_GAUGE and (self._gauge_view._test_proc is not None
                                       or self._gauge_view._live_proc is not None)) \
               or (idx == _TAB_PANEL and (self._preview.is_running or self._preview.is_live))
        enabled = has_file and not busy
        self._play_btn.setEnabled(enabled)
        color = _HEADER_COLOR if enabled else self._ICON_GREY
        self._play_btn.setIcon(make_svg_icon("bug-play", color, size=36))

    def _update_run_btn(self):
        from gauge_designer.ui_utils import _HEADER_COLOR
        idx = self._tabs.currentIndex()
        has_file = (
            (idx == _TAB_GAUGE and self._gauge_path is not None)
            or (idx == _TAB_PANEL and self._panel_path is not None)
        )
        busy = (idx == _TAB_GAUGE and (self._gauge_view._test_proc is not None
                                       or self._gauge_view._live_proc is not None)) \
               or (idx == _TAB_PANEL and (self._preview.is_running or self._preview.is_live))
        enabled = has_file and not busy
        self._run_btn.setEnabled(enabled)
        color = _HEADER_COLOR if enabled else self._ICON_GREY
        self._run_btn.setIcon(make_svg_icon("play-circle-outline", color, size=36))

    def _update_save_all_btn(self):
        from gauge_designer.ui_utils import _HEADER_COLOR
        any_dirty = (
            (self._gauge_dirty and self._gauge_path is not None)
            or (self._panel_dirty and self._panel_path is not None)
        )
        self._save_all_btn.setEnabled(any_dirty)
        color = _HEADER_COLOR if any_dirty else self._ICON_GREY
        self._save_all_btn.setIcon(make_svg_icon("content-save-all-outline", color, size=36))

    def _update_add_container_btn(self):
        from gauge_designer.ui_utils import _HEADER_COLOR
        enabled = (
            self._tabs.currentIndex() == _TAB_PANEL
            and self._panel_path is not None
        )
        self._add_container_btn.setEnabled(enabled)
        color = _HEADER_COLOR if enabled else self._ICON_GREY
        self._add_container_btn.setIcon(make_svg_icon("file-table-box-outline", color, size=36))

    def _on_add_container_clicked(self):
        if self._tabs.currentIndex() == _TAB_PANEL:
            self._panel_view._add_container()

    def _update_script_btn(self):
        from gauge_designer.ui_utils import _HEADER_COLOR
        enabled = (
            self._tabs.currentIndex() == _TAB_PANEL
            and self._panel_path is not None
        )
        self._script_btn.setEnabled(enabled)
        color = _HEADER_COLOR if enabled else self._ICON_GREY
        self._script_btn.setIcon(make_svg_icon("script-text-play-outline", color, size=36))

    def _on_script_clicked(self):
        if not self._panel_path:
            return
        from gauge_designer.launch_script_dialog import LaunchScriptDialog
        dlg = LaunchScriptDialog(
            self._panel_path, self._project_root(), self._panel_view._panels_root, parent=self,
        )
        dlg.exec()

    def _save_all(self):
        if self._gauge_dirty and self._gauge_path:
            self._write_gauge(self._gauge_path)
        if self._panel_dirty and self._panel_path:
            self._write_panel(self._panel_path)

    def _on_play_clicked(self):
        if self._tabs.currentIndex() == _TAB_GAUGE:
            self._gauge_view.toggle_test()
        else:
            self._preview.launch()

    def _on_run_clicked(self):
        if self._tabs.currentIndex() == _TAB_GAUGE:
            self._gauge_view.run_live()
        else:
            self._preview.launch_live()

    def _on_test_running(self, running: bool):
        self._update_play_btn()
        self._update_run_btn()

    def _on_live_running(self, running: bool):
        self._update_play_btn()
        self._update_run_btn()

    def _on_instrument_moved(self, old_abs: str, new_abs: str):
        """Rewrite instrument file references in all panel YAMLs when a file/folder moves."""
        instruments_root = self._gauge_view._instruments_root
        panels_root = self._panel_view._panels_root
        if not instruments_root or not panels_root:
            return
        project_root = Path(instruments_root).parent.resolve()
        try:
            old_rel = Path(old_abs).resolve().relative_to(project_root).as_posix()
            new_rel = Path(new_abs).resolve().relative_to(project_root).as_posix()
        except ValueError:
            return

        updated: list[str] = []
        for yaml_path in Path(panels_root).rglob("*.yaml"):
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception:
                continue
            if not isinstance(data, dict) or "instruments" not in data:
                continue
            if not _rewrite_refs(data, old_rel, new_rel):
                continue
            try:
                with open(yaml_path, "w", encoding="utf-8") as f:
                    yaml.dump(data, f, default_flow_style=False,
                              allow_unicode=True, sort_keys=False)
                updated.append(yaml_path.name)
            except Exception:
                continue
            # Keep in-memory panel data in sync if this is the open panel
            if self._panel_path and Path(self._panel_path).resolve() == yaml_path.resolve():
                self._panel_data = data
                self._panel_dirty = False
                self._panel_view.load(self._panel_data, self._panel_path)
                self._update_save_btn(False)
                self._update_save_all_btn()

        if updated:
            self.statusBar().showMessage(
                f"Auto-updated paths in: {', '.join(updated)}"
            )

    def _on_instrument_delete_requested(self, abs_path: str) -> None:
        """Confirm deletion of an instrument file, warn if panels reference it, then clean up."""
        path = Path(abs_path)
        instruments_root = self._gauge_view._instruments_root
        panels_root = self._panel_view._panels_root

        # Scan panel YAMLs for references to this file.
        ref_rel: str | None = None
        affected: list[tuple[Path, dict]] = []
        if instruments_root and panels_root:
            project_root = Path(instruments_root).parent.resolve()
            try:
                ref_rel = path.resolve().relative_to(project_root).as_posix()
            except ValueError:
                pass
            if ref_rel:
                for yaml_path in Path(panels_root).rglob("*.yaml"):
                    try:
                        with open(yaml_path, encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                    except Exception:
                        continue
                    if isinstance(data, dict) and _has_instrument_ref(data, ref_rel):
                        affected.append((yaml_path, data))

        # Build confirmation dialog.
        if affected:
            panel_names = "\n".join(f"  • {p.name}" for p, _ in affected)
            msg = (
                f"The following panels reference '{path.name}':\n\n"
                f"{panel_names}\n\n"
                f"Delete '{path.name}' and remove it from all listed panels?"
            )
            reply = QMessageBox.warning(
                self, "Delete Instrument — Panels Affected",
                msg, QMessageBox.Yes | QMessageBox.No,
            )
        else:
            reply = QMessageBox.question(
                self, "Delete Instrument",
                f"Delete '{path.name}'?\nThis cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
            )
        if reply != QMessageBox.Yes:
            return

        # Delete the file.
        try:
            path.unlink()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        # Remove from affected panel YAMLs.
        if affected and ref_rel:
            cleaned: list[str] = []
            for yaml_path, data in affected:
                _remove_instrument_refs(data, ref_rel)
                try:
                    with open(yaml_path, "w", encoding="utf-8") as f:
                        yaml.dump(data, f, default_flow_style=False,
                                  allow_unicode=True, sort_keys=False)
                    cleaned.append(yaml_path.name)
                except Exception:
                    continue
                if self._panel_path and Path(self._panel_path).resolve() == yaml_path.resolve():
                    self._panel_data = data
                    self._panel_dirty = False
                    self._panel_view.load(self._panel_data, self._panel_path)
                    self._update_save_btn(False)
                    self._update_save_all_btn()
            if cleaned:
                self.statusBar().showMessage(
                    f"Deleted {path.name}; removed from: {', '.join(cleaned)}"
                )

        # Refresh the instrument tree (and clear form if the deleted file was open).
        self._gauge_view.after_file_deleted(abs_path)

    # ── Context toolbar actions ────────────────────────────────────────────

    def _wire_ctx_actions(self) -> None:
        self._gauge_view.context_changed.connect(self._refresh_ctx_actions)
        self._panel_view.context_changed.connect(self._refresh_ctx_actions)
        self._ctx_add_act.triggered.connect(self._on_ctx_add)
        self._ctx_delete_act.triggered.connect(self._on_ctx_delete)
        self._ctx_duplicate_act.triggered.connect(self._on_ctx_duplicate)
        self._ctx_copy_act.triggered.connect(self._on_ctx_copy)
        self._ctx_paste_act.triggered.connect(self._on_ctx_paste)
        self._ctx_add_folder_act.triggered.connect(self._on_ctx_add_folder)

    def _refresh_ctx_actions(self) -> None:
        from gauge_designer.ui_utils import _HEADER_COLOR
        idx = self._tabs.currentIndex()
        view = self._gauge_view if idx == _TAB_GAUGE else self._panel_view if idx == _TAB_PANEL else None
        can_add   = view.can_add()       if view else False
        can_del   = view.can_delete()    if view else False
        can_dup   = view.can_duplicate() if view else False
        can_copy  = view.can_copy()      if view else False
        can_paste = view.can_paste()     if view else False
        # Instruments-tree-only; PanelView has no folder concept.
        can_add_folder = idx == _TAB_GAUGE and self._gauge_view.can_add_folder()
        for btn, icon, enabled in (
            (self._ctx_add_btn,       "plus-circle-outline",          can_add),
            (self._ctx_delete_btn,    "trash-can-outline",            can_del),
            (self._ctx_duplicate_btn, "plus-circle-multiple-outline", can_dup),
            (self._ctx_copy_btn,      "content-copy",                 can_copy),
            (self._ctx_paste_btn,     "content-paste",                can_paste),
            (self._ctx_add_folder_btn, "folder-plus-outline",         can_add_folder),
        ):
            btn.setEnabled(enabled)
            btn.setIcon(make_svg_icon(icon, _HEADER_COLOR if enabled else self._ICON_GREY, size=36))
        self._ctx_add_act.setEnabled(can_add)
        self._ctx_delete_act.setEnabled(can_del)
        self._ctx_duplicate_act.setEnabled(can_dup)
        self._ctx_copy_act.setEnabled(can_copy)
        self._ctx_add_folder_act.setEnabled(can_add_folder)
        self._ctx_paste_act.setEnabled(can_paste)

    def _on_ctx_add(self) -> None:
        idx = self._tabs.currentIndex()
        if idx == _TAB_GAUGE:
            self._gauge_view.do_add()
        elif idx == _TAB_PANEL:
            self._panel_view.do_add()

    def _on_ctx_delete(self) -> None:
        idx = self._tabs.currentIndex()
        if idx == _TAB_GAUGE:
            self._gauge_view.do_delete()
        elif idx == _TAB_PANEL:
            self._panel_view.do_delete()

    def _on_ctx_duplicate(self) -> None:
        idx = self._tabs.currentIndex()
        if idx == _TAB_GAUGE:
            self._gauge_view.do_duplicate()
        elif idx == _TAB_PANEL:
            self._panel_view.do_duplicate()

    def _on_ctx_copy(self) -> None:
        idx = self._tabs.currentIndex()
        if idx == _TAB_GAUGE:
            self._gauge_view.do_copy()

    def _on_ctx_paste(self) -> None:
        idx = self._tabs.currentIndex()
        if idx == _TAB_GAUGE:
            self._gauge_view.do_paste()

    def _on_ctx_add_folder(self) -> None:
        if self._tabs.currentIndex() == _TAB_GAUGE:
            self._gauge_view.do_add_folder()

    # ── Tab handling ──────────────────────────────────────────────────────

    def _on_tab_changed(self, idx: int):
        if idx == _TAB_GAUGE and self._gauge_path:
            self._preview.set_yaml(self._gauge_path, data_provider=lambda: self._gauge_data)
        elif idx == _TAB_PANEL and self._panel_path:
            self._preview.set_yaml(self._panel_path, data_provider=lambda: self._panel_data)
        dirty = self._gauge_dirty if idx == _TAB_GAUGE else self._panel_dirty
        self._update_save_btn(dirty)
        self._update_save_all_btn()
        self._update_script_btn()
        self._update_add_container_btn()
        self._update_play_btn()
        self._update_run_btn()
        self._refresh_ctx_actions()
        self._update_title()

    # ── Recent files ──────────────────────────────────────────────────────

    def _refresh_recent_menu(self):
        self._recent_menu.clear()
        recent = self._settings.value("recentFiles", []) or []
        if isinstance(recent, str):
            recent = [recent]
        if not recent:
            self._recent_menu.setEnabled(False)
            return
        self._recent_menu.setEnabled(True)
        for path in recent:
            act = QAction(path, self)
            act.triggered.connect(lambda checked=False, p=path: self._load_recent(p))
            self._recent_menu.addAction(act)

    def _push_recent(self, path: str):
        recent = self._settings.value("recentFiles", []) or []
        if isinstance(recent, str):
            recent = [recent]
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:_MAX_RECENT]
        self._settings.setValue("recentFiles", recent)
        self._refresh_recent_menu()

    # ── Open ──────────────────────────────────────────────────────────────

    def _open_gauge_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Gauge YAML", "", "YAML files (*.yaml *.yml)"
        )
        if path:
            self._tabs.setCurrentIndex(_TAB_GAUGE)
            self._load_gauge(path)

    def _open_panel_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Panel YAML", "", "YAML files (*.yaml *.yml)"
        )
        if path:
            self._tabs.setCurrentIndex(_TAB_PANEL)
            self._load_panel(path)

    def _load_recent(self, path: str):
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return
        if "components" in data:
            self._tabs.setCurrentIndex(_TAB_GAUGE)
            self._load_gauge(path, data)
        elif "instruments" in data:
            self._tabs.setCurrentIndex(_TAB_PANEL)
            self._load_panel(path, data)
        else:
            QMessageBox.warning(
                self, "Unknown File",
                "Cannot determine file type\n(missing 'components' or 'instruments' key)."
            )

    # ── Load ──────────────────────────────────────────────────────────────

    def _load_gauge(self, path: str, data: dict | None = None):
        if self._gauge_dirty and not self._confirm_discard("gauge"):
            return
        if data is None:
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception as exc:
                QMessageBox.critical(self, "Load Error", str(exc))
                return
        if not isinstance(data, dict) or "components" not in data:
            QMessageBox.warning(
                self, "Invalid File",
                "File does not look like a gauge YAML\n(missing 'components' key)."
            )
            return
        self._gauge_path = path
        self._gauge_data = data
        self._gauge_dirty = False
        self._gauge_view.load(data, path)
        self._gauge_view.set_instruments_root(_find_instruments_root(path))
        self._preview.set_yaml(path, data_provider=lambda: self._gauge_data)
        self._update_save_btn(False)
        self._update_save_all_btn()
        self._update_play_btn()
        self._update_run_btn()
        self._update_title()
        n = len(data.get("components", []))
        self.statusBar().showMessage(
            f"{path}  |  {n} components  |  size {data.get('size', '?')}"
        )
        self._push_recent(path)

    def _load_panel(self, path: str, data: dict | None = None):
        if self._panel_dirty and not self._confirm_discard("panel"):
            return
        if data is None:
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception as exc:
                QMessageBox.critical(self, "Load Error", str(exc))
                return
        if not isinstance(data, dict) or "instruments" not in data:
            QMessageBox.warning(
                self, "Invalid File",
                "File does not look like a panel YAML\n(missing 'instruments' key)."
            )
            return
        self._panel_path = path
        self._panel_data = data
        self._panel_dirty = False
        self._panel_view.set_panels_root(_find_panels_root(path))
        self._panel_view.load(data, path)
        self._preview.set_yaml(path, data_provider=lambda: self._panel_data)
        self._update_save_btn(False)
        self._update_save_all_btn()
        self._update_script_btn()
        self._update_add_container_btn()
        self._update_play_btn()
        self._update_run_btn()
        self._update_title()
        n = len(data.get("instruments", []))
        self.statusBar().showMessage(
            f"{path}  |  {n} instruments  |  size {data.get('size', '?')}"
        )
        self._push_recent(path)

    # ── Dirty tracking ────────────────────────────────────────────────────

    def _mark_gauge_dirty(self):
        if not self._gauge_dirty:
            self._gauge_dirty = True
            self._update_save_btn(True)
            self._update_save_all_btn()
            self._update_title()

    def _mark_panel_dirty(self):
        if not self._panel_dirty:
            self._panel_dirty = True
            self._update_save_btn(True)
            self._update_save_all_btn()
            self._update_title()

    def _update_title(self):
        idx = self._tabs.currentIndex()
        if idx == _TAB_GAUGE:
            path = self._gauge_path
            name = self._gauge_data.get("name", Path(path).stem if path else "")
            dirty = self._gauge_dirty
        else:
            path = self._panel_path
            name = self._panel_data.get("name", Path(path).stem if path else "")
            dirty = self._panel_dirty
        prefix = "* " if dirty else ""
        self.setWindowTitle(
            f"{prefix}pyXplane Panels Designer — {name}" if name else "pyXplane Panels Designer"
        )

    # ── Save ──────────────────────────────────────────────────────────────

    def _save(self):
        if self._tabs.currentIndex() == _TAB_GAUGE:
            if not self._gauge_path:
                self._save_as()
                return
            self._write_gauge(self._gauge_path)
        else:
            if not self._panel_path:
                self._save_as()
                return
            self._write_panel(self._panel_path)

    def _save_as(self):
        if self._tabs.currentIndex() == _TAB_GAUGE:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Gauge YAML",
                self._gauge_path or "",
                "YAML files (*.yaml *.yml)"
            )
            if path:
                self._gauge_path = path
                self._write_gauge(path)
                self._preview.set_yaml(path, data_provider=lambda: self._gauge_data)
                self._push_recent(path)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Panel YAML",
                self._panel_path or "",
                "YAML files (*.yaml *.yml)"
            )
            if path:
                self._panel_path = path
                self._write_panel(path)
                self._preview.set_yaml(path, data_provider=lambda: self._panel_data)
                self._push_recent(path)

    def _write_gauge(self, path: str):
        self._gauge_data["name"] = self._gauge_view.get_name()
        self._gauge_data["components"] = self._gauge_view.get_components()
        self._gauge_data["size"] = self._gauge_view.get_size()
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self._gauge_data, f,
                    default_flow_style=False, allow_unicode=True, sort_keys=False,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return
        self._gauge_dirty = False
        self._update_save_btn(False)
        self._update_save_all_btn()
        self._update_title()
        self.statusBar().showMessage(f"Saved: {path}")

    def _write_panel(self, path: str):
        self._panel_data["name"] = self._panel_view.get_name()
        self._panel_data["instruments"] = self._panel_view.get_instruments()
        self._panel_data["size"] = self._panel_view.get_size()
        self._panel_data["background_color"] = self._panel_view.get_background_color()
        layout_scale = self._panel_view.get_layout_scale()
        if abs(layout_scale - 1.0) > 1e-4:
            self._panel_data["layout_scale"] = layout_scale
        else:
            self._panel_data.pop("layout_scale", None)
        layout_offset = self._panel_view.get_layout_offset()
        if any(abs(v) > 1e-4 for v in layout_offset):
            self._panel_data["layout_offset"] = layout_offset
        else:
            self._panel_data.pop("layout_offset", None)
        port = self._panel_view.get_listen_port()
        if port is not None:
            self._panel_data.setdefault("udp", {})["listen_port"] = port
        else:
            udp = self._panel_data.get("udp", {})
            udp.pop("listen_port", None)
            if not udp:
                self._panel_data.pop("udp", None)
        win_opts = self._panel_view.get_window_opts()
        if win_opts:
            self._panel_data["window"] = win_opts
        else:
            self._panel_data.pop("window", None)
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self._panel_data, f,
                    default_flow_style=False, allow_unicode=True, sort_keys=False,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return
        self._panel_dirty = False
        self._update_save_btn(False)
        self._update_save_all_btn()
        self._update_script_btn()
        self._update_add_container_btn()
        self._update_title()
        self.statusBar().showMessage(f"Saved: {path}")

    # ── Close ─────────────────────────────────────────────────────────────

    def _confirm_discard(self, mode: str) -> bool:
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            f"The {mode} has unsaved changes. Discard and continue?",
            QMessageBox.Discard | QMessageBox.Cancel,
        )
        return reply == QMessageBox.Discard

    def closeEvent(self, event):
        if self._gauge_dirty and not self._confirm_discard("gauge"):
            event.ignore()
            return
        if self._panel_dirty and not self._confirm_discard("panel"):
            event.ignore()
            return
        self._gauge_view.stop_test()
        self._gauge_view.stop_live()
        self._preview.stop_live()
        self._settings.setValue("windowGeometry", self.saveGeometry())
        self._gauge_view.save_state(self._settings)
        self._panel_view.save_state(self._settings)
        event.accept()
