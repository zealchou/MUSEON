"""
places_crawler.py — 使用 Google Places API (New) Nearby Search 抓取 POI 數據
並計算各區的場所密度指標（每萬人）。

公開 API：
  crawl_all_districts(centroids_path, output_path, force, radius, types_to_crawl)
      → dict   主函數：抓取所有區的 POI 數據，回傳快取內容

  compute_places_indicators(cache_path, population_data)
      → dict[str, dict[str, float]]   從快取算出每個區的場所密度指標

  _search_nearby(api_key, lat, lng, included_types, radius)
      → list[dict]   單次 API 呼叫

快取路徑：~/MUSEON/data/darwin/raw_data/places_cache.json
TTL：90 天（抓一次存檔，90 天內重用）
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────
# 常數
# ──────────────────────────────────────────

PLACES_API_URL = "https://places.googleapis.com/v1/places:searchNearby"
CACHE_VERSION = 1
CACHE_TTL_DAYS = 90
API_CALL_INTERVAL = 0.3   # 秒，避免 rate limit
API_RETRY_COUNT = 2
API_RETRY_WAIT = 2.0       # 秒
MAX_RESULTS_PER_CALL = 20
PROGRESS_INTERVAL = 10     # 每 N 個區印進度

# POI 類型 → indicator 名稱對應
TYPE_TO_INDICATOR: dict[str, str] = {
    "cafe":               "cafe_density",
    "gym":                "gym_density",
    "shopping_mall":      "mall_density",
    "religious_venue":    "religious_venue_density",  # 聚合多種類型
    "restaurant":         "fine_dining_density",      # 需要 priceLevel 過濾
    "outdoor_venue":      "outdoor_venue_density",    # 聚合多種類型
    "brand_store":        "brand_store_density",      # 聚合多種類型
}

# 各邏輯類型對應的 Google Places API includedTypes
LOGICAL_TYPES: dict[str, list[str]] = {
    "cafe":            ["cafe"],
    "gym":             ["gym"],
    "shopping_mall":   ["shopping_mall"],
    "religious_venue": ["hindu_temple", "church", "mosque", "buddhist_temple"],
    "restaurant":      ["restaurant"],
    "outdoor_venue":   ["park", "campground", "hiking_area"],
    "brand_store":     ["clothing_store", "shoe_store", "jewelry_store"],
}

# fine_dining 的 priceLevel 過濾條件
FINE_DINING_PRICE_LEVELS = {"PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE"}


# ──────────────────────────────────────────
# API Key 載入
# ──────────────────────────────────────────

def _load_api_key() -> str:
    """從 ~/MUSEON/.env 讀取 GOOGLE_MAPS_API_KEY。"""
    env_path = Path.home() / "MUSEON" / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("GOOGLE_MAPS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise ValueError("GOOGLE_MAPS_API_KEY not found in .env")


# ──────────────────────────────────────────
# 快取工具
# ──────────────────────────────────────────

def _now_iso() -> str:
    """回傳本機現在時間的 ISO 8601 字串（不含微秒，不含時區後綴）。"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _is_cache_fresh(crawled_at: str, ttl_days: int = CACHE_TTL_DAYS) -> bool:
    """
    判斷快取是否仍在 TTL 內。
    crawled_at 為 ISO 8601 字串（無時區後綴），與 _now_iso() 格式一致。
    """
    try:
        ts = datetime.fromisoformat(crawled_at.rstrip("Z").split("+")[0])
        now = datetime.now()
        return (now - ts).days < ttl_days
    except (ValueError, TypeError):
        return False


def _load_cache(cache_path: Path) -> dict:
    """讀取快取檔，若不存在回傳空白快取結構。"""
    if cache_path.exists():
        try:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "version": CACHE_VERSION,
        "last_full_crawl": None,
        "cache_ttl_days": CACHE_TTL_DAYS,
        "districts": {},
    }


def _save_cache(cache: dict, cache_path: Path) -> None:
    """寫入快取檔，確保目錄存在。"""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────
# 核心 API 呼叫
# ──────────────────────────────────────────

