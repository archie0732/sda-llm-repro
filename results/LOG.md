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

## 2026-09-30 合併 v2 並下載作者公開資料

- 合併前 `pytest -q` 為 28 passed、2 skipped（兩項需要作者資料）。所有變更 commit 為 691a4ef「merge plan v2 from Cowork」，包含根目錄的 `sda-llm-repro.zip`（v1 起始程式碼，只有程式與文件，沒有資料或金鑰）。
- `bash scripts/fetch_visdial.sh` 把作者 repo 取到 `third_party/SDA-LLM`，commit c10ac74（2026-01-10）。
- 之後 `pytest -q` 為 30 passed，跟 UPDATE_v2.md 說的一致。

## 2026-09-30 M1 驗收與標籤重疊

- 使用者已看過 42446103 的標註圖，確認框有套在物件上，M1 人眼驗收通過。
- 用 v2 程式重跑 `prepare_all.py --csv data/m1_one.csv`，結果 ok。新的 8 張標註圖與拼圖已覆蓋到 `results/m1_check/`（不進 git）。
- 用同樣的畫圖程式重畫一次並記下每個標籤底色框的位置，8 張圖的標籤兩兩之間都沒有重疊。第 0 張的 #29 在 y 為 −1 到 14，#30 被往下移到 y 為 15 到 30，兩個標籤都看得清楚，我也用眼睛看過這張圖。
- 新增測試 `test_tags_of_boxes_at_top_edge_do_not_overlap`，用三個都頂到上緣的框檢查標籤不重疊。舊版程式會讓前兩個標籤都畫在 y=0，這個測試會失敗。`pytest -q` 為 31 passed。

## 2026-09-30 M0.5 Track V 標註圖（未呼叫 API）

- 使用者還沒設定 `SDA_API_KEY`，所以這一步不呼叫任何付費 API，也沒有用到模型 id。
- `run_visdial.py` 原本在存圖之前就建立 Claude 客戶端，沒有金鑰時會先出錯。改成先讀資料與存圖，再建立客戶端，並新增 `--images_only`，存完圖就結束。
- 執行 `run_visdial.py --track A --save_images --images_only`，Office 的 8 張標註圖存到 `results/visdial_check/office_view_0.jpg` 到 `office_view_7.jpg`（不進 git，作者資料沒有授權檔）。標籤沿用作者的樣式，例如 `whiteboard 1`。
- 我看過第 0 張與第 2 張，框與標籤清楚。第 2 張背景有幾張摺疊椅沒有框，這是作者原本的標註就沒有框，不是我們的程式漏畫。
- 等使用者確認標籤清楚、設定 `SDA_API_KEY` 後，才照 CLAUDE.md 先用 `--limit` 試跑 3 組。

## 2026-09-30 M2 挑場景規則改版

- 使用者對 M1 留下的兩個問題做了決定。目標類別以 chair、stool、table、sofa 為主，挑場景時依這些類別的實例數排序。同一個 visit 只留一支影片。PLAN.md 3.3 與 11 節已照此更新。
- 程式的改動有三處。`dialogue.TARGET_CLASSES` 定義這四類。`select_scenes.py` 改成依四類中最多的那一類的實例數排序，同分再看四類總數與地標數，並讀 `metadata.csv` 的 `visit_id`，每個 visit 只留第一名。`prepare_scene` 新增 `target_classes`，對話目標只從這四類挑，其他類別仍可當地標。
- 驗證集 549 支影片分屬 183 個 visit。符合條件的有 138 支，每個 visit 留一支後剩 61 支，前 40 支寫進 `data/selected_scenes.csv`，舊清單備份為 `data/selected_scenes_v1.csv`。
- 新清單的最多類別有 32 支是 chair、6 支是 table、2 支是 sofa。最多實例數的分布是 12 張 1 支、9 張 1 支、8 張 1 支、7 張 3 支、6 張 5 支、5 張 11 支、4 張 17 支、3 張 1 支。31 支有沙發，17 支有凳子。跟舊清單只重疊 9 支。
- 有一個風險要先記下。一半左右的場景最多只有 4 個同類物件，而可見性過濾後常會變少（42446103 標註有 3 張椅子，8 張圖裡只看得到 2 張），所以可用場景可能不到 25 支。到時可以把 `--n` 加到全部 61 支。
- 已下載的 3 支都不在新清單。42446103 與 42446100 同一個 visit，而且椅子只有 3 張，排在 40 名外。42898849 跟清單第 3 名 42898854 是同一個 visit（434659），椅子都是 8 張，42898854 的桌子多一張所以排前面。如果想省一支的下載量，可以手動換成已經下載的 42898849。
- 用新規則重跑 42446103，對話從 6 組變成 4 組（Type B 2 組、Type A 2 組），目標都是椅子。`pytest -q` 31 passed，`dry_run.py` oracle 仍全部 1.00。
- 照使用者指示，還沒有下載新清單的影片。以每支約 2.1 GB 估，40 支約 84 GB。


## 2026-09-30 M6 第一步 去重（gt 框，只有 42446103）

- 使用者指示先做 M6 的第一步，這一步不花錢。M3 到 M5 要等 API key，所以順序跟 PLAN.md 第 10 節不同，是使用者的決定。
- 執行 `run_dedup.py --source gt --tau 0.3`、`0.5`、`0.8`，結果寫在 `results/dedup.jsonl`。這時 `data/prepared/` 只有 42446103，所以只有這一個場景。
- 8 張圖共有 23 個框，對應 19 個物件，所以真正該合併的只有 4 對（同一物件出現在兩張圖）。

| 方法 | τ (m) | precision | recall | F1 | 預測物件數 | 物件數量誤差 |
| --- | --- | --- | --- | --- | --- | --- |
| 不去重 | 無 | 1.00 | 0.00 | 0.00 | 23 | +4 |
| 幾何去重 | 0.3 | 1.00 | 0.75 | 0.86 | 20 | +1 |
| 幾何去重 | 0.5 | 1.00 | 1.00 | 1.00 | 19 | 0 |
| 幾何去重 | 0.8 | 0.67 | 1.00 | 0.80 | 18 | −1 |

