"""
PyQt6 QSS Stylesheet Generator with Dark & Light Mode Tokens.
"""

from __future__ import annotations


def get_qt_dialog_stylesheet(dark: bool) -> str:
    """Generate the full Qt stylesheet customized for dark or light theme."""
    tokens = {
        "bg_dialog": "#0f172a" if dark else "#f8fafc",
        "bg_card": "#1e293b" if dark else "#ffffff",
        "border_card": "#334155" if dark else "#e2e8f0",
        "text_title": "#f8fafc" if dark else "#0f172a",
        "text_body": "#cbd5e1" if dark else "#334155",
        "text_muted": "#94a3b8" if dark else "#64748b",
        "bg_input": "#0f172a" if dark else "#ffffff",
        "border_input": "#475569" if dark else "#cbd5e1",
        "text_input": "#f8fafc" if dark else "#0f172a",
        "bg_btn": "#1e293b" if dark else "#f1f5f9",
        "border_btn": "#475569" if dark else "#cbd5e1",
        "text_btn": "#f8fafc" if dark else "#1e293b",
        "bg_btn_hover": "#334155" if dark else "#e2e8f0",
        "border_btn_hover": "#64748b" if dark else "#94a3b8",
        "bg_btn_paste": "#1e1b4b" if dark else "#e0e7ff",
        "border_btn_paste": "#4338ca" if dark else "#c7d2fe",
        "text_btn_paste": "#c7d2fe" if dark else "#3730a3",
        "bg_btn_paste_hover": "#312e81" if dark else "#c7d2fe",
        "bg_btn_save": "#059669" if dark else "#10b981",
        "border_btn_save": "#10b981" if dark else "#059669",
        "bg_btn_save_hover": "#10b981" if dark else "#059669",
        "bg_btn_remove": "#450a0a" if dark else "#fee2e2",
        "border_btn_remove": "#7f1d1d" if dark else "#fca5a5",
        "text_btn_remove": "#fca5a5" if dark else "#b91c1c",
        "bg_btn_remove_hover": "#5c1313" if dark else "#fecaca",
        "scrollbar_handle": "#475569" if dark else "#cbd5e1",
        "scrollbar_hover": "#64748b" if dark else "#94a3b8",
    }
    return """
        QDialog {
            background-color: %(bg_dialog)s;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Ubuntu, Cantarell, sans-serif;
        }
        QScrollArea {
            background-color: transparent;
            border: none;
        }
        QWidget#scrollContent {
            background-color: transparent;
        }
        QGroupBox {
            background-color: %(bg_card)s;
            border: 1px solid %(border_card)s;
            border-radius: 8px;
            margin-top: 14px;
            padding: 12px 14px 14px 14px;
            font-weight: bold;
            color: %(text_title)s;
            font-size: 13px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 6px;
            color: %(text_title)s;
            background-color: %(bg_card)s;
            border-radius: 3px;
        }
        QLabel {
            color: %(text_body)s;
            font-size: 13px;
        }
        QLabel#lblHeaderTitle {
            font-size: 18px;
            font-weight: bold;
            color: %(text_title)s;
        }
        QLabel#lblHeaderSub {
            font-size: 12px;
            color: %(text_muted)s;
        }
        QLabel#lblQuickDesc {
            font-size: 11px;
            color: %(text_muted)s;
        }
        QLineEdit {
            background-color: %(bg_input)s;
            border: 1px solid %(border_input)s;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 13px;
            color: %(text_input)s;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            min-height: 24px;
            max-height: 24px;
        }
        QLineEdit:focus {
            border: 1.5px solid #3b82f6;
        }
        QComboBox {
            background-color: %(bg_input)s;
            border: 1px solid %(border_input)s;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 13px;
            color: %(text_input)s;
            min-height: 24px;
            max-height: 24px;
        }
        QComboBox:focus {
            border: 1.5px solid #3b82f6;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: none;
        }
        QComboBox QAbstractItemView {
            background-color: %(bg_card)s;
            border: 1px solid %(border_card)s;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            color: %(text_input)s;
            padding: 4px;
        }
        QPushButton {
            border-radius: 6px;
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 600;
            border: 1px solid %(border_btn)s;
            background-color: %(bg_btn)s;
            color: %(text_btn)s;
            min-height: 24px;
            max-height: 24px;
        }
        QPushButton:hover {
            background-color: %(bg_btn_hover)s;
            border-color: %(border_btn_hover)s;
        }
        QPushButton#btnPaste {
            background-color: %(bg_btn_paste)s;
            border: 1px solid %(border_btn_paste)s;
            color: %(text_btn_paste)s;
        }
        QPushButton#btnPaste:hover {
            background-color: %(bg_btn_paste_hover)s;
        }
        QPushButton#btnSave {
            background-color: %(bg_btn_save)s;
            border: 1px solid %(border_btn_save)s;
            color: #ffffff;
        }
        QPushButton#btnSave:hover {
            background-color: %(bg_btn_save_hover)s;
        }
        QPushButton#btnRemove {
            background-color: %(bg_btn_remove)s;
            border: 1px solid %(border_btn_remove)s;
            color: %(text_btn_remove)s;
        }
        QPushButton#btnRemove:hover {
            background-color: %(bg_btn_remove_hover)s;
        }
        QScrollBar:vertical {
            border: none;
            background-color: transparent;
            width: 8px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background-color: %(scrollbar_handle)s;
            min-height: 24px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: %(scrollbar_hover)s;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
        QMessageBox {
            background-color: %(bg_dialog)s;
        }
        QMessageBox QLabel {
            color: %(text_title)s;
        }
    """ % tokens