def _search_nearby(
    api_key: str,
    lat: float,
    lng: float,
    included_types: list[str],
    radius: int = 5000,
) -> list[dict]:
    """
    單次 Google Places API (New) Nearby Search 呼叫。

    Parameters
    ----------
    api_key : str
        Google Maps API Key。
    lat, lng : float
        搜尋中心點（緯度/經度）。
    included_types : list[str]
        Places API 的 includedTypes 欄位（可多種類型聚合）。
    radius : int
        搜尋半徑（公尺），預設 5000。

    Returns
    -------
    list[dict]
        API 回傳的 places 列表，失敗時回傳空列表。
    """
    body = {
        "includedTypes": included_types,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius),
            }
        },
        "maxResultCount": MAX_RESULTS_PER_CALL,
        "languageCode": "zh-TW",
    }
    body_bytes = json.dumps(body).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.types,places.location,places.priceLevel",
    }

    req = urllib.request.Request(
        PLACES_API_URL,
        data=body_bytes,
        headers=headers,
        method="POST",
    )

    for attempt in range(1 + API_RETRY_COUNT):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("places", [])
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if attempt < API_RETRY_COUNT:
                time.sleep(API_RETRY_WAIT)
            else:
                raise RuntimeError(
                    f"HTTP {e.code} from Places API: {err_body[:200]}"
                ) from e
        except Exception:
            if attempt < API_RETRY_COUNT:
                time.sleep(API_RETRY_WAIT)
            else:
                raise

    return []


# ──────────────────────────────────────────
# 主函數
# ──────────────────────────────────────────

def crawl_all_districts(
    centroids_path: str,
    output_path: str,
    force: bool = False,
    radius: int = 5000,
    types_to_crawl: list[str] | None = None,
) -> dict:
    """
    抓取所有區的 POI 數據，結果存入 output_path（快取）。

    Parameters
    ----------
    centroids_path : str
        區域中心點 JSON 檔路徑。
        格式：{site_id: {"lat": float, "lng": float}} 或
              [{site_id: str, lat: float, lng: float}]
    output_path : str
        快取輸出路徑，預設為 ~/MUSEON/data/darwin/raw_data/places_cache.json。
    force : bool
        True = 忽略快取，全部重抓。
    radius : int
        搜尋半徑（公尺）。
    types_to_crawl : list[str] | None
        要抓的邏輯類型（LOGICAL_TYPES 的 key），None = 全部 7 種。

    Returns
    -------
    dict
        更新後的快取內容。
    """
    api_key = _load_api_key()
    cache_path = Path(output_path)
    cache = _load_cache(cache_path)

    # 載入中心點
    with open(centroids_path, encoding="utf-8") as f:
        raw_centroids = json.load(f)

    # 統一轉換為 {site_id: {lat, lng}}
    # geocoder 輸出格式: {"districts": {name: {lat, lng, ...}}, ...}
    if isinstance(raw_centroids, dict) and "districts" in raw_centroids:
        raw_centroids = raw_centroids["districts"]
    if isinstance(raw_centroids, dict):
        centroids: dict[str, dict] = {
            sid: {"lat": v["lat"], "lng": v["lng"]}
            for sid, v in raw_centroids.items()
            if isinstance(v, dict) and "lat" in v
        }
    elif isinstance(raw_centroids, list):
        centroids = {}
        for item in raw_centroids:
            sid = item.get("site_id") or item.get("district") or item.get("name", "")
            if sid:
                centroids[sid] = {
                    "lat": float(item.get("lat", item.get("latitude", 0))),
                    "lng": float(item.get("lng", item.get("longitude", 0))),
                }
    else:
        raise ValueError(f"Unsupported centroids format: {type(raw_centroids)}")

    logical_types = types_to_crawl or list(LOGICAL_TYPES.keys())
    total_districts = len(centroids)
    crawled_count = 0
    skipped_count = 0
    error_count = 0

    print(f"[places_crawler] 開始抓取 {total_districts} 個區 × {len(logical_types)} 種類型")
    if force:
        print("[places_crawler] force=True，忽略快取全部重抓")

    for idx, (site_id, coord) in enumerate(centroids.items(), start=1):
        lat = coord["lat"]
        lng = coord["lng"]

        if site_id not in cache["districts"]:
            cache["districts"][site_id] = {"crawled_at": None, "types": {}, "errors": []}

        district_cache = cache["districts"][site_id]

        # 進度報告
        if idx % PROGRESS_INTERVAL == 0 or idx == total_districts:
            print(
                f"[places_crawler] 進度 {idx}/{total_districts} — "
                f"已抓 {crawled_count}，跳過 {skipped_count}，錯誤 {error_count}"
            )

        for logical_type in logical_types:
            included_types = LOGICAL_TYPES[logical_type]

            # 快取判斷
            type_cache = district_cache["types"].get(logical_type)
            if not force and type_cache and _is_cache_fresh(
                district_cache.get("crawled_at", ""), CACHE_TTL_DAYS
            ):
                skipped_count += 1
                continue

            # 呼叫 API
            try:
                places = _search_nearby(api_key, lat, lng, included_types, radius)
                district_cache["types"][logical_type] = {
                    "count": len(places),
                    "raw_results": places,
                }
                crawled_count += 1
                time.sleep(API_CALL_INTERVAL)
            except Exception as e:
                err_msg = f"{logical_type}@{site_id}: {e}"
                district_cache.setdefault("errors", []).append(
                    {"type": logical_type, "error": str(e), "timestamp": _now_iso()}
                )
                print(f"[places_crawler] ⚠ 錯誤（繼續）: {err_msg}")
                error_count += 1

        # 每區完成後更新 crawled_at 並寫入快取（防中斷丟失）
        district_cache["crawled_at"] = _now_iso()
        _save_cache(cache, cache_path)

    # 更新全量抓取時間戳
    cache["last_full_crawl"] = _now_iso()
    _save_cache(cache, cache_path)

    print(
        f"[places_crawler] 完成！已抓 {crawled_count}，跳過 {skipped_count}，錯誤 {error_count}"
    )
    print(f"[places_crawler] 快取已寫入：{cache_path}")
    return cache