- 不去重的 precision 是 1.00，只是因為它沒有預測任何連結，程式把沒有連結的情況定義成 1，這個數字沒有意義。
- 另外寫了診斷程式看每一對的反投影距離（在 scratchpad，沒有進 repo）。四對正確的配對距離是 0.04、0.09、0.25、0.44 m。τ=0.3 漏掉的是椅子 #19（0.44 m）。最近的錯誤配對是櫃子 #8 與 #9，距離 0.70 m，τ=0.8 把它們併在一起，因為 #9 已經跟另一張圖的 #9 是同一群，所以一次產生 2 對錯誤連結。
- 反投影點跟標註框中心的距離，中位數約 0.3 m，最大 1.36 m。反投影取的是框中央看得到的表面，不是物件中心，大的物件（櫃子、桌子）誤差比較大。所以 τ 太小會漏掉大物件，τ 太大會把相鄰的同類櫃子併起來。
- 只有 4 對正例，這組數字只能當程式可以跑的確認，不能當結論。之後要在所有可用場景上重跑。
- 補充（使用者要求）。不去重的 precision = 1.00 沒有意義。之後 `evaluate_clusters` 在沒有預測任何連結時回傳 None，`summarize_dedup.py` 顯示 N/A。

## 2026-09-30 M2 下載前 10 支與前處理

- 使用者同意用已下載的 42898849 代替 42898854（同一個 visit 434659，椅子都是 8 張）。`select_scenes.py` 新增 `--prefer`，預設就是 42898849，重新產生的 `data/selected_scenes.csv` 第 3 名已換成它。全部 61 支另存 `data/selected_scenes_all61.csv`。PLAN.md 3.3 已註明。
- 使用者也決定可用場景不足 25 支時擴大到 61 支。
- 先試過前 5 支（`data/m2_top5.csv`），下載時 42898854 已經在清單裡，所以它的 1.7 GB 也下載了，現在沒有用到，還留在 `data/` 裡。
- 下載新清單前 10 支（`data/m2_top10.csv`），官方下載程式會跳過已經解壓的資產，沒有錯誤。10 支合計約 13.6 GB，每支 0.5 到 2.5 GB。
- `prepare_all.py --csv data/m2_top10.csv` 的結果是 7 支 ok、3 支 rejected，共 32 組對話。

| video_id | 結果 | 對話數 |
| --- | --- | --- |
| 42445998 | ok | 5 |
| 41159541 | ok | 6 |
| 42898849 | ok | 6 |
| 47429906 | rejected | 0 |
| 42897564 | ok | 4 |
| 47204552 | ok | 4 |
| 48458417 | ok | 4 |
| 48018956 | rejected | 0 |
| 45662924 | rejected | 0 |
| 47331265 | ok | 3 |

- 三支被拒絕的原因都是 8 張圖裡目標類別看得到的不到 2 個，不是方位不夠（涵蓋數為 6、8、8）。47429906 的站點在廚房，7 張椅子都不在畫面內。48018956 的站點在門口，8 張圖只有 1 張有物件，而且那張正對 1 m 外的門板，深度判斷把後面的東西全部擋掉是對的。45662924 不做深度判斷時看得到 6 張椅子、4 張凳子，做了之後全部被擋掉。
- 45662924 被擋掉的物件，量到的深度都約是框中心距離的 0.6 倍，我原本懷疑深度有系統性錯誤。把深度圖反投影回世界座標檢查，第 1 張有 41% 的點落在地板高度 5 cm 內，所以深度與位姿是對的。原因是廚房中島剛好擋在遠處餐椅與吧台凳的框中心前面，椅背其實看得到。
- 這表示目前的可見性判斷只看框中心一點，會把「部分被桌子或中島擋住」的椅子當成看不見，而圍著桌子的椅子正是我們要的目標。另外 `select_views` 選站點只看方位涵蓋，不看目標類別看不看得到。這兩點我先不改，等使用者決定（改的話會動到 PLAN.md 4.2 第 2 步與第 4 步）。
- 以目前 7/10 的比例推估，40 支大約可用 28 支，接近 25 支的門檻。每支平均 4.6 組對話，28 支約 128 組，也接近 120 組的門檻。

## 2026-09-30 M6 去重重跑（gt 框，7 個可用場景）

- 對 7 個可用場景執行 `run_dedup.py --source gt --csv data/m2_top10.csv`，τ 為 0.3、0.4、0.5、0.6、0.8（PLAN.md 第 6 節已從三個改成五個）。之前只有 42446103 的結果改名為 `results/dedup_42446103_first.jsonl`，新的結果在 `results/dedup.jsonl`，彙整表由新的 `scripts/summarize_dedup.py` 產生，存在 `results/dedup_summary.md`。
- 各場景的連結數加總後再算 precision、recall、F1。7 個場景共有 27 對真正該合併的連結。

| 方法 | τ (m) | precision | recall | F1 | 數量誤差平均 | 數量誤差絕對值平均 |
| --- | --- | --- | --- | --- | --- | --- |
| 不去重 | 無 | N/A | 0.00 | 0.00 | +3.57 | 3.57 |
| 幾何去重 | 0.3 | 0.27 | 0.70 | 0.39 | +0.14 | 1.29 |
| 幾何去重 | 0.4 | 0.25 | 0.81 | 0.39 | −0.29 | 1.43 |
| 幾何去重 | 0.5 | 0.26 | 0.85 | 0.39 | −0.57 | 1.43 |
| 幾何去重 | 0.6 | 0.24 | 0.85 | 0.38 | −0.86 | 1.14 |
| 幾何去重 | 0.8 | 0.22 | 0.89 | 0.35 | −1.86 | 1.86 |

- precision 低幾乎全部來自 48458417。τ=0.3 時全部 52 對錯誤連結中有 50 對在這個場景，其他 6 個場景合計只有 2 對。這個場景有 6 張圍著餐桌的椅子，框中央的深度量到的是桌面，6 張椅子反投影後都落在彼此 0.3 m 內，跟各自真實中心差 0.2 到 1.24 m，於是用 union-find 串成一整群。連結數是兩兩配對，會隨群的大小平方成長，所以一個場景就壓過其他全部。
- 這跟上一段的可見性問題是同一個原因，用框中心附近的深度代表物件位置，在椅子塞在桌下時會失效。這是 D2 的真實限制，跟 RQ4 有關，我照實記下，沒有為了分數去調 τ 或改方法。之後可以另外報每個場景的平均（macro average），避免單一場景主導，但 PLAN.md 目前定義的是加總，我沒有改。
- 其他 6 個場景在 τ=0.5 時，precision 與 recall 大多在 0.67 到 1.00 之間，但每個場景只有 0 到 5 對連結，數字很不穩定。

## 2026-09-30 M2 人工檢查清單

