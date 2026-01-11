import json
import datetime
import os
from typing import List, Dict
from klotto.config import APP_CONFIG
from klotto.utils import logger

# ============================================================
# 즐겨찾기 관리
# ============================================================
class FavoritesManager:
    """즐겨찾기 번호 관리"""
    
    def __init__(self):
        self.favorites_file = APP_CONFIG['FAVORITES_FILE']
        self.favorites: List[Dict] = []
        self._load()
    
    def _load(self):
        """파일에서 즐겨찾기 로드"""
        try:
            if self.favorites_file and self.favorites_file.exists():
                with open(self.favorites_file, 'r', encoding='utf-8') as f:
                    self.favorites = json.load(f)
                logger.info(f"Loaded {len(self.favorites)} favorites")
        except Exception as e:
            logger.error(f"Failed to load favorites: {e}")
            self.favorites = []
    
    def _save(self):
        """즐겨찾기를 파일에 저장 (Atomic)"""
        if not self.favorites_file:
            return

        try:
            self.favorites_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.favorites_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=2)
            
            if self.favorites_file.exists():
                os.replace(temp_file, self.favorites_file)
            else:
                os.rename(temp_file, self.favorites_file)
            logger.info(f"Saved {len(self.favorites)} favorites")
        except Exception as e:
            logger.error(f"Failed to save favorites: {e}")
            try:
                if 'temp_file' in locals() and temp_file.exists():
                    temp_file.unlink()
            except: pass
    
    def add(self, numbers: List[int], memo: str = "") -> bool:
        """즐겨찾기 추가"""
        if any(f['numbers'] == numbers for f in self.favorites):
            return False
        
        self.favorites.append({
            'numbers': numbers,
            'memo': memo,
            'created_at': datetime.datetime.now().isoformat()
        })
        self._save()
        return True
    
    def remove(self, index: int):
        """즐겨찾기 삭제"""
        if 0 <= index < len(self.favorites):
            del self.favorites[index]
            self._save()
    
    def get_all(self) -> List[Dict]:
        return self.favorites.copy()
