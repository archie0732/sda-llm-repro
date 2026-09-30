# Log

## 2026-09-30 M0 環境

- 這台 Windows 11 原本沒有 Python（只有 Microsoft Store 的空殼），mise 被 Windows Application Control 政策擋下，所以經使用者同意用 winget 以使用者範圍安裝 Python 3.12.10，再建立專案內的 `.venv`（已加進 `.gitignore`）。
- `pip install -e ".[dev]"` 裝到的版本為 numpy 2.5.3、pillow 12.3.0、opencv-python-headless 5.0.0.93、anthropic 1.9.0、pandas 3.0.6、matplotlib 3.11.2、pytest 9.1.1。
- `pytest -q` 17 項全過。
- `python scripts/dry_run.py` 在合成房間產生 6 組對話（B0–B2、A0–A2），oracle 全部 1.00，random 全部 0.00。
- M0 驗收通過。這一步沒有呼叫任何付費 API，也沒有用到模型 id。

## 2026-09-30 M1 下載標註與挑場景

- 使用者確認接受 ARKitScenes 非商業研究授權。ARKitScenes 官方 repo 取在 commit 474aaa8（2026-09-11），放在 `third_party/`。
- `scripts/download_arkit.sh` 原本寫死 `python3`，在這台 Windows 上會叫到 Store 空殼，所以改成可用 `PYTHON` 環境變數指定直譯器，預設仍是 `python3`。指令為 `PYTHON=.venv/Scripts/python.exe bash scripts/download_arkit.sh annotations`。
- 第一次下載失敗，pandas 的一個 DLL 被 Windows Application Control 擋下（官方 `download_data.py` 用 pandas 讀 metadata）。之後單獨 import pandas 正常，重跑就成功，推測是新安裝的 DLL 第一次載入時被掃描擋住。沒有更動任何安全設定。
- 驗證集 549 支影片的 `_3dod_annotation.json` 全部下載成功，合計 8.0 MB。
- `select_scenes.py --n 40` 找到 310 支符合條件，前 40 支寫進 `data/selected_scenes.csv`。
- 有兩件事留給 M2 處理。第一件是前 40 支裡有 37 支最多實例的類別是 cabinet，只有 3 支是 chair。現在的排序只看「最多實例數」，所以廚房櫃子數量多的場景全部排在前面，跟計畫書設想的「很多張一樣的椅子」不同。M2 前要決定是否限制目標類別或改排序方式，這會動到 3.3 的規則，屆時一併更新 PLAN.md。
- 第二件是 42446103 與 42446100 的實例數與地標數完全相同，查 metadata 確認是同一個 visit（422034），同一個空間錄了兩次。若都留下，兩支場景的結果不獨立，M2 應該每個 visit 只留一支。

## 2026-09-30 M1 下載 3 支影片

- 下載 `data/selected_scenes.csv` 前 3 支（42446103、42446100、42898849）的 `lowres_wide.traj`、`vga_wide`、`vga_wide_intrinsics`、`lowres_depth`、`lowres_wide_intrinsics`，zip 解壓後自動刪除，沒有錯誤。
- 每支實際佔用空間如下（`du -sh`，解壓後）。

| video_id | 合計 | vga_wide | lowres_depth | vga 幀數 | depth 幀數 |
| --- | --- | --- | --- | --- | --- |
| 42446103 | 2.0 GB | 1.7 GB | 317 MB | 3827 | 7652 |
| 42446100 | 2.1 GB | 1.8 GB | 330 MB | 4025 | 8048 |
| 42898849 | 2.1 GB | 1.7 GB | 386 MB | 4353 | 8703 |

- 內參與軌跡加起來每支約 15 MB，可以忽略。以每支約 2.1 GB 估，40 支約 84 GB，D 槽剩 437 GB，空間足夠，但下載時間要算進去。
- 3 支的 metadata `sky_direction` 都是 Left，也就是手機直拿，原始影像是側躺的。

## 2026-09-30 M1 前處理與標註圖