- 新增 `scripts/make_check_sheet.py`，從 7 個可用場景的 32 組對話中用 seed 0 隨機抽 10 組（Type A 3 組、Type B 7 組），輸出 `results/m2_check/index.html`（不進 git，內含資料集影像）。
- 每一組列出每句話與正解集合、生成這句話時用的數字（到地標或機器人的距離、高度，只列當時還剩下的候選）、俯視圖（紅色是目標、橘色是候選、藍色是地標），以及看得到候選或地標的標註圖。
- 抽到的是 47204552-A1、48458417-A1、48458417-B0、42897564-B2、41159541-B1、42445998-B2、42898849-B1、42898849-B0、42897564-B1、42445998-A0。
- Type A 的補充句只要求對目標成立，不要求能區分目標，例如 47204552-A1 的「near the table」三張椅子都成立。這是 PLAN.md 4.3 的設計，不算錯誤。
- 等使用者檢查後把錯誤數記在這裡。這一步到現在都沒有呼叫任何付費 API。

## 2026-09-30 M2 可見性改成深度圖逐像素判斷

- 使用者看了 M2 檢查表，驗收沒過。47204552 第 4 張的 #22 桌子框蓋滿整張圖，48458417 第 4、5 張被桌布擋住的 #16、#17、#18 也畫了框。使用者決定改用深度圖逐像素判斷，取代「框上半部取多點」的提議。PLAN.md 4.2 第 4 步與第 6 節（新增 D2b）已更新。
- 程式的改動在 `geometry.py`（`depth_to_world`、`in_box_mask`、`object_pixels`、`box_from_pixels`、`backproject_pixels`）與 `annotate.compute_view_boxes`。舊的 `visible_with_depth` 刪掉。門檻是立方體外擴 5 cm、上下左右各去掉 2%、至少 30 個深度像素、框面積至少 150 像素。`run_dedup.py` 新增 `geometric_mask`（D2b），`--tau` 可一次給多個值。
- `make_check_sheet.py` 原本只在圖不存在時才複製，重跑前處理後會留下舊圖。改成每次先清空 `img/`，並新增 `--recheck`，把上次標出問題的圖新舊並排。
- 新增 4 項測試，用光線投射畫出的合成深度圖檢查。被桌布擋住的椅子沒有框、半被擋住的椅子框只到看得到的地方、離群像素被去掉、像素太少不畫框、D2b 的點落在物件上。`pytest -q` 36 passed（含下一段的 1 項）。
- 舊結果都留著。`data/prepared_v1/`、`results/m2_check_v1/`、`results/dedup_v1_projbox.jsonl`、`results/dedup_summary_v1_projbox.md`。
- 重跑 `prepare_all.py --csv data/m2_top10.csv`，8 支 ok、2 支 rejected（47429906、48018956），共 42 組對話。之前的版本是 7 支 32 組。45662924 從 rejected 變成 ok（6 組），就是上次記下的「中島擋住框中心、其實椅背看得到」的情況。47204552 從 4 組變成 6 組，42445998 從 5 組變成 4 組。
- 我自己看了三張問題圖，只修好一部分。48458417 的 #18 不見了。但 47204552 第 4 張的 #22 仍然從上緣畫到接近下緣，48458417 第 4、5 張的 #16、#17 框往上延伸到桌布。
- 另外寫了診斷程式（在 scratchpad，沒有進 repo）找原因，有兩個。第一是地板，每個物件的像素有 24% 到 47% 落在立方體最下面 5 cm，也就是物件底下與周圍的地板。第二是立方體互相重疊，塞在桌下的椅子，它的立方體跟桌子的立方體重疊，這些物件有 72% 到 100% 的像素同時落在另一個物件的立方體內。48458417 第 5 張的 #17 全部 1886 個像素都在桌子立方體內，是桌布而不是椅子。
- 所以照目前的規則，M2 人工檢查應該還不會過。要不要加「去掉立方體底部幾公分」與「重疊像素只算給一個物件」這兩條規則，等使用者決定，這一步我沒有自己加。
- 去重用新的框重跑（8 個場景），因為部分被擋住的物件現在也有框，真正該合併的連結從 27 對變成 117 對，所以數字不能跟舊表直接比。D2b 在每個 τ 的 F1 都比 D2 高，例如 τ=0.5 時 D2 為 0.47、D2b 為 0.57，τ=0.3 時 precision 為 0.62 對 0.94。但 recall 在 τ≤0.5 時都只有 0.2 到 0.5，因為取的是看得到那一部分的中心，大物件從不同角度看到的部分不同。上面講的地板與重疊問題也會影響 D2b，所以這組數字先當參考。

## 2026-09-30 M0.5 Track V 試跑 3 組（第一次呼叫付費 API）

- `SDA_API_KEY` 有設定，`ANTHROPIC_API_KEY` 沒有設定。
- `python -m sdarepro.vlm --list` 列出 13 個模型，Sonnet 等級最新的是 `claude-sonnet-5-5`，所以 SDA_MODEL 用 `claude-sonnet-5-5`。這次用命令列環境變數傳入，程式裡沒有寫死。
- 試跑前發現 `ClaudeClient` 會固定傳 `temperature=0.0`，但 SDK 1.9.0 的 `messages.create` 已經沒有這個參數，一呼叫就會出 TypeError（還沒送出請求）。目前的模型也拒絕非預設的取樣設定。所以拿掉 temperature，並新增 `SDA_THINKING`，預設 `between_tools`（不用 thinking），PLAN.md 5.2 第 5 步已更新並寫了原因。另外記錄 `stop_reason` 與 cache 寫入的 token。新增測試 `test_claude_client_sends_no_temperature`。
- 確認參數時送了 2 次很短的純文字請求（各約 15 個輸入、4 個輸出 token），兩種 thinking 設定都被接受。
- `run_visdial.py --track A --cond multi_image --limit 3` 的結果如下。3 組都沒有找到（T_A 皆為 0）。

| 對話 | 目標 | 每輪的回答 | 結果 |
| --- | --- | --- | --- |
| Office-A0 | chair 1 | chair 1、chair 2 | 沒有縮到一個，只有一句話所以結束 |
| Office-A1 | chair 2 | chair 3、chair 4，再來 chair 4 | 指錯 |
| Office-A2 | chair 3 | chair 3、chair 4 | 沒有縮到一個 |

- 模型的理由三次都只提到第 5 張圖。A1 與 A2 它都認為檯燈、水瓶所在的桌子旁邊是摺疊椅 chair 3 與 chair 4。3 組太少，還不能說是模型看錯、標籤看不清楚，還是作者的對話本身有歧義，全跑之後再看。
- 實際用量合計為未快取輸入 233、cache 寫入 12698、cache 讀取 38094、輸出 341 token。以 Sonnet 5.5 的價格（輸入每百萬 2 美元、輸出 10 美元、cache 讀取 0.2 美元，cache 寫入以 1.25 倍輸入即 2.5 美元估）計算約 0.043 美元。8 張圖約 12.7k token，第一組寫入快取，後兩組都讀到快取。
- 以此估計，15 組跑完一個影像條件約 0.2 美元，V1 四個條件合計不到 1 美元。等使用者同意後再全跑。

