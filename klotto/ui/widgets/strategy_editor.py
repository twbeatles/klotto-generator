from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from klotto.core.strategy_catalog import create_default_strategy_request, list_strategies
from klotto.data.app_state import AppStateStore


class StrategyRequestEditor(QGroupBox):
    strategiesChanged = pyqtSignal()
    presetApplied = pyqtSignal(dict)

    def __init__(
        self,
        scope: str,
        title: str = '전략 설정',
        parent: Optional[QWidget] = None,
        *,
        store: Optional[AppStateStore] = None,
    ):
        super().__init__(title, parent)
        self.scope = scope
        self.store = store
        self._setup_ui()
        self.reload_strategies()
        self.reload_presets()
        self.apply_request(create_default_strategy_request('ensemble_weighted'))

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.experimental_chk = QCheckBox('실험 전략 포함')
        self.experimental_chk.toggled.connect(self.reload_strategies)
        header.addWidget(self.experimental_chk)
        header.addStretch()
        layout.addLayout(header)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel('프리셋'))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(180)
        preset_row.addWidget(self.preset_combo, 1)
        self.load_preset_btn = QPushButton('불러오기')
        self.load_preset_btn.clicked.connect(self.load_selected_preset)
        preset_row.addWidget(self.load_preset_btn)
        self.save_preset_btn = QPushButton('저장')
        self.save_preset_btn.clicked.connect(self.save_current_preset)
        preset_row.addWidget(self.save_preset_btn)
        self.delete_preset_btn = QPushButton('삭제')
        self.delete_preset_btn.clicked.connect(self.delete_selected_preset)
        preset_row.addWidget(self.delete_preset_btn)
        layout.addLayout(preset_row)

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

    def reload_presets(self):
        current = self.preset_combo.currentData()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem('프리셋 선택', '')
        presets = self.store.get_strategy_presets(self.scope) if self.store else []
        for preset in presets:
            self.preset_combo.addItem(str(preset.get('name') or '이름 없는 프리셋'), str(preset.get('id') or ''))
        index = self.preset_combo.findData(current)
        self.preset_combo.setCurrentIndex(index if index >= 0 else 0)
        self.preset_combo.blockSignals(False)
        enabled = bool(self.store)
        self.load_preset_btn.setEnabled(enabled)
        self.save_preset_btn.setEnabled(enabled)
        self.delete_preset_btn.setEnabled(enabled and bool(self._get_selected_preset()))

    def _get_selected_preset(self) -> Optional[Dict[str, Any]]:
        if not self.store:
            return None
        preset_id = str(self.preset_combo.currentData() or '').strip()
        if not preset_id:
            return None
        for preset in self.store.get_strategy_presets(self.scope):
            if str(preset.get('id') or '') == preset_id:
                return preset
        return None

    def _read_pair(self, left: QSpinBox, right: QSpinBox) -> Optional[list[int]]:
        if left.value() < 0 or right.value() < 0:
            return None
        return sorted([left.value(), right.value()])

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
        self.lookback_spin.setValue(int(current['params'].get('lookbackWindow') or 20))
        self.simulation_spin.setValue(int(current['params'].get('simulationCount') or 5000))
        self.wheel_pool_spin.setValue(int(current['params'].get('wheelPoolSize') or 0))
        self.wheel_guarantee_spin.setValue(int(current['params'].get('wheelGuarantee') or 0))
        self.seed_edit.setText('' if current['params'].get('seed') is None else str(current['params'].get('seed')))
        payout_index = self.payout_combo.findData(str(current['params'].get('payoutMode') or 'hybrid_dynamic_first'))
        self.payout_combo.setCurrentIndex(max(0, payout_index))
        self._apply_pair(self.odd_min_spin, self.odd_max_spin, current['filters'].get('oddEven'))
        self._apply_pair(self.high_min_spin, self.high_max_spin, current['filters'].get('highLow'))
        self._apply_pair(self.sum_min_spin, self.sum_max_spin, current['filters'].get('sumRange'))
        self._apply_pair(self.ac_min_spin, self.ac_max_spin, current['filters'].get('acRange'))
        self.max_consecutive_spin.setValue(-1 if current['filters'].get('maxConsecutivePairs') is None else int(current['filters']['maxConsecutivePairs']))
        self.end_digit_spin.setValue(-1 if current['filters'].get('endDigitUniqueMin') is None else int(current['filters']['endDigitUniqueMin']))

    def _apply_pair(self, left: QSpinBox, right: QSpinBox, values: Any):
        if isinstance(values, (list, tuple)) and len(values) >= 2:
            left.setValue(int(values[0]))
            right.setValue(int(values[1]))
            return
        left.setValue(-1)
        right.setValue(-1)

    def save_current_preset(self):
        if not self.store:
            return
        name, ok = QInputDialog.getText(self, '전략 프리셋 저장', '프리셋 이름')
        cleaned = name.strip()
        if not ok or not cleaned:
            return
        preset = self.store.save_strategy_preset(self.scope, cleaned, self.build_request())
        if not preset:
            QMessageBox.warning(self, '프리셋 저장', '프리셋을 저장할 수 없습니다.')
            return
        self.reload_presets()
        index = self.preset_combo.findData(str(preset.get('id') or ''))
        self.preset_combo.setCurrentIndex(index if index >= 0 else 0)
        self.delete_preset_btn.setEnabled(True)

    def load_selected_preset(self):
        preset = self._get_selected_preset()
        if not preset:
            return
        self.apply_request(preset.get('request') or {})
        self.delete_preset_btn.setEnabled(True)
        self.presetApplied.emit(dict(preset))

    def delete_selected_preset(self):
        if not self.store:
            return
        preset = self._get_selected_preset()
        if not preset:
            return
        result = QMessageBox.question(self, '프리셋 삭제', f"'{preset.get('name')}' 프리셋을 삭제할까요?")
        if result != QMessageBox.StandardButton.Yes:
            return
        if self.store.delete_strategy_preset(str(preset.get('id') or '')):
            self.reload_presets()
