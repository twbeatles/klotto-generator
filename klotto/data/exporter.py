import json
import csv
from typing import Any, List, Dict, Optional
from klotto.utils import logger

# ============================================================
# 데이터 내보내기/가져오기
# ============================================================
class DataExporter:
    """데이터 내보내기/가져오기"""

    @staticmethod
    def _normalize_numbers(numbers: Any) -> List[Any]:
        if not isinstance(numbers, (list, tuple)):
            numbers = []

        normalized: List[Any] = []
        for value in list(numbers)[:6]:
            try:
                normalized.append(int(value))
            except (TypeError, ValueError):
                normalized.append('')

        while len(normalized) < 6:
            normalized.append('')

        return normalized
    
    @staticmethod
    def export_to_csv(data: List[Dict[str, Any]], filepath: str, data_type: str = 'favorites'):
        """CSV로 내보내기"""
        try:
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                if data_type == 'favorites':
                    writer.writerow(["번호1", "번호2", "번호3", "번호4", "번호5", "번호6", "메모", "생성일"])
                    for item in data:
                        nums = DataExporter._normalize_numbers(item.get('numbers', []))
                        memo = item.get('memo', '')
                        created = item.get('created_at', '')
                        writer.writerow([*nums, memo, created])
                elif data_type == 'history':
                    writer.writerow(["번호1", "번호2", "번호3", "번호4", "번호5", "번호6", "생성일"])
                    for item in data:
                        nums = DataExporter._normalize_numbers(item.get('numbers', []))
                        created = item.get('created_at', '')
                        writer.writerow([*nums, created])
                elif data_type == 'winning_stats':
                    writer.writerow(["회차", "번호1", "번호2", "번호3", "번호4", "번호5", "번호6", "보너스"])
                    for item in data:
                        draw_no = item.get('draw_no', '')
                        nums = DataExporter._normalize_numbers(item.get('numbers', []))
                        bonus = item.get('bonus', '')
                        writer.writerow([draw_no, *nums, bonus])
            
            logger.info(f"Exported {len(data)} items to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            return False
    
    @staticmethod
    def export_to_json(data: List[Dict[str, Any]], filepath: str):
        """JSON으로 내보내기"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Exported {len(data)} items to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export JSON: {e}")
            return False
    
    @staticmethod
    def import_from_json(filepath: str) -> Optional[List[Dict[str, Any]]]:
        """JSON에서 가져오기"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Imported {len(data)} items from {filepath}")
            return data
        except Exception as e:
            logger.error(f"Failed to import JSON: {e}")
            return None