## 2026-09-30 M2 逐像素判斷加上地板與重疊兩條規則

- 使用者決定加兩條規則。離地 5 cm 內的深度像素不算，地板高度用場景資料估計。同時落在兩個以上物件立方體內的像素，每個物件都不算。PLAN.md 4.2 第 4 步已更新，也寫了代價。
- 地板高度的估法是把 8 張圖的深度點都反投影，取由下往上第一個占全部點 2% 以上的 2 cm 區間，再取附近 3 cm 內的中位數（`geometry.estimate_floor_height`）。重疊判斷用場景的全部標註物件，`run_dedup.py` 的 D2b 也改用同一個函式 `geometry.frame_object_pixels`，所以兩邊規則一致。`scene.json` 新增 `up_vector` 與 `floor_height`。
- 檢查地板估計。8 個場景的估計值跟椅子、桌子、沙發、凳子立方體底部的中位數都差 2 cm 以內（例如 48458417 為 −1.234 對 −1.231 m，42897564 為 −1.578 對 −1.599 m）。
- 新增 2 項測試。第一項檢查地板高度估得出來（加了 20 個地板下的雜訊點也不受影響），而且沒有任何離地 5 cm 內的像素被算給物件。第二項用一張只有標註、沒有畫進深度圖的椅子，它的立方體凸出桌面，沒有這條規則時會拿到至少 30 個桌布像素，加了規則之後沒有框，而且每個物件的像素都不落在其他物件的立方體內。寫測試時發現單一張圖無法估上方軸（`estimate_up_axis` 需要相機轉動），前處理一律傳入場景的上方軸，所以測試也改成傳入。`pytest -q` 38 passed。
- 第二版（逐像素、沒有兩條規則）的結果另存為 `data/prepared_v2/`、`results/m2_check_v2/`、`results/dedup_v2_pixels.jsonl`、`results/dedup_summary_v2_pixels.md`。`.gitignore` 新增 `results/m2_check_v*/` 與 `results/human_office/`，這些資料夾都有資料集影像。
- 重跑前處理，結果跟第二版一樣是 8 支 ok、2 支 rejected，共 42 組對話，各場景對話數也相同。
- 我看了三張問題圖。48458417 第 4 張的 #17、#18 不見了，#16 只剩右邊那張椅子（椅背在桌子後面、座椅在桌下）。第 5 張的 #16、#17 都不見了，但桌下看得到座椅的兩張椅子也因此沒有框，因為它們的立方體整個在桌子的立方體裡面，這就是 PLAN.md 寫的代價。47204552 第 4 張的 #22 不再畫到畫面下緣，底部停在 y≈305，但還蓋住 #20 椅背的上半部。48458417 第 4 張的桌子 #20 框反而變小，左邊一段桌布和桌腳下半部沒有框進去，桌腳的像素可能跟塞在桌下的椅子重疊。
- 檢查表重新產生，`make_check_sheet.py --old` 可以給多個舊版本，三張問題圖以 v1（3D 框投影）、v2（逐像素）、新版三張並排。

| 方法 | τ (m) | precision | recall | F1 |
| --- | --- | --- | --- | --- |
| D2 幾何去重 | 0.3 | 0.83 | 0.27 | 0.41 |
| D2b 物件像素 | 0.3 | 0.95 | 0.38 | 0.55 |
| D2 幾何去重 | 0.4 | 0.73 | 0.45 | 0.56 |
| D2b 物件像素 | 0.4 | 0.96 | 0.49 | 0.65 |
| D2 幾何去重 | 0.5 | 0.64 | 0.54 | 0.58 |
| D2b 物件像素 | 0.5 | 0.93 | 0.59 | 0.72 |
| D2 幾何去重 | 0.6 | 0.52 | 0.58 | 0.55 |
| D2b 物件像素 | 0.6 | 0.56 | 0.63 | 0.59 |
| D2 幾何去重 | 0.8 | 0.34 | 0.68 | 0.45 |
| D2b 物件像素 | 0.8 | 0.33 | 0.79 | 0.47 |

- 去重重跑的結果如上表（8 個場景，真正該合併的連結 91 對，第二版是 117 對，因為重疊規則拿掉了一些框，連結也跟著變少）。D2b 在每個 τ 的 F1 都比 D2 高，最好的是 τ=0.5 的 0.72。τ 到 0.6 以上兩種方法的 precision 都掉到 0.5 左右，跟之前一樣是相鄰的同類物件被併在一起。D1 不去重的物件數平均多 8.38 個。

## 2026-09-30 Office 人類作答表

- 使用者要一份自己作答的 Office 15 題作答表。新增 `scripts/make_human_sheet.py`，輸出 `results/human_office/index.html`（不進 git，內含作者影像，也不放到任何公開頁面）。
- 頁面有 8 張標註圖（跟模型看到的同一組，附方位說明）與 15 題。作答規則跟 `runner.run_dialogue` 相同，一次只給一句，勾選所有還符合的物件，只勾一個就結束，句子用完也結束，送出後不能改。
- 正解不直接出現在頁面文字裡，只存成編碼過的字串，按「對答案」才用 `metrics.score_type_a` 同樣的公式算 SR、AS、T_A。作答進度存在瀏覽器，「下載作答紀錄」可以存成 JSON，放到 `results/human_office/answers.json` 之後可以跟模型逐題比較。
- 我用 node 檢查過頁面腳本語法，15 題的正解都能解出來。實際作答流程沒有在瀏覽器裡點過。

## 2026-09-30 M0.5 Track V 全跑（V1 四個條件各 3 次、V2 1 次）

- 模型 `claude-sonnet-5-5`，`SDA_THINKING=between_tools`，程式與試跑相同。結果在 `results/raw_visdial/`，每次重複一個檔（`__r1` 到 `__r3`），彙整表由新的 `scripts/summarize_visdial.py` 產生，存在 `results/visdial_summary.md`。上一段試跑的 3 組 multi_image 就是第 1 次的前 3 組。
- 依 CLAUDE.md 先對新條件各跑 `--limit 5`（grid、text_only、multi_image_text、V2 count），這 5 組算在第 1 次裡。先檢查過回覆的解析與名稱對應沒有問題，失敗都是模型真的答了兩個以上或答錯，才繼續全跑。
- 全部跑完後發現一個解析錯誤。multi_image_text 第 3 次的 A5，模型先回一個 JSON，後面又寫「Correction to format」再給一個 JSON，`parse_json` 用貪婪的正規表示式把兩段當成一段，解析失敗，被當成空答案。改成取最後一個完整的 JSON 物件，新增測試 `test_parse_json_takes_the_last_object`，`pytest -q` 39 passed。新增 `scripts/reparse_visdial.py`，不呼叫 API，只用存下來的回覆重新解析並重算分數。只有這一筆改變（空答案變成 chair 5、chair 6），而且不影響對話流程（前後都不是單一答案），所以直接重算，原檔備份為 `.bak`。修正前的解析成功率約 99.6%。

