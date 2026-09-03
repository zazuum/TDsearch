#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""PySide6 Desktop Graphical User Interface (GUI) for Tabular Data Search (TDsearch)."""

import csv
import os
import re
import sys
from pathlib import Path
from time import perf_counter

try:
    from PySide6.QtCore import QSettings, QStandardPaths, QThread, Signal, Qt
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QGridLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QMenu,
        QCheckBox,
        QComboBox,
        QTableWidget,
        QTableWidgetItem,
        QFileDialog,
        QMessageBox,
        QStatusBar,
        QGroupBox,
        QHeaderView,
        QProgressBar,
        QDialog,
        QDialogButtonBox,
        QPlainTextEdit,
        QTabWidget,
        QSizePolicy,
    )
    from PySide6.QtGui import QColor, QFont, QPalette
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False

try:
    from xlsxgrep import process_single_file, __version__ as xlsxgrep_version
except ImportError:
    try:
        from xlsxgrep.xlsxgrep import process_single_file, __version__ as xlsxgrep_version
    except ImportError:
        process_single_file = None
        xlsxgrep_version = "unknown"

try:
    from tdsearch import __version__ as tdsearch_version
except ModuleNotFoundError:
    from __init__ import __version__ as tdsearch_version


SUPPORTED_EXTENSIONS = (
    ".xls",
    ".xlsx",
    ".ods",
    ".csv",
    ".tsv",
    ".xlsm",
)


IGNORE_CASE_INLINE_FLAG_RE = re.compile(r"^\(\?[a-zA-Z-]*i[a-zA-Z-]*\)")
SETTINGS_ORGANIZATION = "TDsearch"
SETTINGS_APPLICATION = "TDsearch"
VALID_THEME_CHOICES = {"system", "dark", "light"}


def collect_target_files(path_str, recursive=True):
    path = Path(path_str)
    file_list = []
    if not path.exists():
        return file_list

    if path.is_file():
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            file_list.append(str(path))
    elif path.is_dir():
        pattern = "**/*" if recursive else "*"
        for p in path.glob(pattern):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                file_list.append(str(p))

    return file_list


def build_search_options(
    pattern,
    *,
    fixed_strings,
    regex_enabled,
    posix_ere,
    ignore_case,
    word_regexp,
    recursive,
    jobs,
    count,
    with_filename,
    with_sheetname,
    files_with_match,
    files_without_match,
    column_mode,
    separator,
    debug=False,
):
    if regex_enabled:
        fixed_strings = False
        word_regexp = False
        ignore_case = False
    elif fixed_strings:
        word_regexp = False

    python_regex = regex_enabled and not posix_ere
    extended_regexp = regex_enabled and posix_ere
    effective_pattern = pattern
    effective_ignore_case = ignore_case

    if word_regexp:
        escaped_pattern = re.escape(pattern)
        effective_pattern = rf"(?<!\w){escaped_pattern}(?!\w)"
        if ignore_case:
            effective_pattern = f"(?i){effective_pattern}"
        python_regex = True
        extended_regexp = False
        effective_ignore_case = False
        word_regexp = False

    elif python_regex and ignore_case and not IGNORE_CASE_INLINE_FLAG_RE.match(pattern):
        effective_pattern = f"(?i){pattern}"
        effective_ignore_case = False

    return {
        "PATTERN": effective_pattern,
        "python_regex": python_regex,
        "extended_regexp": extended_regexp,
        "fixed_strings": fixed_strings,
        "ignore_case": effective_ignore_case,
        "word_regexp": word_regexp,
        "recursive": recursive,
        "jobs": jobs,
        "count": count,
        "with_filename": with_filename,
        "with_sheetname": with_sheetname,
        "files_with_match": files_with_match,
        "files_without_match": files_without_match,
        "column": column_mode,
        "row": not column_mode,
        "null": False,
        "separator": separator,
        "debug": debug,
    }


def _pluralize(count, singular, plural=None):
    if count == 1:
        return singular
    return plural or f"{singular}s"