- 第一次讀 42446103 時 `estimate_up_axis` 回傳 1，但這個資料集的世界座標是 z 朝上（相機平均高度 0.14 m，物件中心平均 −0.74 m，框的旋轉都繞 z 軸）。原因是 v1 假設相機 −y 朝上，直拿錄影時相機 −y 其實是水平的。3 支影片的相機 x 軸平均有 0.91 到 0.94 落在世界 −z，印證這一點。上方軸判錯會讓選視角在錯的平面上分方位格，選出的第 3 張圖是對著牆。
- 第一個修正是把 `estimate_up_axis` 改成同時看相機 x 軸與 y 軸（見 PLAN.md 4.1）。修正後 3 支都判為 z。
- 第二個修正是新增 `image_rotation_cw`，依位姿算出影像要順時鐘轉幾度才會正。3 支都得到 90°，跟 metadata 的 Left 一致。存圖時影像與框一起轉，`scene.json` 的框仍是原始座標，另存 `image_rot_cw`，這樣 Phase 2 的 YOLO 仍可用原始影像。
- 第三個修正跟框的角點有關。原本把 `normalizedAxes` 的「行」當框軸，官方 `compute_box_3d` 用的是「列」。這個場景的牆面約在 2.2° 與 92.3°，大部分物件兩種寫法只差約 4°，看不出來，所以另外挑了三個斜放的物件（椅子 45.6°、椅子 −34.8°、角落吊櫃 42.4°），用同一幀畫兩種框並排比對。官方寫法的框包住椅腳，正面也跟角落吊櫃的玻璃門平行。舊寫法的框往桌子方向歪，吊櫃頂面也斜向另一邊。因此改成官方寫法，`dialogue.height` 也跟著改成讀 `rotation[:, up]`。
- 新增測試共 10 項。手機四種拿法的上方軸與旋轉角、框旋轉跟影像旋轉一致、角點跟官方公式一致，以及 42446103 的實際資料檢查（上方軸為 z、旋轉角跟 metadata 一致、涵蓋至少 6 格，沒有資料時自動跳過）。`pytest -q` 27 項全過，`dry_run.py` oracle 仍全部 1.00。
- 對 42446103 執行 `prepare_all.py`，結果 ok。8 個方位全部湊到，相對方位為 0、45、70、157、189、224、270、314 度，第 2 與第 3 張離標準方位差 20° 以上但在 22.5° 容許內。30 個物件中 19 個至少在一張圖可見（cabinet 10、oven 2、chair 2，其餘各 1）。每張圖的框數為 4、5、4、1、2、4、0、3，第 6 張對著掛照片的牆，沒有標註物件。生成 Type B 3 組、Type A 3 組。
- 8 張標註圖與拼圖已存到 `results/m1_check/`（不進 git）。我自己看過，框大致都套在物件上，電視、書櫃、吊櫃、圓桌、椅子、AGA 爐、高櫃都對得上。
- 看到的兩個問題先記下，留給 M2 決定。第一，第 2 張的 #10 oven 框在中島檯面上，這台烤箱應該是嵌在中島裡、從這個角度被檯面擋住，現在的遮擋判斷只看框中心附近的深度，容許差距是半個框長加 0.35 m，所以沒擋掉。第二，第 0 張 #29 stove 與 #30 oven 的框都頂到畫面上緣，兩個標籤疊在一起，#29 的標籤被蓋住。這跟計畫書 11 節「ID 看錯」的風險有關。
- 這一步沒有呼叫任何付費 API。M1 的人眼驗收還在等使用者確認，確認前不進 M2。

## 2026-09-30 計畫書 v2 合併（由 Cowork 工作階段直接寫入）

- 原因是 IROS 正式版附了作者的公開資料（github.com/CKL9001/SDA-LLM），計畫加入 Track V，詳見 `UPDATE_v2.md` 與 PLAN.md 3.0、5.0、M0.5。
- 合併時保留 M1 的所有修正（上方軸、影像旋轉、`normalizedAxes` 以列為軸、`dialogue.height`、`download_arkit.sh` 的 `PYTHON`、`.venv` 的 gitignore），v2 只加上新功能。
- M1 提到第 0 張 #29 與 #30 標籤重疊，新版 `annotate.draw_view` 會把後畫的標籤往下移到不重疊的位置，重跑 `prepare_all.py` 後請再看一次 `results/m1_check/`。
- 在雲端用相同檔案重建專案測過，`pytest -q` 為 29 passed、1 skipped（跳過的是需要 `data/` 的 42446103 測試），在這台電腦上應為 30 passed。
- 下一步是使用者確認 M1 標註圖。確認後先做 M0.5（Track V），再做 M2。

