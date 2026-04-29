from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from klotto.core.strategy_catalog import create_default_strategy_request, list_strategies


class StrategyRequestEditor(QGroupBox):
    strategiesChanged = pyqtSignal()

    def __init__(self, scope: str, title: str = '전략 설정', parent: Optional[QWidget] = None):
        super().__init__(title, parent)
        self.scope = scope
        self._setup_ui()
        self.reload_strategies()
        self.apply_request(create_default_strategy_request('ensemble_weighted'))

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.experimental_chk = QCheckBox('실험 전략 포함')
        self.experimental_chk.toggled.connect(self.reload_strategies)
        header.addWidget(self.experimental_chk)
        header.addStretch()
        layout.addLayout(header)

        form = QFormLayout()
        self.strategy_combo = QComboBox()
        form.addRow('전략', self.strategy_combo)

        self.lookback_spin = QSpinBox()
        self.lookback_spin.setRange(5, 120)
        form.addRow('최근 회차', self.lookback_spin)

        self.simulation_spin = QSpinBox()
        self.simulation_spin.setRange(1000, 20000)
        self.simulation_spin.setSingleStep(500)
        form.addRow('시뮬레이션 수', self.simulation_spin)

        self.wheel_pool_spin = QSpinBox()
        self.wheel_pool_spin.setRange(0, 20)
        self.wheel_pool_spin.setSpecialValueText('사용 안 함')
        form.addRow('휠 후보군', self.wheel_pool_spin)

        self.wheel_guarantee_spin = QSpinBox()
        self.wheel_guarantee_spin.setRange(0, 5)
        self.wheel_guarantee_spin.setSpecialValueText('사용 안 함')
        form.addRow('휠 보장수', self.wheel_guarantee_spin)

        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText('비워두면 랜덤')
        form.addRow('시드', self.seed_edit)

        self.payout_combo = QComboBox()
        self.payout_combo.addItem('동적 1등 우선', 'hybrid_dynamic_first')
        self.payout_combo.addItem('고정 상금 빠른 평가', 'fast_fixed')
        form.addRow('정산 모드', self.payout_combo)

        self.odd_min_spin, self.odd_max_spin = self._pair_spins(0, 6)
        form.addRow('홀수 수', self._pair_widget(self.odd_min_spin, self.odd_max_spin))

        self.high_min_spin, self.high_max_spin = self._pair_spins(0, 6)
        form.addRow('고수(24+) 수', self._pair_widget(self.high_min_spin, self.high_max_spin))

        self.sum_min_spin, self.sum_max_spin = self._pair_spins(0, 300)
        form.addRow('합계 범위', self._pair_widget(self.sum_min_spin, self.sum_max_spin))

        self.ac_min_spin, self.ac_max_spin = self._pair_spins(0, 20)
        form.addRow('AC 범위', self._pair_widget(self.ac_min_spin, self.ac_max_spin))

        self.max_consecutive_spin = QSpinBox()
        self.max_consecutive_spin.setRange(-1, 5)
        self.max_consecutive_spin.setSpecialValueText('제한 없음')
        self.max_consecutive_spin.setValue(-1)
        form.addRow('최대 연속쌍', self.max_consecutive_spin)

        self.end_digit_spin = QSpinBox()
        self.end_digit_spin.setRange(-1, 6)
        self.end_digit_spin.setSpecialValueText('제한 없음')
        self.end_digit_spin.setValue(-1)
        form.addRow('최소 끝수 종류', self.end_digit_spin)

        layout.addLayout(form)

    def _pair_spins(self, min_value: int, max_value: int) -> tuple[QSpinBox, QSpinBox]:
        left = QSpinBox()
        left.setRange(-1, max_value)
        left.setSpecialValueText('미사용')
        left.setValue(-1)
        right = QSpinBox()
        right.setRange(-1, max_value)
        right.setSpecialValueText('미사용')
        right.setValue(-1)
        return left, right

    def _pair_widget(self, left: QSpinBox, right: QSpinBox) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(left)
        row.addWidget(QLabel('~'))
        row.addWidget(right)
        return widget

    def reload_strategies(self):
        current = self.strategy_combo.currentData()
        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        for meta in list_strategies(include_experimental=self.experimental_chk.isChecked(), scope=self.scope):
            label = f"{meta['label']} ({meta['id']})"
            self.strategy_combo.addItem(label, meta['id'])
        index = max(0, self.strategy_combo.findData(current))
        self.strategy_combo.setCurrentIndex(index)
        self.strategy_combo.blockSignals(False)
        self.strategiesChanged.emit()

    def _read_pair(self, left: QSpinBox, right: QSpinBox) -> Optional[list[int]]:
        if left.value() < 0 or right.value() < 0:
            return None
        values = sorted([left.value(), right.value()])
        return values

    def build_request(self) -> Dict[str, Any]:
        seed_text = self.seed_edit.text().strip()
        seed_value = int(seed_text) if seed_text and seed_text.lstrip('-').isdigit() else None
        return {
            'strategyId': str(self.strategy_combo.currentData() or 'ensemble_weighted'),
            'params': {
                'lookbackWindow': self.lookback_spin.value(),
                'simulationCount': self.simulation_spin.value(),
                'wheelPoolSize': self.wheel_pool_spin.value() or None,
                'wheelGuarantee': self.wheel_guarantee_spin.value() or None,
                'seed': seed_value,
                'payoutMode': str(self.payout_combo.currentData() or 'hybrid_dynamic_first'),
            },
            'filters': {
                'oddEven': self._read_pair(self.odd_min_spin, self.odd_max_spin),
                'highLow': self._read_pair(self.high_min_spin, self.high_max_spin),
                'sumRange': self._read_pair(self.sum_min_spin, self.sum_max_spin),
                'acRange': self._read_pair(self.ac_min_spin, self.ac_max_spin),
                'maxConsecutivePairs': None if self.max_consecutive_spin.value() < 0 else self.max_consecutive_spin.value(),
                'endDigitUniqueMin': None if self.end_digit_spin.value() < 0 else self.end_digit_spin.value(),
            },
        }

    def apply_request(self, request: Dict[str, Any]):
        current = create_default_strategy_request(str(request.get('strategyId') or 'ensemble_weighted'))
        current['params'].update(request.get('params') or {})
        current['filters'].update(request.get('filters') or {})
        strategy_id = str(current.get('strategyId') or 'ensemble_weighted')
        index = self.strategy_combo.findData(strategy_id)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        self._set_spin_value(self.lookback_spin, current['params'].get('lookbackWindow'), 20)
        self._set_spin_value(self.simulation_spin, current['params'].get('simulationCount'), 5000)
        self._set_spin_value(self.wheel_pool_spin, current['params'].get('wheelPoolSize'), 0)
        self._set_spin_value(self.wheel_guarantee_spin, current['params'].get('wheelGuarantee'), 0)
        self.seed_edit.setText('' if current['params'].get('seed') is None else str(current['params'].get('seed')))
        payout_index = self.payout_combo.findData(str(current['params'].get('payoutMode') or 'hybrid_dynamic_first'))
        self.payout_combo.setCurrentIndex(max(0, payout_index))
        self._apply_pair(self.odd_min_spin, self.odd_max_spin, current['filters'].get('oddEven'))
        self._apply_pair(self.high_min_spin, self.high_max_spin, current['filters'].get('highLow'))
        self._apply_pair(self.sum_min_spin, self.sum_max_spin, current['filters'].get('sumRange'))
        self._apply_pair(self.ac_min_spin, self.ac_max_spin, current['filters'].get('acRange'))
        self._set_spin_value(self.max_consecutive_spin, current['filters'].get('maxConsecutivePairs'), -1)
        self._set_spin_value(self.end_digit_spin, current['filters'].get('endDigitUniqueMin'), -1)

    def _apply_pair(self, left: QSpinBox, right: QSpinBox, values: Any):
        if isinstance(values, (list, tuple)) and len(values) >= 2:
            self._set_spin_value(left, values[0], -1)
            self._set_spin_value(right, values[1], -1)
        else:
            left.setValue(-1)
            right.setValue(-1)

    def _set_spin_value(self, spin: QSpinBox, value: Any, fallback: int):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = fallback
        spin.setValue(max(spin.minimum(), min(spin.maximum(), parsed)))