# ──────────────────────────────────────────
# 密度指標計算
# ──────────────────────────────────────────

def compute_places_indicators(
    cache_path: str,
    population_data: dict,
) -> dict[str, dict[str, float]]:
    """
    從快取算出每個區的場所密度指標（每萬人）。

    Parameters
    ----------
    cache_path : str
        places_cache.json 路徑。
    population_data : dict
        {site_id: {people_total: float, ...}} — 來自 data_loader 的人口資料。

    Returns
    -------
    dict[str, dict[str, float]]
        {site_id: {indicator_name: density_per_10k_people, ...}}

    密度公式
    --------
        xxx_density = place_count / (population / 10000)

    fine_dining_density 額外過濾：
        只計入 priceLevel in {PRICE_LEVEL_EXPENSIVE, PRICE_LEVEL_VERY_EXPENSIVE}
    """
    cache = _load_cache(Path(cache_path))
    result: dict[str, dict[str, float]] = {}

    for site_id, district_data in cache["districts"].items():
        indicators: dict[str, float] = {}
        types_data = district_data.get("types", {})

        def _saturation(count: int) -> float:
            """飽和度指標：count/20（API 上限 20），0=沒有，1=飽和"""
            return min(count, MAX_RESULTS_PER_CALL) / MAX_RESULTS_PER_CALL

        # 1. cafe_density
        if "cafe" in types_data:
            indicators["cafe_density"] = _saturation(types_data["cafe"]["count"])

        # 2. gym_density
        if "gym" in types_data:
            indicators["gym_density"] = _saturation(types_data["gym"]["count"])

        # 3. mall_density
        if "shopping_mall" in types_data:
            indicators["mall_density"] = _saturation(types_data["shopping_mall"]["count"])

        # 4. religious_venue_density
        if "religious_venue" in types_data:
            indicators["religious_venue_density"] = _saturation(
                types_data["religious_venue"]["count"]
            )

        # 5. fine_dining_density（需過濾 priceLevel）
        if "restaurant" in types_data:
            raw_results = types_data["restaurant"].get("raw_results", [])
            fine_dining_count = sum(
                1 for p in raw_results
                if p.get("priceLevel") in FINE_DINING_PRICE_LEVELS
            )
            indicators["fine_dining_density"] = _saturation(fine_dining_count)

        # 6. outdoor_venue_density
        if "outdoor_venue" in types_data:
            indicators["outdoor_venue_density"] = _saturation(
                types_data["outdoor_venue"]["count"]
            )

        # 7. brand_store_density
        if "brand_store" in types_data:
            indicators["brand_store_density"] = _saturation(
                types_data["brand_store"]["count"]
            )

        if indicators:
            result[site_id] = indicators

    return result