| 條件 | 找到比例 | SR | AS | T_A | 每次花費（美元） |
| --- | --- | --- | --- | --- | --- |
| 論文 GPT-4o | 無 | 0.866 | 0.835 | 0.860 | 無 |
| multi_image | 0.178（0.13–0.20） | 0.093 | 0.125 | 0.100（0.07–0.11） | 0.093 |
| grid | 0.200（0.20–0.20） | 0.100 | 0.150 | 0.110（0.11–0.11） | 0.034 |
| text_only | 0.000 | 0.000 | 0.000 | 0.000 | 0.092 |
| multi_image_text | 0.222（0.20–0.27） | 0.118 | 0.151 | 0.124（0.11–0.15） | 0.125 |

- 表中是 3 次的平均，括號是 3 次的範圍。3 次合計找到的次數為 multi_image_text 10、grid 9、multi_image 8、text_only 0（每個條件共 45 次）。
- 跟論文差很多。論文 GPT-4o 的 Office T_A 是 0.86，這裡最好的條件只有 0.12。最常見的失敗是只有一句話的題目，模型回兩張以上的椅子（例如「桌上有白色水瓶的那張」回 chair 3、chair 4），對話就結束了。有些題目模型選的椅子跟正解在不同張桌子。這個結果跟 PLAN.md 第 1 節 RQ0「會在同一個量級」的猜測不同，照實記下。現在還不能判斷差距來自模型、作者的提示或流程細節（作者每輪重送圖，我們用快取）、還是題目本身光看圖就有歧義。使用者的人類作答結果可以回答最後一點。
- text_only 如 PLAN.md 5.0 的預期完全答不出來，物件表沒有桌上物品，模型大多回全部 11 張椅子或猜一組。
- grid 跟 multi_image 差不多，沒有看到論文說的拼圖掉分，但 15 題太少，差 1 題就是 0.07。
- 3 次之間最後答案不一致的共 14 題次，multi_image 4、grid 3、text_only 4、multi_image_text 3，完整清單在 `results/visdial_summary.md`。例如 multi_image 的 A6，第 1、3 次答對 chair 7，第 2 次停在 chair 7、chair 8。
- V2 共 40 組，每一輪數量完全正確的比例 0.496，最後一輪正確（都是 1 個）的比例 0.850。場景之間差很多，Cafeteria_3 為 0.83 與 1.00，Classroom_4 為 0.17 與 0.40。40 組最後一輪都是 1 個，所以都要人工看 `where` 欄位才知道有沒有指對，這一步還沒做。
- Track V 到目前的實際用量合計為未快取輸入 169606、輸出 46769、cache 讀取 3017101、cache 寫入 131457 token，約 1.74 美元（含上一段試跑與 `--limit 5`，另有 2 次確認參數的極短請求不到 0.001 美元）。V1 12 次約 1.03 美元，V2 約 0.71 美元，比先前估的 2.4 美元少。

## 2026-09-30 Track V 人類基準、白板標籤、強迫選一個（C5）、V2 where 檢查表

- 使用者自己看圖作答 Office 15 題，存在 `results/human_office/answers.json`（使用者說明沒有利用題號規律）。`summarize_visdial.py` 改成讀這個檔，用 `metrics.score_type_a` 算分，並新增逐題表、寬鬆指標（最後答案集合包含正解的比例 contains）、最後答案集合的平均大小、C5 條件，以及 `--fix` 敏感度欄（還沒有用）。結果寫在 `results/visdial_summary.md`。
- 人類的結果是 15 題找對 9 題，SR 0.600、AS 0.600、T_A 0.600。A0 到 A2 停在兩張椅子，A11 到 A13 都答了比作者正解大一號的白板，A14 跟作者一致。
- 新增條件 C5 `forced_choice`。跟 multi_image 一樣，但在使用者最後一句之後加一則對話中的系統訊息（`prompts.FORCED_CHOICE`），要求只回一個最有可能的 ID。用對話中的系統訊息而不是改最上面的系統提示，是為了讓 8 張圖的快取繼續有效。`vlm.ClaudeClient` 會把這種訊息轉成純文字的 system 訊息。新增測試 `test_forced_choice_system_message_only_on_last_turn`，寫測試時發現 `ScriptedClient` 存的是訊息串列的參照，之後被 runner 改掉，改成存副本。`pytest -q` 40 passed。
- C5 先跑 `--limit 3`，3 組用了未快取輸入 444、輸出 370、cache 讀取 38094、cache 寫入 12698 token，約 0.044 美元，2 組找對，系統訊息被 API 接受，快取也有讀到。之後跑完 15 題 3 次。C5 全部合計為未快取輸入 9393、輸出 5814、cache 讀取 876162、cache 寫入 12698 token，約 0.284 美元（含試跑）。45 次的最後答案都剛好一個 ID。

| 條件 | 找到 | contains | 最後集合大小 | SR | AS | T_A |
| --- | --- | --- | --- | --- | --- | --- |
| 論文 GPT-4o | 無 | 無 | 無 | 0.866 | 0.835 | 0.860 |
| 人類（一人，同樣規則） | 0.600 | 0.800 | 1.20 | 0.600 | 0.600 | 0.600 |
| multi_image | 0.178 | 0.622 | 1.67 | 0.093 | 0.125 | 0.100 |
| grid | 0.200 | 0.489 | 2.13 | 0.100 | 0.150 | 0.110 |
| text_only | 0.000 | 0.867 | 7.67 | 0.000 | 0.000 | 0.000 |
| multi_image_text | 0.222 | 0.667 | 1.69 | 0.118 | 0.151 | 0.124 |
| forced_choice（C5） | 0.578 | 0.578 | 1.00 | 0.446 | 0.500 | 0.457（0.45–0.47） |

