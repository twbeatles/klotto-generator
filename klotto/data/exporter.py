import json
from typing import List, Dict, Optional
from klotto.utils import logger

# ============================================================
# 데이터 내보내기/가져오기
# ============================================================
class DataExporter:
    """데이터 내보내기/가져오기"""
    
    @staticmethod
    def export_to_csv(data: List[Dict], filepath: str, data_type: str = 'favorites'):
        """CSV로 내보내기"""
        try:
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                if data_type == 'favorites':
                    f.write("번호1,번호2,번호3,번호4,번호5,번호6,메모,생성일\n")
                    for item in data:
                        nums = item.get('numbers', [])
                        memo = item.get('memo', '')
                        created = item.get('created_at', '')
                        f.write(f"{','.join(map(str, nums))},{memo},{created}\n")
                elif data_type == 'history':
                    f.write("번호1,번호2,번호3,번호4,번호5,번호6,생성일\n")
                    for item in data:
                        nums = item.get('numbers', [])
                        created = item.get('created_at', '')
                        f.write(f"{','.join(map(str, nums))},{created}\n")
                elif data_type == 'winning_stats':
                    f.write("회차,번호1,번호2,번호3,번호4,번호5,번호6,보너스\n")
                    for item in data:
                        draw_no = item.get('draw_no', '')
                        nums = item.get('numbers', [])
                        bonus = item.get('bonus', '')
                        f.write(f"{draw_no},{','.join(map(str, nums))},{bonus}\n")
            
            logger.info(f"Exported {len(data)} items to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            return False
    
    @staticmethod
    def export_to_json(data: List[Dict], filepath: str):
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
    def import_from_json(filepath: str) -> Optional[List[Dict]]:
        """JSON에서 가져오기"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Imported {len(data)} items from {filepath}")
            return data
        except Exception as e:
            logger.error(f"Failed to import JSON: {e}")
            return None