def format_search_status_message(
    opts,
    *,
    file_count,
    result_count,
    matched_group_count=0,
    matched_file_count=0,
    matched_cell_count=0,
    matched_string_count=0,
):
    searched_file_label = _pluralize(file_count, "file")

    if opts["files_with_match"]:
        match_label = _pluralize(matched_file_count, "matching file")
        return (
            f"Search completed. Found {matched_file_count} {match_label} "
            f"across {file_count} searched {searched_file_label}."
        )

    if opts["files_without_match"]:
        match_label = _pluralize(matched_file_count, "file without a match", "files without a match")
        return (
            f"Search completed. Found {matched_file_count} {match_label} "
            f"across {file_count} searched {searched_file_label}."
        )

    if opts["count"]:
        group_label = _pluralize(
            matched_group_count,
            "matching column" if opts["column"] else "matching row",
        )
        cell_label = _pluralize(matched_cell_count, "cell")
        string_label = _pluralize(matched_string_count, "string")
        return (
            f"Search completed. Found {matched_group_count} {group_label}, "
            f"{matched_cell_count} {cell_label}, {matched_string_count} {string_label} "
            f"across {file_count} {searched_file_label}."
        )

    if opts["column"]:
        result_label = _pluralize(result_count, "result cell")
        return (
            f"Search completed. Displaying {result_count} {result_label} "
            f"from matching columns across {file_count} {searched_file_label}."
        )

    result_label = _pluralize(result_count, "matching row")
    return (
        f"Search completed. Found {result_count} {result_label} "
        f"across {file_count} {searched_file_label}."
    )


def format_elapsed_time(seconds):
    if seconds < 1:
        return f"{seconds:.3f}s"
    if seconds < 10:
        return f"{seconds:.2f}s"
    if seconds < 60:
        return f"{seconds:.1f}s"

    minutes = int(seconds // 60)
    remaining_seconds = seconds - (minutes * 60)
    if remaining_seconds.is_integer():
        return f"{minutes}m {int(remaining_seconds)}s"
    return f"{minutes}m {remaining_seconds:.1f}s"


def normalize_processing_errors(error_lines):
    return [line.strip() for line in error_lines if line and line.strip()]


def format_processing_error_tooltip(error_count):
    file_label = _pluralize(error_count, "file")
    verb = "was" if error_count == 1 else "were"
    return f"{error_count} {file_label} {verb} not processed. Click for details."


def format_processing_error_summary(error_count):
    file_label = _pluralize(error_count, "file")
    verb = "was" if error_count == 1 else "were"
    return f"{error_count} {file_label} {verb} not processed."


def build_processing_error_details(error_lines):
    return "\n".join(normalize_processing_errors(error_lines))


def build_progress_message(processed_files, total_files):
    if total_files <= 0:
        return "Searching across 0 files..."
    return f"Searching... {processed_files}/{total_files} files processed"


def format_count_result_summary(opts, group_count, cell_count, string_count):
    group_label = _pluralize(
        group_count,
        "matching column" if opts["column"] else "matching row",
    )
    cell_label = _pluralize(cell_count, "cell")
    string_label = _pluralize(string_count, "string")
    return (
        f"{group_count} {group_label}, {cell_count} {cell_label}, "
        f"{string_count} {string_label}"
    )


def normalize_theme_choice(theme_choice):
    if theme_choice in VALID_THEME_CHOICES:
        return theme_choice
    return "system"


def build_dark_palette():
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    return palette


def build_light_palette():
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(245, 245, 245))
    palette.setColor(QPalette.WindowText, Qt.black)
    palette.setColor(QPalette.Base, Qt.white)
    palette.setColor(QPalette.AlternateBase, QColor(238, 238, 238))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.black)
    palette.setColor(QPalette.Text, Qt.black)
    palette.setColor(QPalette.Button, QColor(245, 245, 245))
    palette.setColor(QPalette.ButtonText, Qt.black)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(0, 102, 204))
    palette.setColor(QPalette.Highlight, QColor(76, 163, 224))
    palette.setColor(QPalette.HighlightedText, Qt.white)
    return palette