- 「Claude 不敢下決定」的假設得到支持。同樣的圖與對話，只要求最後一定要選一個，找到的比例從 0.18 升到 0.58，跟人類的 0.60 差不多，T_A 從 0.10 升到 0.46。C5 在 A0、A2、A5、A7、A8 這幾題 3 次都答對，multi_image 在這幾題都停在兩到三張椅子，而正解都在裡面。C5 的 T_A 仍比人類低，因為 C5 要到最後一句才被迫選，SR 會扣掉多用的句數，人類平均只用 1.07 句。
- text_only 的 contains 最高（0.867），但最後集合平均有 7.7 個，大多是把 11 張椅子全列出來，所以 contains 必須跟集合大小一起看，不能單獨解讀。
- C5 3 次之間最後答案不一致的有 3 題（A1、A3、A4），A4 三次分別答 chair 3、4、6，正解是 chair 5。
- 白板題。A11 到 A13，人類與 Claude 的五個條件（text_only 除外，它列出全部白板）都一致答 wb2、wb3、wb4，作者正解是 wb1、wb2、wb3。A14（電線旁邊的白板）人類答 wb4 跟作者一致，但 Claude 的五個條件 3 次都答 wb1。新增 `scripts/make_whiteboard_sheet.py`，輸出 `results/visdial_check/whiteboards.html`（不進 git），把 8 張圖中 5 個白板框（view 0 的 whiteboard1、view 2 與 3 的 whiteboard2、view 4 的 whiteboard3 與 4）裁成放大圖，附整張圖、作者座標（CSV 沒有 whiteboard_2）與四題對話，讓使用者選愛心、寫字、電線各在哪一塊旁邊並下載成 JSON。view 2 與 view 3 的 whiteboard2 框座標完全相同，頁面上有註明。
- 我看了裁圖，愛心在 view 2 的 whiteboard2 旁邊，寫字在 view 4 的 whiteboard3 上，電線在 view 0 的 whiteboard1 旁邊。如果這樣判斷，四題白板正解像是整組往後錯了一格（A11 應為 wb2、A12 應為 wb3、A13 應為 wb4、A14 應為 wb1），而 A14 的人類答案 wb4 反而跟圖不一致。這只是我的觀察，照使用者指示，確認前不改正解，也還沒有算敏感度欄。
- V2 where 檢查表。新增 `scripts/make_v2_check.py`，輸出 `results/v2_check/index.html`（`.gitignore` 已加入 `results/v2_check/`）。40 組各列出每一句、作者的數量、模型的數量、模型最後的 where 文字、where 提到的視角大圖（40 組都有提到視角編號）與全部 8 張小圖，可以選指對、指錯、看不出來並下載 JSON。
- 兩個新頁面的腳本都用 node 檢查過語法，沒有在瀏覽器實際點過。
- Track V 到目前的全部實際花費約 2.02 美元（未快取輸入 178999、輸出 52583、cache 讀取 3893263、cache 寫入 144155 token）。

## 2026-10-01 盤點與寫信用的事實整理（未呼叫 API）

- 這一輪只讀檔與整理，沒有呼叫任何付費 API，也沒有跑新實驗。查作者時讀了 arXiv 摘要頁與 GitHub 公開 API。
- 使用者提到的交接文檔不在 repo 裡，所以各項狀態依本檔與結果檔判斷。人類基準與 15 題逐題對照表已完成（`results/human_office/answers.json`、`results/visdial_summary.md`）。白板裁切頁部分完成，`results/visdial_check/whiteboards.html` 已做好，但還沒有使用者的判斷 JSON。C5 forced_choice 已完成（`results/raw_visdial/trackA_forced_choice__*__r1..r3.jsonl`）。V2 where 檢查表已完成，使用者 40 組都判過（`results/v2_check/answers.json`）。V2 人工判斷彙整在這一輪做完，寫在 `results/EMAIL_FACTS.md`。
- V2 人工判斷為指對 27 組、指錯 6 組、看不出來 7 組。指對占全部 0.675，不算看不出來時為 27／33 = 0.818。最後一輪數量正確的 34 組裡只有 23 組指對，數量錯誤的 6 組裡有 4 組指對。
- 從 raw 檔重算 V1 各條件，與 `visdial_summary.md` 到小數第三位一致。C5 找到 0.578、contains 0.578、T_A 0.457（3 次為 0.446、0.451、0.473），multi_image 找到 0.178、contains 0.622、T_A 0.100。
- 找到兩處說法要更正。上面 Track V 全跑那一段寫「40 組最後一輪都是 1 個」，其實是作者的數量 40 組都是 1，模型最後一輪是 1 的只有 34 組。每輪數量正確 0.496 是先算每組再平均，98 輪合併計算是 0.459。
- 作者查證。IROS 正式版作者依序為 Kuan-Lin Chen、Tzu-Ti Wei、Ming-Lun Lee、Li-Tzu Yeh、Elaine Kao、Yu-Chee Tseng、Jen-Jee Chen。GitHub CKL9001（Chen Kuan Lin）同時擁有 SDA-LLM 與 AlloEgo-VLM 兩個 repo，AlloEgo-VLM 是 arXiv 2608.15605，第一作者也是 Kuan-Lin Chen。兩篇的作者名單都沒有 Cheng-Kuan Lin。
- 新增 `results/EMAIL_FACTS.md`，三個發現各一段，每個數字都附來源檔與欄位。
- 檢查 git。這一輪之前工作區是乾淨的，先前的結果都在 commit 7556305。`data/`、`third_party/`、`results/m2_check*/`、`results/human_office/`、`results/v2_check/` 都被 `.gitignore` 擋住，`git ls-files` 也沒有列出這些路徑。這一輪新增的 `results/EMAIL_FACTS.md` 與本段還沒有 commit。

## 2026-10-01 白板判斷比對、EMAIL_FACTS 改成四點（未呼叫 API）

- 使用者的白板判斷存在 `results/visdial_check/whiteboards_answers.json`（不進 git），愛心為 whiteboard 2、寫字為 whiteboard 4、電線為 whiteboard 1。跟我前一天的判斷比，愛心與電線一致，寫字不一致（我判 whiteboard 3）。我重看 `wb/view4_full.jpg`，有算式的那塊框標 whiteboard3，whiteboard4 是空白的，使用者在作答表 A12 也答 whiteboard 3。照使用者指示，不一致時不改正解，所以沒有建立修正檔，也沒有執行 `summarize_visdial.py --fix`，`summarize_visdial.py` 沒有改動。等使用者再確認寫字那一塊。
- 讀作者 `Code/VLM.ipynb`。整本只有一個 code cell，第 41 行 `while True:`、第 43 行 `input(...)` 由人即時輸入，第 47 到 48 行輸入 `ee` 才結束，第 75 到 78 行超過 10 輪就中止，第 35 行的系統提示寫 until the unique object is confirmed by the user。存下來的輸出是人打的三輪對話，句子跟 CSV 不同。`llava.ipynb` 有同樣的迴圈，7 個 notebook 都沒有讀對話 CSV。
- 使用者說 A0 到 A2 只有一句話，查 CSV 後 A0 與 A2 是一句、A1 是兩句，人類三題最後都停在兩張椅子，已在 EMAIL_FACTS 註明。
- `results/EMAIL_FACTS.md` 改成四點，依序是照 CSV 重播達不到 0.86、Claude 不敢下決定（C5）、白板正解可能錯位、V2 數量對不等於指對，每點附一句請教語氣的信件摘要。
- 打開 Type B 的圖看場景名稱。Classroom_1 到 3 的圖是學生餐廳（餐桌、紙巾盒、取餐區、TRAY RETURN 告示），資料夾內的對話也在講取餐與餐盤回收，圖與對話一致，只有資料夾名稱寫 Classroom。順帶看到 Cafeteria_1 到 3 是會議室與辦公桌，Meeting_room_II 像教室（門旁有 D202 與給學生的告示）。只記觀察，沒有改任何程式或資料對應。
- 這一輪沒有呼叫付費 API。

