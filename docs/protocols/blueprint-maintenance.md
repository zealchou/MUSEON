# 工程藍圖的維護義務

> 「藍圖」= 以下五張架構文件的統稱。說「讀藍圖」「更新藍圖」「藍圖同步」即指此組。
> 每次 commit 後檢查：「我改了任何共享狀態的讀寫嗎？改了模組介面嗎？改了 Skill 連線嗎？」
> 如果是，**必須在同一個 commit 中**同步更新對應的藍圖。不更新 = 過期地圖 = 比沒有地圖更危險。

## 五張藍圖速查

| 代稱 | 檔案 | 用途 | 更新時機 |
|------|------|------|---------|
| 🧠 神經圖 | `docs/system-topology.md` | 控制流（誰呼叫誰） | 新增/刪除模組、改變呼叫關係 |
| 🔧 水電圖 | `docs/persistence-contract.md` | 資料流（怎麼存、存哪裡） | 新增/刪除 Store、改變儲存引擎 |
| 🔗 接頭圖 | `docs/joint-map.md` | 共享狀態所有權 | 改變共享檔案的讀寫者或格式 |
| 💥 爆炸圖 | `docs/blast-radius.md` | 改了會炸到誰 | 改變模組的 import 或共享狀態存取 |
| 📬 郵路圖 | `docs/memory-router.md` | 記憶流向（洞見存哪裡） | 新增 Skill 的記憶寫入、改變記憶路由 |

## 施工時判斷邏輯

- 改了共享狀態 → 更新 `joint-map.md`
- 改了 import 關係 → 更新 `blast-radius.md`
- 改了模組拓撲 → 更新 `system-topology.md`
- 改了持久層 → 更新 `persistence-contract.md`
- 改了 Skill 記憶連線 → 更新 `memory-router.md`

## 3D 心智圖同步義務

改了 `system-topology.md` 的節點或連線後，必須跑：

```bash
python scripts/sync_topology_to_3d.py --apply
```

將變更同步到 HTML 心智圖。反向也成立——如果直接修改了 HTML 心智圖，必須回補拓撲文件。

## 藍圖交叉引用規則

更新藍圖 X 後，必須 grep 其他四張藍圖，找出舊版本引用一併更新（見 feedback_38）。

藍圖是合約不是文件——過期合約比沒有合約更危險（見 feedback_33）。
