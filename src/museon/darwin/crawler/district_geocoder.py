"""
district_geocoder.py — 台灣 370 個鄉鎮市區中心座標查詢與快取

資料來源：Nominatim (OpenStreetMap)，遵守 1 次/秒 rate limit。
快取檔案：~/MUSEON/data/darwin/raw_data/district_centroids.json

公開 API：
  build_centroids(raw_data_dir, output_path, force=False) — 主函數，建立/更新快取
  load_centroids(path)                                     — 讀取快取
  _geocode_district(name)                                  — 單區查詢（純標準庫）
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# ──────────────────────────────────────────
# 常數
# ──────────────────────────────────────────

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "MUSEON-Darwin/1.0 (https://github.com/museon)"
_RATE_LIMIT_SEC = 1.1  # Nominatim 要求 ≤ 1 req/s
_CACHE_TTL_DAYS = 90

# 台灣座標合法範圍（包含離島）
_TW_LAT_MIN = 21.5
_TW_LAT_MAX = 25.5
_TW_LNG_MIN = 119.5
_TW_LNG_MAX = 122.5


# ──────────────────────────────────────────
# 內部工具
# ──────────────────────────────────────────

def _is_in_taiwan(lat: float, lng: float) -> bool:
    """確認座標在台灣合理範圍內。"""
    return (
        _TW_LAT_MIN <= lat <= _TW_LAT_MAX
        and _TW_LNG_MIN <= lng <= _TW_LNG_MAX
    )


def _geocode_district(name: str) -> tuple[float, float]:
    """
    用 Nominatim 查詢單一行政區的中心座標。

    Parameters
    ----------
    name : str
        行政區名，例如「臺北市信義區」、「高雄市鳳山區」。

    Returns
    -------
    (lat, lng) : tuple[float, float]

    Raises
    ------
    ValueError
        查無結果或座標不在台灣範圍內時。
    urllib.error.URLError
        網路錯誤時。
    """
    # 嘗試不同的查詢格式
    query_variants = [
        f"{name},台灣",
        f"{name},Taiwan",
        name,
    ]

    for query in query_variants:
        params = urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "limit": "3",
            "accept-language": "zh-TW,zh",
            "countrycodes": "tw",
        })
        url = f"{_NOMINATIM_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                results = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError:
            raise

        if not results:
            continue

        # 優先選在台灣範圍內的結果
        for item in results:
            try:
                lat = float(item["lat"])
                lng = float(item["lon"])
            except (KeyError, ValueError):
                continue
            if _is_in_taiwan(lat, lng):
                return lat, lng

    raise ValueError(f"查無台灣範圍內座標：{name}")


def _load_area_map(raw_data_dir: Path) -> dict[str, float]:
    """
    從 population_density_113.json 建立 {site_id: area_km2} 對應表。
    """
    path = raw_data_dir / "population_density_113.json"
    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    area_map: dict[str, float] = {}
    for rec in records:
        site_id = rec.get("site_id", "").strip()
        if not site_id:
            continue
        try:
            area_km2 = float(rec.get("area", 0))
        except (TypeError, ValueError):
            area_km2 = 0.0
        area_map[site_id] = round(area_km2, 4)

    return area_map


def _is_cache_fresh(generated_at_str: str) -> bool:
    """
    判斷快取是否在 TTL 內（90 天）。
    generated_at_str 格式：ISO 8601。
    """
    try:
        generated_at = datetime.fromisoformat(generated_at_str)
        # 確保兩個 datetime 都有時區或都沒有時區
        if generated_at.tzinfo is None:
            now = datetime.now()
        else:
            now = datetime.now(timezone.utc)
        delta = now - generated_at
        return delta.days < _CACHE_TTL_DAYS
    except (ValueError, TypeError):
        return False


# ──────────────────────────────────────────
# 公開 API
# ──────────────────────────────────────────

def load_centroids(path: str) -> dict:
    """
    讀取已存在的座標快取。

    Parameters
    ----------
    path : str
        district_centroids.json 的路徑。

    Returns
    -------
    dict
        快取的完整 JSON 物件（含 generated_at、source、districts、failed）。
        如果檔案不存在，回傳空 dict。
    """
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build_centroids(
    raw_data_dir: str,
    output_path: str,
    force: bool = False,
) -> dict:
    """
    查詢台灣 370 個鄉鎮市區的中心座標，存成 JSON 快取。

    邏輯：
    - 快取存在且在 90 天內 → 直接 return（除非 force=True）
    - 快取存在但缺某些區 → 增量補查缺的區
    - 快取不存在 → 全量查詢

    Parameters
    ----------
    raw_data_dir : str
        raw_data 目錄路徑，用於讀取區名清單和面積數據。
    output_path : str
        輸出 JSON 快取的路徑。
    force : bool
        True = 強制重查所有區（即使快取仍有效）。

    Returns
    -------
    dict
        完整的 districts dict：{site_id: {lat, lng, area_km2}}。
    """
    base = Path(raw_data_dir)
    out = Path(output_path)

    # 確保輸出目錄存在
    out.parent.mkdir(parents=True, exist_ok=True)

    # 載入面積對應表（同時也是區名清單）
    area_map = _load_area_map(base)
    all_districts = set(area_map.keys())

    # 讀取現有快取
    existing: dict = {}
    if out.exists():
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    cached_districts: dict = existing.get("districts", {})
    cached_failed: list = existing.get("failed", [])
    generated_at_str: str = existing.get("generated_at", "")

    # 判斷是否需要重查
    if (
        not force
        and existing
        and _is_cache_fresh(generated_at_str)
        and all_districts.issubset(set(cached_districts.keys()))
    ):
        print(f"[geocoder] 快取有效（{generated_at_str}），共 {len(cached_districts)} 區，跳過查詢。")
        return cached_districts

    # 計算需要查詢的區（增量 or 全量）
    if force:
        to_query = sorted(all_districts)
        districts = {}
        failed_list: list[dict] = []
        print(f"[geocoder] force=True，全量重查 {len(to_query)} 個區。")
    else:
        already_queried = set(cached_districts.keys())
        to_query = sorted(all_districts - already_queried)
        districts = dict(cached_districts)
        # 保留現有 failed，但這次查詢成功的會移除
        failed_list = [f for f in cached_failed if f.get("name") not in set(to_query)]
        if to_query:
            print(f"[geocoder] 增量查詢 {len(to_query)} 個缺少的區。")
        else:
            print(f"[geocoder] 快取過期，全量重查 {len(all_districts)} 個區。")
            to_query = sorted(all_districts)
            districts = {}
            failed_list = []

    # 執行查詢
    total = len(to_query)
    for idx, name in enumerate(to_query, 1):
        if idx > 1:
            time.sleep(_RATE_LIMIT_SEC)

        try:
            lat, lng = _geocode_district(name)
            districts[name] = {
                "lat": round(lat, 6),
                "lng": round(lng, 6),
                "area_km2": area_map.get(name, 0.0),
            }
            print(f"[geocoder] ({idx}/{total}) {name}: lat={lat:.4f}, lng={lng:.4f}")
        except Exception as e:
            print(f"[geocoder] ({idx}/{total}) {name}: 失敗 — {e}")
            failed_list.append({
                "name": name,
                "error": str(e),
                "tried_at": datetime.now().isoformat(timespec="seconds"),
            })

    # 寫入快取
    output_data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "nominatim",
        "total": len(districts),
        "districts": dict(sorted(districts.items())),
        "failed": failed_list,
    }
    out.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    success_count = len(districts)
    fail_count = len(failed_list)
    print(
        f"[geocoder] 完成。成功 {success_count} 區，失敗 {fail_count} 區。"
        f" 快取寫入：{out}"
    )

    return districts