## 2026-10-01 白板正解敏感度分析（未呼叫 API）

- 使用者說明白板判斷的 `writing` 原本把題目讀成「寫字那塊旁邊的白板」才選 whiteboard 4，線索本身是 whiteboard 3。`results/visdial_check/whiteboards_answers.json` 已改成 whiteboard 3 並加註記，三條線索現在跟我的判斷一致。
- 新增修正檔 `results/visdial_target_fix.json`，A11 為 whiteboard 2、A12 為 whiteboard 3、A13 為 whiteboard 4、A14 為 whiteboard 1。
- `summarize_visdial.py --fix` 原本只加一欄修正後的 T_A，改成兩欄（修正後的找到比例與 T_A）。PLAN.md 5.0 已同步把「另加一欄」改成「另加兩欄」，原因是寫信需要同時報找到比例。原始正解仍是主要結果。
- 修正後的結果（3 次平均）。人類找到 0.733、T_A 0.733。multi_image 找到 0.444、T_A 0.366。grid 找到 0.467、T_A 0.377。text_only 都是 0。multi_image_text 找到 0.489、T_A 0.391。C5 找到 0.844、T_A 0.723。Claude 四個影像條件在四題白板的 12 次答案都符合修正後的正解，人類 A14 答 wb4 從對變錯。修正後 C5 的找到比例高於人類，所有條件的 T_A 仍低於論文的 0.86。
- `results/EMAIL_FACTS.md` 第三點補上這張表，標題拿掉「兩個人的判斷還沒一致」。

## 2026-10-01 README 中文版、RESULTS.md 與 repo 整理（未呼叫 API）

- 使用者新增 `results/RESULTS.md`，並把 `README.md` 改成中文版。我逐項對照結果檔與腳本參數，大部分數字與指令都正確，例如 V1 各條件、V2 交叉表、去重表、花費 2.02 美元、`run_visdial.py` 與 `download_arkit.sh` 的參數。
- 修了五處。README 第三個觀察原本寫修正後「各條件分數都會上升」，text_only 仍是 0，改成除了 text_only 以外。RESULTS 寫「四題的 12 次答案」，其實是每題 12 次，共 48 次。RESULTS 推估 40 支可用 28 支，用 7 到 8 成的比例應為 28 到 32 支。RESULTS 說 D2 的主要失敗是 6 張椅子擠在 0.3 m 內，那是第一版（3D 框投影）時 48458417 的診斷，已註明版本。RESULTS 說資料夾錯開「在 PLAN.md 3.0 已經記下」，PLAN 只記了 Classroom_1 與 Cafeteria_2，Meeting_room_II 是新的觀察，已改清楚。
- `trackA_multi_image_text__claude-sonnet-5-5__r3.jsonl.bak` 跟現行檔比對，15 筆裡只有 A5 的 `preds` 不同（備份是空答案，現行是 chair 5、chair 6），模型回覆完全相同，確認是修正 `parse_json` 前的備份。已從 git 移除（本機檔案保留），`.gitignore` 加上 `*.bak`。`summarize_visdial.py` 只讀 `*.jsonl`，不受影響。
- 根目錄 `sda-llm-repro.zip` 在 691a4ef 被 commit 過，已從 git 移除（本機檔案保留），並加進 `.gitignore`。它仍在 git 歷史裡，如果要從歷史中徹底刪掉需要改寫歷史，這一步沒有做。
- PLAN.md 第 9 節的 README.md 改成「中文簡介」，`results/` 底下補上 RESULTS.md 一行。
- 前一輪我寫「沒有跟論文的場景表比對」，其實 PLAN.md 3.0 第 1 點早已記下資料夾名稱與論文對調的情況，這裡更正。

## 2026-10-01 白板題正解改用我們圖上的編號當主要結果（未呼叫 API）

- 使用者決定 V1 的主要結果改用「依我們圖上標籤翻譯後的正解」。規則是保留作者要找的物件，只把編號換成我們圖上的編號，只適用 A11 到 A14，其他題目照作者答案。PLAN.md 5.0 已更新並寫了原因。
- 原因先查證過。作者 `Code/VLM.ipynb` cell 0 第 10 到 17 行讀的圖在 `label/chair/` 底下，我把它存下來的輸出圖解出來看（只存在 scratchpad，沒有進 repo），8 張圖只有椅子有紅框，白板沒有框。`Code/img_bounding_box_number.ipynb` cell 0 第 24 到 25 行依 YOLO 偵測順序給編號，計數在 8 張圖之間累加（第 49 到 51 行）。所以作者答案的白板編號與公開的 LabelMe 框名稱是兩套系統。
- `results/visdial_target_fix.json` 改成每題一個物件，含 `author_target`、`target`、`author_description`、`our_label`、`reason`。理由寫明依據是圖片與描述，不是模型答案。
- `summarize_visdial.py` 的 `--fix` 改成 `--targets`，預設讀上面的檔，主表用翻譯後的正解，作者原本編號下的找到比例與 T_A 移到最後兩欄（`found, authors' numbering`、`T_A, authors' numbering`），`--targets ""` 可以全部改回作者編號。逐題表多一欄作者編號，星號依翻譯後的正解標。
- 主表的新數字（3 次平均）。人類找到 0.733、contains 0.933、T_A 0.733。multi_image 0.444、0.889、0.366。grid 0.467、0.756、0.377。text_only 0、0.867、0。multi_image_text 0.489、0.933、0.391。C5 0.844、0.844、0.723。作者原本編號下的數字跟之前相同。所有條件的 T_A 仍低於論文的 0.86。
- 記下兩個限制，這一輪都不重跑。第一，作者 `Object_Bounding_Box/color_image_3.json` 與 `color_image_2.json` 逐位元相同（`imagePath` 都是 `color_image_2.jpg`），所以我們 view 3 有一個假的 `whiteboard2` 框，我看過圖，框住的是白色 AI 字樣立牌與玻璃牆，沒有白板。第二，我們的圖畫了所有類別的框，作者評估用的圖只畫目標類別，這是重現上的差異。
- README.md、RESULTS.md、EMAIL_FACTS.md 的 V1 數字與說法同步改成以翻譯後的正解為主，作者原本編號的數字一併列出。

