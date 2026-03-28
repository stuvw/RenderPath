from PyQt5.QtWidgets import (
    QLabel, QWidget, QHBoxLayout, QPushButton, QLineEdit
)

# ══════════════════════════════════════════════════════════════════════════════
# Helper widgets
# ══════════════════════════════════════════════════════════════════════════════

def section_label(text):
    lbl = QLabel(text)
    lbl.setObjectName("SectionLabel")
    return lbl


def file_picker_row(label_text, placeholder, callback):
    """Returns (row_widget, line_edit)."""
    row = QWidget()
    hl  = QHBoxLayout(row)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(4)
    le = QLineEdit()
    le.setPlaceholderText(placeholder)
    btn = QPushButton("···")
    btn.setFixedWidth(32)
    btn.setToolTip(f"Browse for {label_text}")
    btn.clicked.connect(callback)
    hl.addWidget(le)
    hl.addWidget(btn)
    return row, le


def color_button(rgba):
    btn = QPushButton()
    btn.setFixedSize(28, 22)
    r, g, b, a = [int(v * 255) for v in rgba]
    btn.setStyleSheet(
        f"QPushButton {{ background: rgba({r},{g},{b},{a}); border: 1px solid #1e1e2e; }}"
        f"QPushButton:hover {{ border: 1px solid #5c7cfa; }}"
    )
    return btn