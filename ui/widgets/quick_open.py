from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QVBoxLayout


class QuickOpenDialog(QDialog):
    """Keyboard-first page finder for the compact TPS workspace."""

    route_selected = Signal(int)

    def __init__(self, routes, parent=None):
        super().__init__(parent)
        self.routes = tuple(routes)
        self.setWindowTitle("Quick Open — TPS Pages")
        self.setMinimumSize(560, 430)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Page name type karein — Enter se open hoga (Ctrl+K)"))
        self.search = QLineEdit(); self.search.setPlaceholderText("Example: OI Flow, Strategy Trades, Settings")
        self.list = QListWidget()
        layout.addWidget(self.search); layout.addWidget(self.list)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._activate)
        self.list.itemActivated.connect(lambda _item: self._activate())
        self._filter("")

    def _filter(self, text):
        query = str(text or "").strip().casefold()
        self.list.clear()
        for label, route, keywords in self.routes:
            if not query or query in f"{label} {keywords}".casefold():
                self.list.addItem(label)
                self.list.item(self.list.count() - 1).setData(Qt.UserRole, int(route))
        if self.list.count(): self.list.setCurrentRow(0)

    def _activate(self):
        item = self.list.currentItem()
        if item is None: return
        self.route_selected.emit(int(item.data(Qt.UserRole)))
        self.accept()

    def open_focused(self):
        self.search.clear(); self.show(); self.raise_(); self.activateWindow(); self.search.setFocus()
