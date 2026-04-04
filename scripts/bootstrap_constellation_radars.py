"""bootstrap_constellation_radars.py

為所有星座的 boss 使用者建立初始雷達資料。

初始值策略：
  - 各維度 = definition.json 的 default_value（通常 0.5）
  - confidence = 0.15（超過 0.1 門檻，讓探針可以觸發）
  - 加上 bootstrapped=true 和 bootstrapped_at 時間戳記

安全措施：若 radars/boss.json 已存在，跳過不覆蓋。
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- 路徑設定 ---
MUSEON_ROOT = Path(__file__).parent.parent
DATA_DIR = MUSEON_ROOT / "data"
CONSTELLATIONS_DIR = DATA_DIR / "_system" / "constellations"
REGISTRY_PATH = CONSTELLATIONS_DIR / "registry.json"

BOOTSTRAP_CONFIDENCE = 0.15
USER_ID = "boss"


def load_registry() -> list[dict]:
    """讀取 registry.json，回傳星座清單。"""
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return data.get("constellations", [])


def load_definition(constellation_name: str) -> dict | None:
    """讀取某星座的 definition.json。"""
    path = CONSTELLATIONS_DIR / constellation_name / "definition.json"
    if not path.exists():
        print(f"  [警告] definition.json 不存在：{path}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def bootstrap_radar(constellation_name: str, defn: dict) -> dict:
    """根據定義生成初始雷達資料。"""
    dimensions: list[str] = defn.get("dimensions", [])
    default_value: float = defn.get("default_value", 0.5)

    now = datetime.now(timezone.utc).isoformat()

    radar = {
        "constellation": constellation_name,
        "user_id": USER_ID,
    }

    # 各維度使用 default_value（growth_rings 同樣用 0.5，恰好是 default_value）
    for dim in dimensions:
        radar[dim] = default_value

    radar["confidence"] = BOOTSTRAP_CONFIDENCE
    radar["bootstrapped"] = True
    radar["bootstrapped_at"] = now
    radar["updated_at"] = now

    return radar


def main() -> None:
    print("=" * 60)
    print("Bootstrap Constellation Radars")
    print(f"目標使用者：{USER_ID}")
    print(f"初始 confidence：{BOOTSTRAP_CONFIDENCE}")
    print("=" * 60)

    constellations = load_registry()
    print(f"\n共找到 {len(constellations)} 個星座\n")

    success_count = 0
    skip_count = 0
    error_count = 0

    for entry in constellations:
        name = entry["name"]
        display = entry.get("display_name", name)
        print(f"[{name}] {display}")

        # 檢查是否已存在
        radar_path = CONSTELLATIONS_DIR / name / "radars" / f"{USER_ID}.json"
        if radar_path.exists():
            print(f"  ✓ 已存在，跳過（{radar_path}）")
            skip_count += 1
            continue

        # 讀取定義
        defn = load_definition(name)
        if defn is None:
            print(f"  ✗ 無法讀取定義，跳過")
            error_count += 1
            continue

        dims = defn.get("dimensions", [])
        print(f"  維度數量：{len(dims)}，default_value：{defn.get('default_value', 0.5)}")

        # 建立目錄
        radar_path.parent.mkdir(parents=True, exist_ok=True)

        # 生成雷達資料
        radar = bootstrap_radar(name, defn)

        # 寫入檔案
        radar_path.write_text(
            json.dumps(radar, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"  ✓ 已建立：{radar_path}")
        success_count += 1

    print("\n" + "=" * 60)
    print(f"完成！建立：{success_count}，跳過：{skip_count}，錯誤：{error_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
