from PyQt6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from klotto.config import APP_CONFIG
from klotto.core.generation_service import GenerationRequest
from klotto.core.lotto_rules import parse_number_expression, validate_generation_constraints


class GenerationControlsPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("생성 설정", parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        row1_layout = QHBoxLayout()
        row1_layout.addWidget(QLabel("생성 개수:"))

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, APP_CONFIG["MAX_SETS"])
        self.count_spin.setValue(5)
        self.count_spin.setFixedWidth(60)
        row1_layout.addWidget(self.count_spin)
        row1_layout.addSpacing(20)

        self.consecutive_chk = QCheckBox("연속 번호 제한 (최대 2쌍)")
        self.consecutive_chk.setChecked(True)
        self.consecutive_chk.setToolTip("연속된 번호(예: 1, 2)가 너무 많이 나오지 않도록 제한합니다.")
        row1_layout.addWidget(self.consecutive_chk)
        row1_layout.addStretch()
        layout.addLayout(row1_layout)

        row2_layout = QHBoxLayout()
        self.smart_mode_chk = QCheckBox("스마트 생성 (통계 기반)")
        self.smart_mode_chk.setChecked(True)
        self.smart_mode_chk.toggled.connect(self._toggle_smart_options)
        row2_layout.addWidget(self.smart_mode_chk)

        self.smart_options_widget = QWidget()
        smart_opts_layout = QHBoxLayout(self.smart_options_widget)
        smart_opts_layout.setContentsMargins(0, 0, 0, 0)

        self.prefer_hot_chk = QCheckBox("핫 넘버 선호")
        self.prefer_hot_chk.setChecked(True)
        self.prefer_hot_chk.setToolTip("최근 자주 나온 번호에 가중치를 둡니다.")
        smart_opts_layout.addWidget(self.prefer_hot_chk)

        self.balance_chk = QCheckBox("홀짝 균형")
        self.balance_chk.setChecked(True)
        self.balance_chk.setToolTip("홀수와 짝수의 비율이 적절하도록 조정합니다.")
        smart_opts_layout.addWidget(self.balance_chk)

        self.smart_options_widget.setEnabled(True)
        row2_layout.addWidget(self.smart_options_widget)
        row2_layout.addStretch()
        layout.addLayout(row2_layout)

        row3_layout = QGridLayout()
        row3_layout.setHorizontalSpacing(12)
        row3_layout.setVerticalSpacing(6)

        fixed_label = QLabel("고정수:")
        self.fixed_nums_input = QLineEdit()
        self.fixed_nums_input.setPlaceholderText("예: 1, 3, 5-8")
        self.fixed_nums_input.setToolTip("쉼표로 구분하고 범위는 1-10 형식으로 입력하세요.")

        exclude_label = QLabel("제외수:")
        self.exclude_nums_input = QLineEdit()
        self.exclude_nums_input.setPlaceholderText("예: 7-10, 22")
        self.exclude_nums_input.setToolTip("쉼표로 구분하고 범위는 1-10 형식으로 입력하세요.")

        row3_layout.addWidget(fixed_label, 0, 0)
        row3_layout.addWidget(self.fixed_nums_input, 0, 1)
        row3_layout.addWidget(exclude_label, 1, 0)
        row3_layout.addWidget(self.exclude_nums_input, 1, 1)
        row3_layout.setColumnStretch(1, 1)
        layout.addLayout(row3_layout)

    def _toggle_smart_options(self, checked: bool):
        self.smart_options_widget.setEnabled(checked)

    def build_request(self, *, max_generate_retries: int) -> GenerationRequest:
        fixed_nums = parse_number_expression(self.fixed_nums_input.text(), "고정수")
        exclude_nums = parse_number_expression(self.exclude_nums_input.text(), "제외수")

        validation_error = validate_generation_constraints(
            fixed_nums,
            exclude_nums,
            max_fixed_nums=int(APP_CONFIG["MAX_FIXED_NUMS"]),
        )
        if validation_error:
            raise ValueError(validation_error)

        return GenerationRequest(
            count=self.count_spin.value(),
            use_smart=self.smart_mode_chk.isChecked(),
            prefer_hot=self.prefer_hot_chk.isChecked(),
            balance_mode=self.balance_chk.isChecked(),
            limit_consecutive=self.consecutive_chk.isChecked(),
            fixed_nums=fixed_nums,
            exclude_nums=exclude_nums,
            max_generate_retries=max_generate_retries,
        )
