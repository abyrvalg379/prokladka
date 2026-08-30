# -*- coding: utf-8 -*-
"""
bridge_qt.py — Qt panel PROKLADKA для Houdini.

Стилизован под STUKACH (Blender-dark QSS). Симметрично с Maya Qt side.
Запуск: launch() из __init__.py или prokladka_hou.launch().
"""
from __future__ import annotations

import os
import contextlib

import hou

# PySide6 в Houdini 20.5+, PySide2 в 20.0
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import Qt
    _QT6 = True
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import Qt
    _QT6 = False

try:
    from . import prokladka_hou as B  # package-режим (python3.11libs)
except ImportError:
    import prokladka_hou as B  # legacy top-level


# ════════════════════════════════════════════════════════════════════════════
# STUKACH-DARK QSS (как в Maya Qt)
# ════════════════════════════════════════════════════════════════════════════

def _get_base_font_size() -> int:
    try:
        app = QtWidgets.QApplication.instance()
        return app.font().pixelSize() if app.font().pixelSize() > 0 else 13
    except Exception:
        return 13

_FONT_PX = _get_base_font_size()

def _px(base: int) -> int:
    return max(1, int(base * (_FONT_PX / 13.0)))


def _build_qss() -> str:
    f = _FONT_PX
    c = _px(16)
    return (
        "QWidget { background: #1d1d1d; color: #e6e6e6; font-family: 'Segoe UI','Arial',sans-serif; font-size: %dpx; }"
        "QPushButton { background: #303030; color: #e6e6e6; border: 1px solid #3a3a3a; border-radius: 3px; padding: %dpx %dpx; font-size: %dpx; }"
        "QPushButton:hover { background: #3d3d3d; }"
        "QPushButton:pressed { background: #252525; }"
        "QPushButton:disabled { color: #606060; background: #252525; }"
        "QCheckBox { spacing: 5px; }"
        "QCheckBox::indicator { width: %dpx; height: %dpx; border: 1px solid #555; border-radius: 2px; background: #252525; }"
        "QCheckBox::indicator:hover { border-color: #4772b3; }"
        "QCheckBox::indicator:checked { background: #4772b3; border-color: #4772b3; image: none; }"
        "QComboBox { background: #303030; color: #e6e6e6; border: 1px solid #3a3a3a; padding: 3px 8px; font-size: %dpx; border-radius: 3px; }"
        "QComboBox::drop-down { border: none; width: %dpx; }"
        "QComboBox QAbstractItemView { background: #252525; color: #e6e6e6; selection-background-color: #3d5d8a; border: 1px solid #3a3a3a; outline: none; }"
        "QLineEdit { background: #252525; color: #e6e6e6; border: 1px solid #3a3a3a; padding: 3px 6px; font-size: %dpx; border-radius: 2px; }"
        "QLabel { background: transparent; }"
        "QScrollArea { border: none; background: transparent; }"
        "QScrollBar:vertical { background: #1d1d1d; width: %dpx; border: none; }"
        "QScrollBar::handle:vertical { background: #3a3a3a; border-radius: 4px; min-height: %dpx; }"
        "QScrollBar::handle:vertical:hover { background: #4a4a4a; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
    ) % (f, _px(4), _px(10), f, c, c, f, _px(20), f, _px(30), _px(10))

_QSS = _build_qss()

_C_BUTTON   = "#4772b3"
_C_GREEN    = "#477a3c"
_C_RED      = "#ad4133"
_C_SUBTEXT  = "#8c8c8c"


@contextlib.contextmanager
def block_signals(*widgets):
    for w in widgets:
        w.blockSignals(True)
    try:
        yield
    finally:
        for w in widgets:
            w.blockSignals(False)


# ════════════════════════════════════════════════════════════════════════════
# COLLAPSE BOX (как в Maya Qt PROKLADKA)
# ════════════════════════════════════════════════════════════════════════════