## 2026-10-01 C6 只框目標類別、C6f（呼叫付費 API）

- 新增 C6 `target_class_only` 與 C6f `target_class_only_forced`，PLAN.md 5.0 已寫明定義。C6 跟 multi_image 差兩件事。第一，標註圖只畫目標那一類的框與標籤（A0 到 A10 只畫椅子，A11 到 A14 只畫白板），對齊作者 `VLM.ipynb` 讀的 `label/chair/` 圖。第二，第 3 張不畫任何框，因為作者 `color_image_3.json` 與 `color_image_2.json` 逐位元相同（程式判斷標註檔跟前面某一張完全相同就不畫，不是寫死第 3 張）。這只影響白板題。C6f 是 C6 加上 C5 的最後一則系統訊息。提示詞沒有改。
- 跑之前先存圖並看過（`results/visdial_check/target_only/`，不進 git）。椅子組只有椅子有框，白板組 view 2 只有 whiteboard 2（旁邊是愛心），view 3 沒有框。
- 試跑各 `--limit 3`。C6 用了未快取輸入 229、輸出 357、cache 讀取 38094、cache 寫入 12698 token，約 0.043 美元。C6f 用了 443、296、50792、0，約 0.014 美元（讀到 C6 剛寫的椅子圖快取）。
- 試跑發現一個解析錯誤。只有一類標籤時，C6f 的模型回 `"candidate_ids": [1]` 代表 chair 1，`ids_from` 把它讀成內部編號 1（chair 1 的內部編號是 2）。改成 C6 與 C6f 把單獨的數字解讀成該類別的標籤（`ids_from` 新增 `bare_class`），其他條件的規則不變。新增測試 `test_ids_from_bare_number_means_the_drawn_class_tag`。`reparse_visdial.py` 也用同一條規則，重新解析試跑的 2 筆（A0、A2），兩筆前後都是單一答案，對話流程不受影響，備份為 `.bak`（不進 git）。先前所有條件的回覆裡都沒有單獨的數字，所以舊結果不受影響。全跑時 C6 有 5 則、C6f 有 12 則回覆用單獨的數字，都照新規則解讀。
- 另新增測試 `test_visdial_target_class_only_views`，檢查只畫目標類別、view 3 不畫框、C6f 送出的是白板組的圖而且最後一輪有系統訊息。
- 全跑 C6 與 C6f 各 15 題 × 3 次，模型 `claude-sonnet-5-5`，`SDA_THINKING=between_tools`。每次重複的花費 C6 約 0.097 美元、C6f 約 0.079 美元，兩個條件合計（含試跑）約 0.53 美元。Track V 到目前合計約 2.55 美元。

| 條件 | 找到 | contains | T_A | 找到（作者原編號） | T_A（作者原編號） |
| --- | --- | --- | --- | --- | --- |
| multi_image | 0.444 | 0.889 | 0.366 | 0.178 | 0.100 |
| C6 target_class_only | 0.533 | 0.911 | 0.416 | 0.267 | 0.149 |
| forced_choice（C5） | 0.844 | 0.844 | 0.723 | 0.578 | 0.457 |
| C6f target_class_only_forced | 0.867 | 0.867 | 0.739 | 0.600 | 0.472 |

- 回答使用者的問題。只框目標類別之後，multi_image 的找到比例從 0.444 變 0.533，T_A 從 0.366 變 0.416。C5 的找到比例從 0.844 變 0.867，T_A 從 0.723 變 0.739。
- 原本預期只框目標類別、對齊作者的圖之後，分數會明顯往論文的 0.86 靠近，結果只有小幅上升，跟預期不同。上升全部來自椅子題，3 次合計 multi_image 找到 8／33、C6 找到 12／33，C5 找到 26／33、C6f 找到 27／33，主要是 A1（檯燈那張）從 3 次都沒找到變成 3 次都找到。白板題四個條件都是 12／12，所以 view 3 不畫錯框沒有造成差別。15 題裡差 1 題就是 0.067，C6 比 multi_image 多的 0.089 約等於每次重複多找到 1.3 題，不能當成穩定的差異。C6f 的 T_A 0.739 仍低於論文的 0.86。
- 不強迫選一個時，C6 的最後集合仍常停在兩到三張椅子（平均 1.51 個），C5 與 C6f 的差距（0.53 對 0.87）遠大於框的差距（0.44 對 0.53），所以「不肯選一個」仍是主要原因。

## 2026-10-01 即時對話腳本（未呼叫 API）

- 新增 `scripts/live_dialogue.py`，照作者 `VLM.ipynb` 的方式即時對話。每題先自動送出答案檔的第一句，之後由使用者在終端機輸入，`ee` 結束，回合計數超過 10 之後結束（同作者 `if i > 10`，所以最多 11 輪），模型只回一個 ID 也結束。圖用 C6 的只框目標類別版本。系統提示是作者 `start_instruction` 原文加上共用的 JSON 輸出規則（`prompts.SYSTEM_LIVE`），加 JSON 規則是為了可靠讀出候選，這點跟作者不同，PLAN.md 5.0 有寫。
- 每一輪一收到回覆就寫進 `results/raw_visdial/live__<model>__r<rep>.jsonl`（使用者的句子、是否自動送出、模型原文、候選、時間、token），每題結束再寫一筆 end。重跑時跳過已結束的題目，中斷的題目用存下的文字重建對話後接著問。
- 輸入含數字或 view、image、photo、tag、id、第幾張、號這類字時會被擋下要求重打，對應 PLAN.md 5.0 的作答規則（只能描述看得到的特徵，不能說編號或第幾張）。
- 指標。即時對話沒有固定的 k，主要報找到比例與平均輪數，這兩個不受 k 影響。T_A 當次要參考，k 用答案檔該題的句數，SR 最低為 0，定義寫在 PLAN.md 第 7 節。
- `--dry_run` 用腳本化的模型與輸入跑 A1 與 A11，輸出到 scratchpad。A1 第一輪回 chair 1、chair 2，輸入「the chair on the right of the lamp」後回 chair 2，找到，2 輪，T_A（k=2）0.55。A11 第一輪回兩塊白板，輸入「the board in view 2」被擋下，再輸入 ee 結束，沒找到。第二次執行兩題都被跳過，續跑判斷正常。這一步沒有呼叫 API。