if PYSIDE_AVAILABLE:
    def default_documents_directory():
        documents_path = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        if documents_path:
            return documents_path
        return str(Path.home())


    class SearchWorkerThread(QThread):
        """Background thread for executing searches without freezing the GUI."""

        result_signal = Signal(dict)
        progress_signal = Signal(int, int, str)

        def __init__(self, path_str, recursive, opts):
            super().__init__()
            self.path_str = path_str
            self.recursive = recursive
            self.opts = opts

        def run(self):
            if process_single_file is None:
                self.result_signal.emit({
                    "results": [],
                    "file_count": 0,
                    "result_count": 0,
                    "matched_group_count": 0,
                    "matched_cell_count": 0,
                    "matched_string_count": 0,
                    "matched_file_count": 0,
                    "error": "xlsxgrep engine is not installed. Please run: pip install xlsxgrep"
                })
                return

            files = collect_target_files(self.path_str, self.recursive)
            results = []
            matched_group_count = 0
            matched_cell_count = 0
            matched_string_count = 0
            matched_file_count = 0
            processing_errors = []

            total_files = len(files)
            self.progress_signal.emit(0, max(total_files, 1), build_progress_message(0, total_files))

            for idx, f in enumerate(files):
                res = process_single_file(f, self.opts)
                stdout_lines = res.get("stdout", [])
                counts = res.get("counts", (0, 0, 0))
                processing_errors.extend(normalize_processing_errors(res.get("stderr", [])))
                matched_group_count += counts[0]
                matched_cell_count += counts[1]
                matched_string_count += counts[2]
                if stdout_lines:
                    matched_file_count += 1

                if self.opts["count"]:
                    if counts[0] > 0:
                        results.append((
                            f,
                            "",
                            format_count_result_summary(self.opts, counts[0], counts[1], counts[2]),
                        ))
                else:
                    for line in stdout_lines:
                        line_str = line.rstrip("\r\n")
                        file_name = ""
                        sheet_name = ""
                        content = line_str
                        if self.opts["with_filename"] and self.opts["with_sheetname"]:
                            parts = line_str.split(": ", 2)
                        else:
                            parts = line_str.split(": ", 1)

                        if self.opts["with_filename"] and self.opts["with_sheetname"] and len(parts) == 3:
                            file_name, sheet_name, content = parts
                        elif self.opts["with_filename"] and len(parts) == 2:
                            file_name, content = parts
                        elif self.opts["with_sheetname"] and len(parts) == 2:
                            sheet_name, content = parts

                        results.append((file_name, sheet_name, content))

                processed_files = idx + 1
                self.progress_signal.emit(
                    processed_files,
                    max(total_files, 1),
                    build_progress_message(processed_files, total_files),
                )

            self.result_signal.emit({
                "results": results,
                "file_count": len(files),
                "result_count": len(results),
                "matched_group_count": matched_group_count,
                "matched_cell_count": matched_cell_count,
                "matched_string_count": matched_string_count,
                "matched_file_count": matched_file_count,
                "processing_errors": processing_errors,
                "status_message": format_search_status_message(
                    self.opts,
                    file_count=len(files),
                    result_count=len(results),
                    matched_group_count=matched_group_count,
                    matched_file_count=matched_file_count,
                    matched_cell_count=matched_cell_count,
                    matched_string_count=matched_string_count,
                ),
            })

    class TDSearchGUI(QMainWindow):
        """TDsearch PySide6 Desktop Application."""

        def __init__(self):
            super().__init__()
            self.setWindowTitle(f"TDsearch v{tdsearch_version} (xlsxgrep v{xlsxgrep_version})")
            self.resize(900, 720)
            self.search_start_time = None
            self.processing_errors = []
            self.settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
            app = QApplication.instance()
            self.original_palette = QPalette(app.palette())
            self.original_style_name = app.style().objectName()
            self.original_stylesheet = app.styleSheet()

            self.init_ui()

        def init_ui(self):
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            main_layout = QVBoxLayout(central_widget)

            # --- Search Controls Panel ---
            panel = QGroupBox("Tabular Data Search Parameters")
            panel_layout = QVBoxLayout(panel)

            # Pattern row
            row1 = QHBoxLayout()
            row1.addWidget(QLabel("Pattern:"))
            self.inp_pattern = QLineEdit()
            self.inp_pattern.setPlaceholderText("Enter search string or regex pattern...")
            self.inp_pattern.returnPressed.connect(self.start_search)
            row1.addWidget(self.inp_pattern)
            panel_layout.addLayout(row1)

            # Path row
            row2 = QHBoxLayout()
            row2.addWidget(QLabel("Path:"))
            self.inp_path = QLineEdit(default_documents_directory())
            self.inp_path.setPlaceholderText("File or directory path...")
            row2.addWidget(self.inp_path)

            btn_open = QPushButton("Open...")
            open_menu = QMenu(btn_open)
            open_file_action = open_menu.addAction("Open File...")
            open_file_action.triggered.connect(self.browse_file)
            open_folder_action = open_menu.addAction("Open Folder...")
            open_folder_action.triggered.connect(self.browse_directory)
            btn_open.setMenu(open_menu)
            row2.addWidget(btn_open)

            panel_layout.addLayout(row2)

            self.options_tabs = QTabWidget()
            panel_layout.addWidget(self.options_tabs)

            search_options_tab = QWidget()
            search_options_layout = QVBoxLayout(search_options_tab)
            search_options_layout.setContentsMargins(8, 8, 8, 8)

            options_grid = QGridLayout()
            options_grid.setHorizontalSpacing(18)
            options_grid.setVerticalSpacing(8)
            for column in range(4):
                options_grid.setColumnStretch(column, 1)

            self.chk_word_regexp = QCheckBox("Match whole words only")
            self.chk_ignore_case = QCheckBox("Ignore uppercase/lowercase")
            self.chk_ignore_case.setChecked(True)
            self.chk_fixed_strings = QCheckBox("Plain text search")
            self.chk_fixed_strings.setChecked(True)
            self.combo_regex_type = QComboBox()
            self.combo_regex_type.addItem("None", None)
            self.combo_regex_type.addItem("Python regex", False)
            self.combo_regex_type.addItem("POSIX regex", True)
            self.chk_count = QCheckBox("Show counts only")

            regex_options = QWidget()
            regex_options_layout = QHBoxLayout(regex_options)
            regex_options_layout.setContentsMargins(0, 0, 0, 0)
            regex_options_layout.setSpacing(6)
            regex_options_layout.addWidget(QLabel("Regex type:"))
            self.combo_regex_type.setFixedWidth(120)
            regex_options_layout.addWidget(self.combo_regex_type)
            regex_options.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

            options_grid.addWidget(self.chk_fixed_strings, 0, 0)
            options_grid.addWidget(self.chk_word_regexp, 0, 1)
            options_grid.addWidget(self.chk_ignore_case, 0, 2)

            self.chk_recursive = QCheckBox("Search subfolders")
            self.chk_recursive.setChecked(True)
            self.chk_filename = QCheckBox("Show file name")
            self.chk_sheetname = QCheckBox("Show sheet name")
            self.chk_lmatch = QCheckBox("Show only matching files")
            self.chk_lwithout = QCheckBox("Show only non-matching files")

            options_grid.addWidget(self.chk_filename, 1, 0)
            options_grid.addWidget(self.chk_sheetname, 1, 1)
            options_grid.addWidget(self.chk_count, 1, 2)
            options_grid.addWidget(self.chk_lmatch, 2, 0)
            options_grid.addWidget(self.chk_lwithout, 2, 1)

            self.chk_lmatch.toggled.connect(
                lambda checked: self.chk_lwithout.setChecked(False) if checked else None
            )
            self.chk_lwithout.toggled.connect(
                lambda checked: self.chk_lmatch.setChecked(False) if checked else None
            )
            self.chk_fixed_strings.toggled.connect(self.on_fixed_strings_toggled)
            self.chk_word_regexp.toggled.connect(self.on_word_regexp_toggled)
            self.combo_regex_type.currentIndexChanged.connect(self.on_regex_type_changed)
            self.chk_ignore_case.toggled.connect(self.on_ignore_case_toggled)
            self.chk_count.toggled.connect(self.on_count_toggled)
            self.combo_search_mode = QComboBox()
            self.combo_search_mode.addItem("Columns", True)
            self.combo_search_mode.addItem("Rows", False)
            self.combo_search_mode.setCurrentIndex(1)
            self.chk_custom_separator = QCheckBox("Custom separator")
            self.inp_sep = QLineEdit("\\t")
            self.inp_sep.setFixedWidth(60)
            self.inp_sep.setEnabled(False)
            self.chk_custom_separator.toggled.connect(self.inp_sep.setEnabled)

            search_mode_options = QWidget()
            search_mode_layout = QHBoxLayout(search_mode_options)
            search_mode_layout.setContentsMargins(0, 0, 0, 0)
            search_mode_layout.addWidget(QLabel("Search by:"))
            search_mode_layout.addWidget(self.combo_search_mode)

            separator_options = QWidget()
            separator_layout = QHBoxLayout(separator_options)
            separator_layout.setContentsMargins(0, 0, 0, 0)
            separator_layout.setSpacing(6)
            separator_layout.addWidget(self.chk_custom_separator)
            separator_layout.addWidget(self.inp_sep, 0, Qt.AlignLeft)
            separator_options.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

            right_options = QWidget()
            right_options_layout = QVBoxLayout(right_options)
            right_options_layout.setContentsMargins(0, 0, 0, 0)
            right_options_layout.setSpacing(8)
            right_options_layout.addWidget(regex_options)
            right_options_layout.addWidget(search_mode_options)
            right_options_layout.addWidget(separator_options)
            right_options_layout.addStretch()
            right_options.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

            options_grid.addWidget(self.chk_recursive, 2, 2)
            options_grid.addWidget(right_options, 0, 3, 3, 1, Qt.AlignTop | Qt.AlignLeft)
            search_options_layout.addLayout(options_grid)

            self.options_tabs.addTab(search_options_tab, "Search options")

            other_options_tab = QWidget()
            other_options_layout = QGridLayout(other_options_tab)
            other_options_layout.setContentsMargins(8, 8, 8, 8)
            other_options_layout.setHorizontalSpacing(20)
            other_options_layout.setVerticalSpacing(12)
            self.combo_theme = QComboBox()
            self.combo_theme.addItem("System default", "system")
            self.combo_theme.addItem("Dark", "dark")
            self.combo_theme.addItem("Light", "light")
            self.combo_search_engine = QComboBox()
            self.combo_search_engine.addItem(f"xlsxgrep v{xlsxgrep_version}", "xlsxgrep")
            self.combo_jobs = QComboBox()
            cpu_count = os.cpu_count() or 1
            self.combo_jobs.addItem("Auto (All Cores)", 0)
            self.combo_jobs.addItem("1 Core (Sequential)", 1)
            for c in range(2, min(cpu_count + 1, 17)):
                self.combo_jobs.addItem(f"{c} CPU Cores", c)

            other_options_layout.addWidget(QLabel("Appearance:"), 0, 0)
            other_options_layout.addWidget(self.combo_theme, 0, 1)
            other_options_layout.addWidget(QLabel("Search engine:"), 1, 0)
            other_options_layout.addWidget(self.combo_search_engine, 1, 1)
            other_options_layout.addWidget(QLabel("CPU Usage:"), 2, 0)
            other_options_layout.addWidget(self.combo_jobs, 2, 1)
            other_options_layout.setColumnStretch(1, 1)

            self.options_tabs.addTab(other_options_tab, "Other Options")
            self.options_tabs.setCurrentIndex(0)

            # Buttons Row
            row6 = QHBoxLayout()
            row6.addStretch()

            self.btn_search = QPushButton("Search")
            self.btn_search.setDefault(True)
            self.btn_search.clicked.connect(self.start_search)
            row6.addWidget(self.btn_search)

            btn_export = QPushButton("Export CSV...")
            btn_export.clicked.connect(self.export_csv)
            row6.addWidget(btn_export)

            btn_reset_options = QPushButton("Reset options")
            btn_reset_options.clicked.connect(self.reset_options)
            row6.addWidget(btn_reset_options)

            btn_clear = QPushButton("Clear Results")
            btn_clear.clicked.connect(self.clear_results)
            row6.addWidget(btn_clear)

            panel_layout.addLayout(row6)
            main_layout.addWidget(panel)

            # --- Results Table ---
            self.table = QTableWidget(0, 3)
            self.table.setHorizontalHeaderLabels(["File", "Sheet / Position", "Matched Row / Line"])
            self.table.setWordWrap(False)
            self.table.setAlternatingRowColors(True)
            self.reset_results_table_layout()
            self.chk_filename.toggled.connect(self.update_output_columns)
            self.chk_sheetname.toggled.connect(self.update_output_columns)
            self.update_output_columns()
            self.restore_selected_theme()
            self.combo_theme.currentIndexChanged.connect(self.on_theme_changed)
            main_layout.addWidget(self.table)

            # --- Status Bar & Progress Bar ---
            self.status_bar = QStatusBar()
            self.setStatusBar(self.status_bar)
            self.status_bar.showMessage("Ready.")

            self.btn_processing_warnings = QPushButton("⚠")
            self.btn_processing_warnings.setFlat(True)
            self.btn_processing_warnings.setVisible(False)
            self.btn_processing_warnings.setToolTip("")
            self.btn_processing_warnings.clicked.connect(self.show_processing_errors_dialog)
            self.status_bar.addPermanentWidget(self.btn_processing_warnings)

            self.lbl_elapsed_time = QLabel("")
            self.status_bar.addPermanentWidget(self.lbl_elapsed_time)

            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.setVisible(False)
            self.status_bar.addPermanentWidget(self.progress_bar)

        def browse_file(self):
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Spreadsheet File",
                self.inp_path.text().strip() or default_documents_directory(),
                "Spreadsheet Files (*.xlsx *.xls *.xlsm *.csv *.tsv *.ods);;All Files (*)",
            )
            if file_path:
                self.inp_path.setText(file_path)

        def browse_directory(self):
            dir_path = QFileDialog.getExistingDirectory(
                self,
                "Select Folder to Search",
                self.inp_path.text().strip() or default_documents_directory(),
            )
            if dir_path:
                self.inp_path.setText(dir_path)

        def clear_results(self):
            self.table.setRowCount(0)
            self.reset_results_table_layout()
            self.table.verticalScrollBar().setValue(0)
            self.search_start_time = None
            self.lbl_elapsed_time.setText("")
            self.set_processing_errors([])
            self.status_bar.showMessage("Results cleared.", 3000)

        def reset_options(self):
            self.chk_ignore_case.setChecked(True)
            self.chk_word_regexp.setChecked(False)
            self.chk_fixed_strings.setChecked(True)
            self.combo_regex_type.setCurrentIndex(0)
            self.chk_count.setChecked(False)

            self.chk_recursive.setChecked(True)
            self.chk_filename.setChecked(False)
            self.chk_sheetname.setChecked(False)
            self.chk_lmatch.setChecked(False)
            self.chk_lwithout.setChecked(False)

            self.combo_search_mode.setCurrentIndex(1)
            self.chk_custom_separator.setChecked(False)
            self.inp_sep.setText("\\t")

            theme_index = self.combo_theme.findData("system")
            if theme_index < 0:
                theme_index = 0
            self.combo_theme.setCurrentIndex(theme_index)
            self.combo_search_engine.setCurrentIndex(0)

            jobs_index = self.combo_jobs.findData(0)
            if jobs_index < 0:
                jobs_index = 0
            self.combo_jobs.setCurrentIndex(jobs_index)

            self.options_tabs.setCurrentIndex(0)
            self.status_bar.showMessage("Options reset.", 3000)

        def reset_results_table_layout(self):
            header = self.table.horizontalHeader()
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.Stretch)
            header.setStretchLastSection(True)
            self.table.horizontalScrollBar().setValue(0)

        def fit_results_table_to_contents(self):
            header = self.table.horizontalHeader()
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            header.setSectionResizeMode(0, QHeaderView.Interactive)
            header.setSectionResizeMode(1, QHeaderView.Interactive)
            header.setSectionResizeMode(2, QHeaderView.Interactive)
            header.setStretchLastSection(False)
            self.table.resizeColumnsToContents()
            self.ensure_file_column_width()
            self.table.horizontalScrollBar().setValue(0)

        def update_output_columns(self):
            self.table.setColumnHidden(0, not self.chk_filename.isChecked())
            self.table.setColumnHidden(1, not self.chk_sheetname.isChecked())
            self.ensure_file_column_width()

        def ensure_file_column_width(self):
            if self.table.isColumnHidden(0):
                return

            header = self.table.horizontalHeader()
            sheet_width = max(self.table.columnWidth(1), header.defaultSectionSize())
            minimum_file_width = sheet_width * 2
            if self.table.columnWidth(0) < minimum_file_width:
                self.table.setColumnWidth(0, minimum_file_width)

        def on_fixed_strings_toggled(self, checked):
            if checked:
                self.chk_word_regexp.setChecked(False)
                self.combo_regex_type.setCurrentIndex(0)

        def on_word_regexp_toggled(self, checked):
            if checked:
                self.chk_fixed_strings.setChecked(False)
                self.combo_regex_type.setCurrentIndex(0)

        def on_regex_type_changed(self, index):
            if self.combo_regex_type.itemData(index) is not None:
                self.chk_fixed_strings.setChecked(False)
                self.chk_word_regexp.setChecked(False)
                self.chk_ignore_case.setChecked(False)

        def on_ignore_case_toggled(self, checked):
            if checked:
                self.combo_regex_type.setCurrentIndex(0)

        def on_count_toggled(self, checked):
            self.update_output_columns()


        def restore_selected_theme(self):
            saved_theme = normalize_theme_choice(self.settings.value("ui/theme", "system"))
            theme_index = self.combo_theme.findData(saved_theme)
            if theme_index < 0:
                theme_index = 0
            self.combo_theme.setCurrentIndex(theme_index)
            self.apply_selected_theme(saved_theme)

        def on_theme_changed(self):
            selected_theme = normalize_theme_choice(self.combo_theme.currentData())
            self.apply_selected_theme(selected_theme)
            self.settings.setValue("ui/theme", selected_theme)

        def apply_selected_theme(self, selected_theme=None):
            app = QApplication.instance()
            selected_theme = normalize_theme_choice(selected_theme or self.combo_theme.currentData())

            if selected_theme == "dark":
                app.setStyle("Fusion")
                app.setPalette(build_dark_palette())
                app.setStyleSheet("")
            elif selected_theme == "light":
                app.setStyle("Fusion")
                app.setPalette(build_light_palette())
                app.setStyleSheet("")
            else:
                app.setStyle(self.original_style_name)
                app.setPalette(QPalette(self.original_palette))
                app.setStyleSheet(self.original_stylesheet)

        def set_processing_errors(self, processing_errors):
            self.processing_errors = normalize_processing_errors(processing_errors)
            if self.processing_errors:
                self.btn_processing_warnings.setToolTip(
                    format_processing_error_tooltip(len(self.processing_errors))
                )
                self.btn_processing_warnings.setVisible(True)
            else:
                self.btn_processing_warnings.setVisible(False)
                self.btn_processing_warnings.setToolTip("")

        def show_processing_errors_dialog(self):
            if not self.processing_errors:
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("Some Files Were Not Processed")
            dialog.resize(int(self.width() * 0.6), int(self.height() * 0.5))

            layout = QVBoxLayout(dialog)

            summary_label = QLabel(format_processing_error_summary(len(self.processing_errors)))
            summary_label.setWordWrap(True)
            layout.addWidget(summary_label)

            info_label = QLabel(
                "Some files may be corrupted, password protected, unsupported, or otherwise unreadable. "
                "Review the log below for the skipped files and reported reasons."
            )
            info_label.setWordWrap(True)
            layout.addWidget(info_label)

            details_edit = QPlainTextEdit()
            details_edit.setReadOnly(True)
            details_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
            details_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            details_edit.setPlainText(build_processing_error_details(self.processing_errors))
            layout.addWidget(details_edit)

            button_box = QDialogButtonBox(QDialogButtonBox.Ok)
            button_box.accepted.connect(dialog.accept)
            layout.addWidget(button_box)

            dialog.exec()

        def start_search(self):
            pattern = self.inp_pattern.text().strip()
            if not pattern:
                QMessageBox.warning(self, "Missing Pattern", "Please enter a search pattern.")
                return

            path_str = self.inp_path.text().strip() or "."
            fixed_strings = self.chk_fixed_strings.isChecked()
            regex_type = self.combo_regex_type.currentData()
            posix_ere = regex_type is True
            regex_enabled = regex_type is not None
            column_mode = self.combo_search_mode.currentData()
            separator = "\t"
            if self.chk_custom_separator.isChecked():
                separator = self.inp_sep.text()
                if separator == "\\t":
                    separator = "\t"

            opts = build_search_options(
                pattern,
                fixed_strings=fixed_strings,
                regex_enabled=regex_enabled,
                posix_ere=posix_ere,
                ignore_case=self.chk_ignore_case.isChecked(),
                word_regexp=self.chk_word_regexp.isChecked(),
                recursive=self.chk_recursive.isChecked(),
                jobs=self.combo_jobs.currentData(),
                count=self.chk_count.isChecked(),
                with_filename=True,
                with_sheetname=True,
                files_with_match=self.chk_lmatch.isChecked(),
                files_without_match=self.chk_lwithout.isChecked(),
                column_mode=column_mode,
                separator=separator,
                debug=False,
            )

            self.btn_search.setEnabled(False)
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.table.setRowCount(0)
            self.reset_results_table_layout()
            self.table.verticalScrollBar().setValue(0)
            self.search_start_time = perf_counter()
            self.lbl_elapsed_time.setText("")
            self.set_processing_errors([])
            self.status_bar.showMessage(f"Searching for '{pattern}' in {path_str}...")

            # Run search in background thread
            self.worker = SearchWorkerThread(path_str, self.chk_recursive.isChecked(), opts)
            self.worker.result_signal.connect(self.on_search_finished)
            self.worker.progress_signal.connect(self.on_search_progress)
            self.worker.start()

        def on_search_progress(self, value, maximum, msg):
            self.progress_bar.setRange(0, maximum)
            self.progress_bar.setValue(value)
            self.status_bar.showMessage(msg)

        def on_search_finished(self, data):
            self.btn_search.setEnabled(True)
            self.progress_bar.setValue(self.progress_bar.maximum())
            self.progress_bar.setVisible(False)

            elapsed_time = None
            if self.search_start_time is not None:
                elapsed_time = perf_counter() - self.search_start_time
                self.search_start_time = None
                self.lbl_elapsed_time.setText(f"Time: {format_elapsed_time(elapsed_time)}")

            if "error" in data:
                self.set_processing_errors([])
                QMessageBox.critical(self, "Engine Error", data["error"])
                self.status_bar.showMessage("Error: " + data["error"])
                return

            self.set_processing_errors(data.get("processing_errors", []))
            results = data["results"]
            self.table.setRowCount(len(results))
            for row_idx, (file_name, sheet_name, content) in enumerate(results):
                self.table.setItem(row_idx, 0, QTableWidgetItem(file_name))
                self.table.setItem(row_idx, 1, QTableWidgetItem(sheet_name))
                self.table.setItem(row_idx, 2, QTableWidgetItem(content))

            if results:
                self.fit_results_table_to_contents()
            else:
                self.reset_results_table_layout()
            self.table.verticalScrollBar().setValue(0)
            self.status_bar.showMessage(data["status_message"])

        def export_csv(self):
            row_count = self.table.rowCount()
            if row_count == 0:
                QMessageBox.warning(self, "No Results", "There are no search results to export.")
                return

            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Results to CSV", "tdsearch_export.csv", "CSV Files (*.csv)"
            )
            if not file_path:
                return

            try:
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["File", "Sheet / Position", "Matched Row / Line"])
                    for row in range(row_count):
                        file_item = self.table.item(row, 0)
                        sheet_item = self.table.item(row, 1)
                        content_item = self.table.item(row, 2)
                        writer.writerow([
                            file_item.text() if file_item else "",
                            sheet_item.text() if sheet_item else "",
                            content_item.text() if content_item else "",
                        ])

                QMessageBox.information(
                    self, "Export Successful", f"Successfully exported {row_count} rows to:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{e}")


def main():
    if not PYSIDE_AVAILABLE:
        print(
            "Error: 'PySide6' is required for TDsearch GUI.\n"
            "Please install it using:\n"
            "    pip install PySide6",
            file=sys.stderr,
        )
        sys.exit(1)

    app = QApplication(sys.argv)
    window = TDSearchGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