class _CollapseBox(QtWidgets.QWidget):
    """Свёртываемая секция: заголовок ▼/▶ + контент."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(_px(2), _px(3), _px(2), _px(3))
        header.setSpacing(_px(4))

        self._collapse_btn = QtWidgets.QPushButton("▼")
        self._collapse_btn.setFixedSize(_px(16), _px(16))
        self._collapse_btn.setFlat(True)
        self._collapse_btn.setStyleSheet(
            "QPushButton { color: #8c8c8c; border: none; font-size: %dpx; padding: 0; }"
            "QPushButton:hover { color: #e6e6e6; }" % _FONT_PX)
        self._collapse_btn.clicked.connect(self._on_collapse)
        header.addWidget(self._collapse_btn)

        title_lbl = QtWidgets.QLabel(title)
        title_lbl.setStyleSheet("color: #c8c8c8; font-size: %dpx; font-weight: bold;" % _FONT_PX)
        header.addWidget(title_lbl)
        header.addStretch()
        outer.addLayout(header)

        sep = QtWidgets.QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2a2a2a;")
        outer.addWidget(sep)

        self._content = QtWidgets.QWidget()
        self._content_layout = QtWidgets.QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(_px(8), _px(4), 0, _px(4))
        self._content_layout.setSpacing(_px(4))
        outer.addWidget(self._content)

        self._open = True

    def addWidget(self, widget) -> None:
        self._content_layout.addWidget(widget)

    def addLayout(self, layout) -> None:
        self._content_layout.addLayout(layout)

    def _on_collapse(self) -> None:
        self._open = not self._open
        self._content.setVisible(self._open)
        self._collapse_btn.setText("▼" if self._open else "▶")


# ════════════════════════════════════════════════════════════════════════════
# MAIN PANEL
# ════════════════════════════════════════════════════════════════════════════

class BridgePanel(QtWidgets.QWidget):
    """PROKLADKA — Qt panel для Houdini."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PROKLADKA — Houdini сторона")
        self.setObjectName("ProkladkaHouPanel")
        self.setMinimumWidth(_px(400))
        self.setStyleSheet(_QSS)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(_px(8), _px(8), _px(8), _px(8))
        root.setSpacing(_px(6))

        root.addWidget(self._build_header())
        root.addWidget(self._build_recent_section())
        root.addWidget(self._build_export_section())
        root.addWidget(self._build_import_section())
        root.addWidget(self._build_naming_section())
        root.addStretch()

    # ── Header ────────────────────────────────────────────────────────────
    def _build_header(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QtWidgets.QLabel("PROKLADKA")
        title.setStyleSheet("color: #c8c8c8; font-size: %dpx; font-weight: bold;" % (_FONT_PX + 2))
        lay.addWidget(title)
        lay.addStretch()
        self._status_lbl = QtWidgets.QLabel("")
        self._status_lbl.setStyleSheet("color: %s; font-size: %dpx;" % (_C_SUBTEXT, _FONT_PX))
        lay.addWidget(self._status_lbl)
        return w

    # ── Recent ────────────────────────────────────────────────────────────
    def _build_recent_section(self) -> _CollapseBox:
        box = _CollapseBox("Recent")
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(_px(4))
        self._recent_combo = QtWidgets.QComboBox()
        self._recent_combo.setMinimumWidth(_px(280))
        row.addWidget(self._recent_combo, 1)
        btn_refresh = QtWidgets.QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_recent)
        row.addWidget(btn_refresh)
        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_recent)
        row.addWidget(btn_clear)
        btn_hist = QtWidgets.QPushButton("History")
        btn_hist.clicked.connect(self._show_history)
        row.addWidget(btn_hist)
        box.addLayout(row)
        self._refresh_recent()
        return box

    def _show_history(self):
        QtWidgets.QMessageBox.information(
            self, "PROKLADKA Export History", B.recent_history_report())

    def _clear_recent(self):
        ret = QtWidgets.QMessageBox.question(
            self, "PROKLADKA", "Очистить историю экспортов?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if ret != QtWidgets.QMessageBox.Yes:
            return
        B.clear_recent_json()
        self._refresh_recent()

    # ── Export ────────────────────────────────────────────────────────────
    def _build_export_section(self) -> _CollapseBox:
        box = _CollapseBox("Export")

        # Format dropdown
        row_fmt = QtWidgets.QHBoxLayout()
        row_fmt.setSpacing(_px(4))
        row_fmt.addWidget(QtWidgets.QLabel("Format:"))
        self._format_combo = QtWidgets.QComboBox()
        for key, cfg in B.EXPORT_FORMATS.items():
            self._format_combo.addItem(cfg["label"], key)
        self._format_combo.setCurrentText(B.EXPORT_FORMATS["fbx"]["label"])
        row_fmt.addWidget(self._format_combo, 1)
        box.addLayout(row_fmt)

        # Animation checkbox + frame range
        row_anim = QtWidgets.QHBoxLayout()
        row_anim.setSpacing(_px(4))
        self._anim_cb = QtWidgets.QCheckBox("Animation")
        self._anim_cb.setChecked(False)
        self._anim_cb.stateChanged.connect(self._on_anim_toggled)
        row_anim.addWidget(self._anim_cb)

        row_anim.addWidget(QtWidgets.QLabel("Frames:"))
        start, end = B.get_current_frame_range()
        self._frame_start = QtWidgets.QSpinBox()
        self._frame_start.setRange(0, 100000)
        self._frame_start.setValue(start)
        self._frame_start.setEnabled(False)
        row_anim.addWidget(self._frame_start)
        row_anim.addWidget(QtWidgets.QLabel("-"))
        self._frame_end = QtWidgets.QSpinBox()
        self._frame_end.setRange(0, 100000)
        self._frame_end.setValue(end)
        self._frame_end.setEnabled(False)
        row_anim.addWidget(self._frame_end)
        box.addLayout(row_anim)

        # Export button
        btn_export = QtWidgets.QPushButton("EXPORT TO FILE")
        btn_export.setMinimumHeight(_px(36))
        btn_export.setStyleSheet(
            "QPushButton { background: %s; color: #fff; font-weight: bold; }"
            "QPushButton:hover { background: #5683c8; }" % _C_BUTTON)
        btn_export.clicked.connect(self._on_export)
        box.addWidget(btn_export)

        # Hint
        hint = QtWidgets.QLabel("Active SOP from selection will be exported")
        hint.setStyleSheet("color: %s; font-size: %dpx;" % (_C_SUBTEXT, _FONT_PX - 1))
        hint.setWordWrap(True)
        box.addWidget(hint)

        return box

    # ── Import ────────────────────────────────────────────────────────────
    def _build_import_section(self) -> _CollapseBox:
        box = _CollapseBox("Import")

        # Главный Import — как Maya: напрямую из Recent combo
        btn_import = QtWidgets.QPushButton("Import")
        btn_import.setMinimumHeight(_px(36))
        btn_import.setStyleSheet(
            "QPushButton { background: %s; color: #fff; font-weight: bold; }"
            "QPushButton:hover { background: #589456; }" % _C_GREEN)
        btn_import.clicked.connect(self._on_import_recent)
        box.addWidget(btn_import)

        # Browse — отдельная кнопка для выбора файла вручную
        browse_row = QtWidgets.QHBoxLayout()
        browse_row.setSpacing(_px(4))
        btn_browse = QtWidgets.QPushButton("Browse...")
        btn_browse.clicked.connect(self._on_import_from_dialog)
        browse_row.addWidget(btn_browse)

        btn_refresh = QtWidgets.QPushButton("Refresh Recent")
        btn_refresh.clicked.connect(self._refresh_recent)
        browse_row.addWidget(btn_refresh)
        box.addLayout(browse_row)

        hint = QtWidgets.QLabel("Auto-detect FBX/VDB/Alembic/USD by extension")
        hint.setStyleSheet("color: %s; font-size: %dpx;" % (_C_SUBTEXT, _FONT_PX - 1))
        hint.setWordWrap(True)
        box.addWidget(hint)

        return box

    # ── Naming ────────────────────────────────────────────────────────────
    def _build_naming_section(self) -> _CollapseBox:
        box = _CollapseBox("Naming")

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(_px(4))
        row.addWidget(QtWidgets.QLabel("Preset:"))
        self._naming_combo = QtWidgets.QComboBox()
        for key in B.HOUDINI_NAMING_PRESETS:
            self._naming_combo.addItem(key)
        row.addWidget(self._naming_combo, 1)
        box.addLayout(row)

        btn_apply = QtWidgets.QPushButton("Apply Naming")
        btn_apply.clicked.connect(self._on_apply_naming)
        box.addWidget(btn_apply)

        hint = QtWidgets.QLabel("Node names + suffixes (_geo/_vdb/_abc/_usd)")
        hint.setStyleSheet("color: %s; font-size: %dpx;" % (_C_SUBTEXT, _FONT_PX - 1))
        hint.setWordWrap(True)
        box.addWidget(hint)

        return box

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_anim_toggled(self, state) -> None:
        enabled = bool(state)
        if hasattr(state, 'value'):
            enabled = int(state) == 2  # Qt.Checked
        self._frame_start.setEnabled(enabled)
        self._frame_end.setEnabled(enabled)

    def _refresh_recent(self) -> None:
        self._recent_combo.clear()
        paths = B.read_recent_files()
        if not paths:
            self._recent_combo.addItem("(no recent files)")
            return
        for p in paths:
            # Показывать имя + размер (как Maya)
            try:
                size_kb = os.path.getsize(p) // 1024
                label = "{} ({} KB)".format(os.path.basename(p), size_kb)
            except Exception:
                label = os.path.basename(p)
            self._recent_combo.addItem(label, p)

    def _on_export(self) -> None:
        # currentData() может вернуть None в PySide6 — fallback на currentIndex + dict
        fmt = self._format_combo.currentData()
        if not fmt:
            keys = list(B.EXPORT_FORMATS.keys())
            idx = self._format_combo.currentIndex()
            fmt = keys[idx] if 0 <= idx < len(keys) else "fbx"
        frame_range = None
        if self._anim_cb.isChecked():
            frame_range = (self._frame_start.value(), self._frame_end.value())

        try:
            path = B.export_current(fmt, frame_range=frame_range)
            if path:
                self._set_status("Exported {}".format(os.path.basename(path)), _C_GREEN)
                self._refresh_recent()
            else:
                self._set_status("Export failed", _C_RED)
        except Exception as e:
            self._set_status("Export error", _C_RED)
            hou.ui.displayMessage("Export error: {}".format(e))

    def _on_import_from_dialog(self) -> None:
        # Houdini file picker через hou.ui
        # chooser_mode enum может отличаться между версиями — try/except
        try:
            try:
                chooser = hou.fileChooserMode.Read
            except AttributeError:
                try:
                    chooser = hou.fileChooserMode.read  # lowercase в некоторых версиях
                except AttributeError:
                    chooser = 0  # fallback: int enum value

            path = hou.ui.selectFile(
                title="Select file to import",
                pattern="*",
                chooser_mode=chooser,
            )
            if path:
                node = B.import_file(path)
                if node:
                    self._set_status("Imported: {}".format(os.path.basename(path)), _C_GREEN)
                else:
                    self._set_status("Import failed", _C_RED)
        except Exception as e:
            hou.ui.displayMessage("Import error: {}".format(e))

    def _on_import_recent(self) -> None:
        if self._recent_combo.count() == 0:
            return
        path = self._recent_combo.currentData()
        if not path or path == "(no recent files)":
            hou.ui.displayMessage("No recent file selected")
            return
        node = B.import_file(path)
        if node:
            self._set_status("Imported: {}".format(os.path.basename(path)), _C_GREEN)
        else:
            self._set_status("Import failed", _C_RED)

    def _on_apply_naming(self) -> None:
        preset = self._naming_combo.currentText()
        try:
            # Применить к выделенным nodes или к активному SOP
            selected = hou.selectedNodes()
            if not selected:
                hou.ui.displayMessage("Select a node first")
                return
            total = 0
            for n in selected:
                total += B.apply_hou_naming(n, preset_name=preset, recursive=True)
            self._set_status("Renamed {} nodes".format(total), _C_GREEN)
        except Exception as e:
            hou.ui.displayMessage("Naming error: {}".format(e))

    def _set_status(self, text: str, color: str = _C_SUBTEXT) -> None:
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet("color: %s; font-size: %dpx;" % (color, _FONT_PX))


# ════════════════════════════════════════════════════════════════════════════
# LAUNCHER
# ════════════════════════════════════════════════════════════════════════════

_PANEL_INSTANCE = None

def launch() -> "BridgePanel":
    """Открыть PROKLADKA panel в Houdini."""
    global _PANEL_INSTANCE
    if _PANEL_INSTANCE is not None:
        try:
            _PANEL_INSTANCE.close()
            _PANEL_INSTANCE.deleteLater()
        except Exception:
            pass
        _PANEL_INSTANCE = None

    panel = BridgePanel()
    # Parent к главному окну Houdini (остаётся активным + корректный стиль)
    try:
        panel.setParent(hou.qt.mainWindow(), Qt.Window)
    except Exception:
        pass
    panel.show()
    panel.raise_()
    _PANEL_INSTANCE = panel
    return panel


if __name__ == "__main__":
    launch()
