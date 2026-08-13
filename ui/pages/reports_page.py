from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from services.excel_report_exporter import ExcelReportExporter, REPORTS


class ReportsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.db = Database()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Journal Report"))
        self.report = QLabel()
        self.report.setWordWrap(True)
        layout.addWidget(self.report)
        refresh = QPushButton("Refresh Report")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        export = QPushButton("Export Journal to CSV")
        export.clicked.connect(self.export_csv)
        layout.addWidget(export)

        excel_box = QGroupBox("Excel Report Center — date-wise and period-wise export")
        excel_layout = QVBoxLayout(excel_box)
        form = QFormLayout()
        self.report_type = QComboBox()
        self.report_type.addItem("All TPS Reports (one multi-sheet workbook)", "__all__")
        for definition in REPORTS:
            self.report_type.addItem(definition.label, definition.key)
        form.addRow("Report", self.report_type)
        date_row = QHBoxLayout()
        self.start_date = QDateEdit(QDate.currentDate())
        self.end_date = QDateEdit(QDate.currentDate())
        for editor in (self.start_date, self.end_date):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd-MM-yyyy")
        date_row.addWidget(QLabel("From")); date_row.addWidget(self.start_date)
        date_row.addWidget(QLabel("To")); date_row.addWidget(self.end_date)
        form.addRow("Period", date_row)
        self.all_dates = QCheckBox("All available dates")
        self.all_dates.toggled.connect(self._toggle_dates)
        form.addRow("", self.all_dates)
        excel_layout.addLayout(form)
        quick = QHBoxLayout()
        today = QPushButton("Today")
        today.clicked.connect(self._select_today)
        last_seven = QPushButton("Last 7 Days")
        last_seven.clicked.connect(self._select_last_seven)
        export_excel = QPushButton("Export Selected Report to Excel")
        export_excel.clicked.connect(self.export_excel)
        quick.addWidget(today); quick.addWidget(last_seven); quick.addWidget(export_excel)
        excel_layout.addLayout(quick)
        excel_layout.addWidget(QLabel("Tip: same From and To date exports one day; a wider period exports an inclusive date range."))
        layout.addWidget(excel_box)
        layout.addStretch()
        self.refresh()

    def refresh(self):
        summary = self.db.get_summary()
        outcomes = self.db.get_ai_outcome_report()
        validation = self.db.get_validation_report()
        versions = self.db.get_rule_version_report()
        version_text = "\n".join(
            f"• {row['rule_version']}: {row['samples']} closed | target {row['target_hits']} | stop {row['stoploss_hits']} | net P&L ₹{row['net_pnl']:,.2f}"
            for row in versions
        ) or "No closed trade samples recorded yet."
        self.report.setText(
            f"Recorded trades: {summary['trades']}\n"
            f"Net P&L: ₹{summary['pnl']:,.2f}\n"
            f"Winning trades: {summary['winning_trades']}\n"
            f"Win rate: {summary['win_rate']:.1f}%\n"
            f"Average AI confidence: {summary['average_ai']:.1f}%\n\n"
            f"AI Outcome Review\n"
            f"Open trades: {outcomes['open_trades']} | Closed trades: {outcomes['closed_trades']}\n"
            f"Target hit: {outcomes['target_hits']} | Stop loss hit: {outcomes['stoploss_hits']} | Manual exit: {outcomes['manual_exits']}\n"
            f"Target vs stop-loss accuracy: {outcomes['target_vs_stop_accuracy']:.1f}%\n"
            f"\nValidated Setup Evidence\n"
            f"Fully-confirmed closed samples: {validation['samples']} | Target hits: {validation['target_hits']} | Stop losses: {validation['stoploss_hits']}\n"
            f"Observed target-vs-stop rate: {validation['accuracy']:.1f}%\n"
            f"Evidence status: {validation['status']}\n"
            f"\nRule-Version Review\n{version_text}\n"
            "A stop loss does not prove the AI was wrong; review the chart, timing, volatility, news, liquidity and execution before changing the rules."
       )

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Trade Journal", "trade_journal.csv", "CSV files (*.csv)")
        if not path:
            return
        try:
            count = self.db.export_csv(path)
        except OSError as error:
            QMessageBox.critical(self, "Export failed", str(error))
            return
        QMessageBox.information(self, "Export complete", f"Exported {count} trade(s) to CSV.")

    def _toggle_dates(self, checked):
        self.start_date.setEnabled(not checked)
        self.end_date.setEnabled(not checked)

    def _select_today(self):
        self.all_dates.setChecked(False)
        self.start_date.setDate(QDate.currentDate())
        self.end_date.setDate(QDate.currentDate())

    def _select_last_seven(self):
        self.all_dates.setChecked(False)
        self.start_date.setDate(QDate.currentDate().addDays(-6))
        self.end_date.setDate(QDate.currentDate())

    @staticmethod
    def _python_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    def export_excel(self):
        key = self.report_type.currentData()
        keys = None if key == "__all__" else [key]
        start = end = None
        if not self.all_dates.isChecked():
            start = self._python_date(self.start_date.date())
            end = self._python_date(self.end_date.date())
            if start > end:
                QMessageBox.warning(self, "Invalid period", "From date cannot be after To date.")
                return
        default_name = "TPS_All_Reports.xlsx" if keys is None else f"TPS_{key}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Export TPS Excel Report", default_name, "Excel Workbook (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            counts = ExcelReportExporter(self.db).export(path, keys, start, end)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Excel export failed", str(error))
            return
        total = sum(counts.values())
        QMessageBox.information(
            self, "Excel export complete",
            f"{len(counts)} report sheet(s) and {total} record(s) exported successfully.\n\n{path}",
        )
