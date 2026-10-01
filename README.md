# sda-llm-repro

用 Claude 小規模重新檢驗 **SDA-LLM**（*Spatial DisAmbiguation via Multi-turn Vision-Language Dialogues for Robot Navigation*，IROS 2025，arXiv 2410.12802）。

*A small-scale, independent re-examination of SDA-LLM (IROS 2025) with Claude as the vision-language model. Documentation is in Traditional Chinese.*

## 這個專案在做什麼

SDA-LLM 要解決的問題是「幫我找那張椅子」，但房間裡有很多張椅子。機器人原地每 45° 拍一張照片，共 8 張，在每個物件上標 ID，再讓視覺語言模型透過多輪對話一步步縮小候選，最後指出唯一的目標。

我重做的是第二層「語言對應到物件」，並補上論文沒有報告的幾個對照。

| 我想回答的問題 | 對應實驗 |
| --- | --- |
| 換成 Claude、用作者自己的資料，分數跟論文的 GPT-4o 差多少 | Track V（V1、V2） |
| 圖片真的有幫上忙，還是物件清單加座標就夠了 | 純文字 baseline（E3、E3b） |
| 多張圖分開送跟拼成一張圖差多少 | multi_image 對 grid（E1、E2、E5） |
| 機器人自己發問能不能更快找到目標 | 主動發問（E6） |
| 跨圖去重做不好時會怎樣 | Phase 2（D0 到 D3） |

