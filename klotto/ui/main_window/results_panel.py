from typing import Callable, List

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from klotto.core.analysis import NumberAnalyzer
from klotto.ui.theme import ThemeManager
from klotto.ui.widgets import ResultRow


class ResultsPanel(QFrame):
    cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.apply_theme()

    def _setup_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)

        header = QHBoxLayout()
        header.setContentsMargins(15, 10, 15, 5)
        header.addWidget(QLabel("생성 결과"))
        header.addStretch()

        self.clear_btn = QPushButton("초기화")
        self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.setFixedSize(60, 26)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._handle_clear_clicked)
        header.addWidget(self.clear_btn)
        layout.addLayout(header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")

        self.results_container = QWidget()
        self.results_container.setStyleSheet("background: transparent;")
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.results_layout.setSpacing(0)
        self.results_layout.setContentsMargins(0, 0, 0, 0)

        self.placeholder_label = QLabel("번호 생성하기 버튼을 눌러주세요.\n행운의 번호가 기다리고 있습니다!")
        self.placeholder_label.setObjectName("placeholderLabel")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_layout.addWidget(self.placeholder_label)

        self.scroll_area.setWidget(self.results_container)
        layout.addWidget(self.scroll_area)

    def apply_theme(self):
        theme = ThemeManager.get_theme()
        self.setStyleSheet(
            f"background-color: {theme['bg_secondary']}; border-radius: 12px; border: 1px solid {theme['border']};"
        )

    def display_results(
        self,
        sets: List[List[int]],
        *,
        start_index: int,
        winning_numbers: List[int],
        bonus: int,
        favorite_callback: Callable[[List[int]], None],
        copy_callback: Callable[[List[int]], None],
    ):
        self.placeholder_label.setVisible(False)

        if self.results_layout.count() > 1:
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet(f"background-color: {ThemeManager.get_theme()['border_light']}; margin: 10px 0;")
            self.results_layout.addWidget(line)

        self.results_container.setUpdatesEnabled(False)
        try:
            for offset, numbers in enumerate(sets):
                analysis = NumberAnalyzer.analyze(numbers)
                matched_info = NumberAnalyzer.compare_with_winning(numbers, winning_numbers, bonus)
                matched_numbers = matched_info.get("matched", [])

                row = ResultRow(start_index + offset + 1, numbers, analysis, matched_numbers)
                row.favoriteClicked.connect(favorite_callback)
                row.copyClicked.connect(copy_callback)
                self.results_layout.addWidget(row)
        finally:
            self.results_container.setUpdatesEnabled(True)
            self.results_container.update()

        QTimer.singleShot(100, self._scroll_results_to_bottom)

    def clear_results(self):
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        self.placeholder_label = QLabel("번호 생성하기 버튼을 눌러주세요.\n행운의 번호가 기다리고 있습니다!")
        self.placeholder_label.setObjectName("placeholderLabel")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_layout.addWidget(self.placeholder_label)

    def _scroll_results_to_bottom(self):
        bar = self.scroll_area.verticalScrollBar()
        if bar is not None:
            bar.setValue(bar.maximum())

    def _handle_clear_clicked(self):
        self.clear_results()
        self.cleared.emit()
