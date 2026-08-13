"""Reusable day/range/all-date Excel export dialog for TPS pages."""

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QLabel, QMessageBox, QVBoxLayout,
)

from services.excel_report_exporter import ExcelReportExporter, REPORTS


class ExcelExportDialog(QDialog):
    def __init__(self, parent, database, report_key: str):
        super().__init__(parent)
        self.database = database
        self.report_key = report_key
        definition = next(item for item in REPORTS if item.key == report_key)
        self.setWindowTitle(f"Export {definition.label} to Excel")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Ek din ke liye From aur To same rakhein; period ke liye alag dates select karein."))
        form = QFormLayout()
        self.start = QDateEdit(QDate.currentDate()); self.end = QDateEdit(QDate.currentDate())
        for editor in (self.start, self.end):
            editor.setCalendarPopup(True); editor.setDisplayFormat("dd-MM-yyyy")
        form.addRow("From", self.start); form.addRow("To", self.end)
        self.all_dates = QCheckBox("All available dates")
        self.all_dates.toggled.connect(lambda checked: (self.start.setEnabled(not checked), self.end.setEnabled(not checked)))
        form.addRow("", self.all_dates); layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.export); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    def export(self):
        start = end = None
        if not self.all_dates.isChecked():
            start, end = self._date(self.start.date()), self._date(self.end.date())
            if start > end:
                QMessageBox.warning(self, "Invalid period", "From date cannot be after To date.")
                return
        path, _ = QFileDialog.getSaveFileName(self, "Save Excel Report", f"TPS_{self.report_key}.xlsx", "Excel Workbook (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            counts = ExcelReportExporter(self.database).export(path, [self.report_key], start, end)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Excel export failed", str(error)); return
        QMessageBox.information(self, "Excel export complete", f"{sum(counts.values())} record(s) exported.\n\n{path}")
        self.accept()


def open_excel_export(parent, database, report_key: str):
    ExcelExportDialog(parent, database, report_key).exec()