實驗分成兩條線。**Track V** 先用作者公開的資料（[CKL9001/SDA-LLM](https://github.com/CKL9001/SDA-LLM)）重跑，**Track R** 再用 ARKitScenes 自動生成更多附正解的對話。完整計畫在 [PLAN.md](PLAN.md)，給 Claude Code 的工作規則在 [CLAUDE.md](CLAUDE.md)。

## 目前的結果

Track V 已經完成，Track R 還在前處理階段。完整整理在 [results/RESULTS.md](results/RESULTS.md)。

V1 是作者公開的 Office 場景，15 組 Type A 對話，每個條件跑 3 次取平均。

主要結果的正解是作者的答案，只有 A11 到 A14 四題白板題把作者的白板編號翻譯成我們圖上的編號（物件不變，理由見 PLAN.md 5.0）。括號內是作者原本編號下的數字。

| 條件 | 找到的比例 | T_A |
| --- | --- | --- |
| 論文 GPT-4o | 無 | 0.860 |
| 人類（我一人，同樣規則） | 0.733（0.600） | 0.733（0.600） |
| multi_image（8 張圖分開送） | 0.444（0.178） | 0.366（0.100） |
| grid（拼成一張） | 0.467（0.200） | 0.377（0.110） |
| text_only（只給物件座標表） | 0.000（0.000） | 0.000（0.000） |
| multi_image_text（圖加座標表） | 0.489（0.222） | 0.391（0.124） |
| forced_choice（最後強迫只回一個 ID） | 0.844（0.578） | 0.723（0.457） |

我目前得到四個觀察。

1. **照公開 CSV 重播對話時達不到 0.86。** 連我自己看圖作答也只有 0.733（作者原本編號下是 0.600）。作者公開的 notebook 是由人即時輸入對話，直到使用者確認才結束，我推測評估流程跟 CSV 重播不同。
2. **Claude 的錯多半是不肯選一個。** 正解常常在它的候選裡，但它停在兩三張椅子。最後強迫只回一個 ID 之後，找到的比例從 0.44 升到 0.84（作者原本編號下是 0.18 升到 0.58）。
3. **四題白板題的作者編號跟我們圖上的編號不同。** 作者評估用的圖只框目標類別，白板編號由偵測順序產生，跟公開的 LabelMe 框不同。我們把這四題的正解翻譯成我們圖上的編號，當作主要結果，作者原本編號下的分數另列。
4. **Type B 的「數量對」不等於「指對」。** 最後一輪數量正確的 34 組裡，我人工確認只有 23 組真的指到對的物件。

Track R 目前有 8 個場景、42 組對話。跨圖去重在標註框上的最佳結果是用物件像素反投影（D2b），τ = 0.5 m 時 F1 為 0.72。

這些觀察只來自 15 題與一個人的作答，規模很小，我把它們當成想請教作者的問題，不是定論。

## 進度

| 里程碑 | 狀態 |
| --- | --- |
| M0 環境 | 完成 |
| M0.5 Track V | 完成 |
| M1 ARKitScenes 讀取驗證 | 完成 |
| M2 挑場景與前處理 | 進行中（8／25 個場景） |
| M3 到 M5 Track R 實驗 | 未開始 |
| M6 跨圖去重 | 標註框版完成，YOLO 版未開始 |
| M7 報告 | 未開始 |

每一步的紀錄在 [results/LOG.md](results/LOG.md)。

## 怎麼跑

需要 Python 3.10 以上。付費呼叫一律先用 `--limit` 試跑。

```bash
pip install -e ".[dev]"
pytest -q                      # 單元測試（合成房間與作者資料）
python scripts/dry_run.py      # 不需資料與 API key 的端到端檢查

# API key 放在 SDA_API_KEY，不要設 ANTHROPIC_API_KEY，也不要寫進任何檔案
export SDA_API_KEY=...
python -m sdarepro.vlm --list  # 列出可用的模型 id
export SDA_MODEL=<model id>
export SDA_THINKING=between_tools
```

Track V（作者公開資料）

```bash
bash scripts/fetch_visdial.sh                                 # 下載到 third_party/，不進 git
python scripts/run_visdial.py --track A --cond multi_image --limit 3
python scripts/run_visdial.py --track A --cond multi_image --rep 1
python scripts/run_visdial.py --track B --cond count
python scripts/summarize_visdial.py                          # 預設讀 results/visdial_target_fix.json
```

`--cond` 可以是 `multi_image`、`grid`、`text_only`、`multi_image_text`、`forced_choice`。

Track R（ARKitScenes）

```bash
bash scripts/download_arkit.sh annotations
python scripts/select_scenes.py --n 40
bash scripts/download_arkit.sh frames data/selected_scenes.csv
python scripts/prepare_all.py
python scripts/run_dedup.py --source gt --tau 0.3 0.4 0.5 0.6 0.8
python scripts/summarize_dedup.py
python scripts/run_experiment.py --cond multi_image --limit 5   # M3 之後
python scripts/summarize.py
```

在 Windows 上如果 `python3` 會叫到 Microsoft Store 的空殼，可以用 `PYTHON=.venv/Scripts/python.exe bash scripts/download_arkit.sh ...` 指定直譯器。

## 專案結構

```
src/sdarepro/      核心程式（讀資料、投影、標註、對話生成、提示詞、Claude 客戶端、指標、去重）
scripts/           執行、彙整與人工檢查頁的產生程式
tests/             單元測試
results/           結果表、原始 JSONL 與紀錄（含影像的檢查頁不進 git）
PLAN.md            實驗計畫書，實驗定義以此為準
CLAUDE.md          給 Claude Code 的工作規則
```

## 資料與授權

- 作者公開的 SDA-LLM repo 沒有授權檔，我只在本機做個人研究，不把它的影像放進這個 repo 或任何公開頁面。
- ARKitScenes 是 Apple 以非商業研究授權釋出，影像同樣不進 git。
- `data/`、`third_party/`，以及含資料集影像的檢查頁資料夾都列在 `.gitignore`。

## 致謝

SDA-LLM 的作者是 K.-L. Chen、T.-T. Wei、M.-L. Lee、L.-T. Yeh、E. Kao、Y.-C. Tseng 與 J.-J. Chen（國立陽明交通大學）。ARKitScenes 由 Apple 釋出。這個 repo 是我個人獨立的學生重現練習，與上述作者及 Apple 都沒有隸屬關係。
