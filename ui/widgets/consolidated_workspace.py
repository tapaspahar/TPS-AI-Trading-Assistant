"""Small tabbed shell used to consolidate related TPS workspaces."""

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget


class ConsolidatedWorkspace(QWidget):
    """Host existing full workspaces as clearly named tabs without losing data."""

    def __init__(self, pages):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        for page, title in pages:
            self.tabs.addTab(page, title)
        layout.addWidget(self.tabs)

    def select_tab(self, index: int):
        if 0 <= int(index) < self.tabs.count():
            self.tabs.setCurrentIndex(int(index))
