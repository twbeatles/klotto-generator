import json
import datetime
import os
from typing import List, Dict, Optional, Tuple, Set
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
        self._favorite_keys: Set[Tuple[int, ...]] = set()
        self._load()

    @staticmethod
    def _numbers_to_key(numbers: List[int], validate: bool = False) -> Optional[Tuple[int, ...]]:
        try:
            normalized = tuple(sorted(int(n) for n in numbers))
        except (TypeError, ValueError):
            return None

        if not validate:
            return normalized

        if len(normalized) != 6 or len(set(normalized)) != 6:
            return None
        if any(n < 1 or n > 45 for n in normalized):
            return None
        return normalized

    def _rebuild_index(self):
        normalized_favorites: List[Dict] = []
        self._favorite_keys.clear()

        for fav in self.favorites:
            if not isinstance(fav, dict):
                continue

            key = self._numbers_to_key(fav.get('numbers', []), validate=True)
            if not key or key in self._favorite_keys:
                continue

            memo = fav.get('memo', '')
            if not isinstance(memo, str):
                memo = str(memo)

            created_at = fav.get('created_at')
            if not isinstance(created_at, str):
                created_at = datetime.datetime.now().isoformat()

            normalized_favorites.append({
                'numbers': list(key),
                'memo': memo,
                'created_at': created_at
            })
            self._favorite_keys.add(key)

        self.favorites = normalized_favorites
    
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
        finally:
            self._rebuild_index()
    
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
    
    def add(self, numbers: List[int], memo: str = "", save: bool = True) -> bool:
        """즐겨찾기 추가"""
        key = self._numbers_to_key(numbers, validate=True)
        if not key:
            return False

        if key in self._favorite_keys:
            return False

        if not isinstance(memo, str):
            memo = str(memo)

        self.favorites.append({
            'numbers': list(key),
            'memo': memo,
            'created_at': datetime.datetime.now().isoformat()
        })
        self._favorite_keys.add(key)

        if save:
            self._save()
        return True

    def add_many(self, items: List[Dict]) -> int:
        """여러 즐겨찾기 항목 추가 (단일 파일 저장)"""
        added_count = 0
        changed = False

        for item in items:
            if not isinstance(item, dict):
                continue
            numbers = item.get('numbers', [])
            memo = item.get('memo', '')
            if self.add(numbers, memo=memo, save=False):
                added_count += 1
                changed = True

        if changed:
            self._save()

        return added_count
    
    def remove(self, index: int):
        """즐겨찾기 삭제"""
        if 0 <= index < len(self.favorites):
            removed = self.favorites.pop(index)
            key = self._numbers_to_key(removed.get('numbers', []))
            if key:
                self._favorite_keys.discard(key)
            self._save()
    
    def get_all(self) -> List[Dict]:
        return self.favorites.copy()
