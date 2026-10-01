# sda-llm-repro

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![arXiv](https://img.shields.io/badge/arXiv-2410.12802-b31b1b)](https://arxiv.org/abs/2410.12802)
[![Status](https://img.shields.io/badge/Track%20V-完成-brightgreen)](results/RESULTS.md)
[![Status](https://img.shields.io/badge/Track%20R-進行中-yellow)](results/LOG.md)

以 Claude 作為視覺語言模型，對 **SDA-LLM**（*Spatial DisAmbiguation via Multi-turn Vision-Language Dialogues for Robot Navigation*，IROS 2025，[arXiv 2410.12802](https://arxiv.org/abs/2410.12802)）進行小規模的獨立重新檢驗。

*A small-scale, independent re-examination of SDA-LLM (IROS 2025) with Claude as the vision-language model. Documentation is in Traditional Chinese.*

> 本專案為個人獨立的學生重現練習，與原論文作者及 Apple 皆無隸屬關係。

## 目錄

- [專案概述](#專案概述)
- [主要結果](#主要結果)
- [進度](#進度)
- [快速開始](#快速開始)
- [執行實驗](#執行實驗)
- [即時對話網頁](#即時對話網頁)
- [專案結構](#專案結構)
- [資料與授權](#資料與授權)
- [致謝](#致謝)

## 專案概述

SDA-LLM 處理的是指代不明確的導航指令，例如使用者說「幫我找那張椅子」，但房間裡有多張椅子。機器人在原地每 45° 拍攝一張影像，共 8 張，並在每個物件上標示 ID，再由視覺語言模型透過多輪對話逐步縮小候選範圍，最終指出唯一的目標物件。

本專案重現其中第二層「語言對應到物件」，並補上原論文未報告的幾組對照實驗。

| 研究問題 | 對應實驗 |
| --- | --- |
| 改用 Claude 並使用作者公開的資料，分數與論文中的 GPT-4o 相差多少 | Track V（V1、V2） |
| 影像是否真正有幫助，或僅提供物件清單與座標即已足夠 | 純文字 baseline（E3、E3b） |
| 多張影像分開輸入與拼接成單張影像的差異 | multi_image 對 grid（E1、E2、E5） |
| 機器人主動發問能否更快鎖定目標 | 主動發問（E6） |
| 跨影像去重效果不佳時對結果的影響 | Phase 2（D0 到 D3） |

實驗分為兩條主線。**Track V** 以作者公開的資料（[CKL9001/SDA-LLM](https://github.com/CKL9001/SDA-LLM)）重新執行，**Track R** 則以 ARKitScenes 自動生成更多附正解的對話。完整的實驗計畫請見 [PLAN.md](PLAN.md)，Claude Code 的工作規範請見 [CLAUDE.md](CLAUDE.md)。

## 主要結果

Track V 已完成，Track R 仍在前處理階段。完整的結果整理請見 [results/RESULTS.md](results/RESULTS.md)。

V1 使用作者公開的 Office 場景，共 15 組 Type A 對話，每個條件執行 3 次後取平均。

主要結果以作者的答案為正解，唯一的例外是 A11 到 A14 四題白板題，這四題將作者的白板編號轉換為本專案影像上的編號（指向的物件不變，理由見 PLAN.md 5.0）。括號內為採用作者原始編號時的數值。

| 條件 | 成功找到的比例 | T_A |
| --- | --- | --- |
| 論文 GPT-4o | 無 | 0.860 |
| 人類（作者本人一人，相同規則） | 0.733（0.600） | 0.733（0.600） |
| multi_image（8 張影像分開輸入） | 0.444（0.178） | 0.366（0.100） |
| grid（拼接為單張影像） | 0.467（0.200） | 0.377（0.110） |
| text_only（僅提供物件座標表） | 0.000（0.000） | 0.000（0.000） |
| multi_image_text（影像加座標表） | 0.489（0.222） | 0.391（0.124） |
| forced_choice（最後一輪強制只回答一個 ID） | 0.844（0.578） | 0.723（0.457） |

目前歸納出以下四項觀察。

1. **依公開 CSV 重播對話時無法達到 0.86。** 即使由我本人看圖作答，也僅達 0.733（作者原始編號下為 0.600）。作者公開的 notebook 由使用者即時輸入對話，直到使用者確認才結束，因此推測其評估流程與 CSV 重播並不相同。
2. **Claude 的錯誤多半來自不願做出單一選擇。** 正解經常已在其候選之中，但模型停留在兩三張椅子之間。最後一輪強制只回答一個 ID 後，成功比例由 0.44 提升至 0.84（作者原始編號下由 0.18 提升至 0.58）。
3. **四題白板題的作者編號與本專案影像上的編號不一致。** 作者評估用的影像只框出目標類別，白板編號依偵測順序產生，與公開的 LabelMe 標註框不同。本專案將這四題的正解轉換為自身影像上的編號作為主要結果，作者原始編號下的分數另行列出。
4. **Type B 中「數量正確」不等於「指認正確」。** 最後一輪數量正確的 34 組對話中，經人工確認僅有 23 組實際指向正確的物件。

Track R 目前已處理 8 個場景、42 組對話。在標註框上進行跨影像去重時，最佳方法為物件像素反投影（D2b），在 τ = 0.5 m 時 F1 為 0.72。

以上觀察僅來自 15 題與單一受試者的作答，樣本規模有限，應視為向原作者請教的問題，而非定論。

## 進度

| 里程碑 | 狀態 |
| --- | --- |
| M0 環境建置 | ✅ 完成 |
| M0.5 Track V | ✅ 完成 |
| M1 ARKitScenes 讀取驗證 | ✅ 完成 |
| M2 場景挑選與前處理 | 🚧 進行中（8／25 個場景） |
| M3 到 M5 Track R 實驗 | ⏳ 未開始 |
| M6 跨影像去重 | 🚧 標註框版完成，YOLO 版未開始 |
| M7 報告撰寫 | ⏳ 未開始 |

每個步驟的詳細紀錄請見 [results/LOG.md](results/LOG.md)。

## 快速開始

### 環境需求

- Python 3.10 以上
- Git，以及可執行 `scripts/*.sh` 的 bash（Windows 請安裝 [Git for Windows](https://git-scm.com/download/win)，內含 Git Bash、curl 與 unzip）
- Docker（僅在以容器啟動即時對話網頁時需要）

> 所有付費 API 呼叫一律先以 `--limit` 小量試跑，確認 token 用量後再執行完整資料集。

### 安裝與自我檢查

macOS／Linux（bash）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web]"

pytest -q                      # 單元測試（合成房間與作者資料）
python scripts/dry_run.py      # 不需資料與 API 金鑰的端到端檢查
```

Windows（PowerShell）

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1   # 若被執行原則擋下，先執行 Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install -e ".[dev,web]"

pytest -q                      # 單元測試（合成房間與作者資料）
python scripts/dry_run.py      # 不需資料與 API 金鑰的端到端檢查
```

選用套件中 `dev` 提供 pytest，`web` 提供即時對話網頁所需的 FastAPI 與 uvicorn，`detect` 提供 YOLO 偵測（ultralytics），可依需求調整。

### 設定 API 金鑰與模型

API 金鑰請放在 `SDA_API_KEY`。請勿設定 `ANTHROPIC_API_KEY`，因為該變數會讓 Claude Code 本身切換為 API 金鑰驗證，也請勿將金鑰寫入任何受版本控制的檔案。程式中不寫死任何模型 ID，一律由環境變數 `SDA_MODEL` 指定。

macOS／Linux（bash）

```bash
export SDA_API_KEY=...
python -m sdarepro.vlm --list  # 列出此金鑰可用的模型 ID
export SDA_MODEL=<model id>
export SDA_THINKING=between_tools
```

Windows（PowerShell）

```powershell
$env:SDA_API_KEY = "..."
python -m sdarepro.vlm --list  # 列出此金鑰可用的模型 ID
$env:SDA_MODEL = "<model id>"
$env:SDA_THINKING = "between_tools"
```

PowerShell 的 `$env:` 變數只在目前的視窗有效，關閉後即消失。不建議以 `setx` 將金鑰永久寫入系統環境變數。

## 執行實驗

Windows 上的 `.sh` 腳本需透過 Git Bash 執行。若 PowerShell 中的 `bash` 指向 WSL（`C:\Windows\System32\bash.exe`），請改用 Git Bash 的完整路徑，例如 `& "C:\Program Files\Git\bin\bash.exe" scripts/fetch_visdial.sh`。

### Track V（作者公開資料）

macOS／Linux（bash）

```bash
bash scripts/fetch_visdial.sh                                  # 下載至 third_party/，不進 git
python scripts/run_visdial.py --track A --cond multi_image --limit 3
python scripts/run_visdial.py --track A --cond multi_image --rep 1
python scripts/run_visdial.py --track B --cond count
python scripts/summarize_visdial.py                            # 預設讀取 results/visdial_target_fix.json
```

Windows（PowerShell）

```powershell
bash scripts/fetch_visdial.sh                                  # 下載至 third_party/，不進 git
python scripts/run_visdial.py --track A --cond multi_image --limit 3
python scripts/run_visdial.py --track A --cond multi_image --rep 1
python scripts/run_visdial.py --track B --cond count
python scripts/summarize_visdial.py                            # 預設讀取 results/visdial_target_fix.json
```

`--cond` 可選 `multi_image`、`grid`、`text_only`、`multi_image_text`、`forced_choice`。

### Track R（ARKitScenes）

下載前請先閱讀並同意 ARKitScenes 的授權條款。

macOS／Linux（bash）

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

Windows（PowerShell）

```powershell
# 讓 download_arkit.sh 使用虛擬環境的直譯器，避免 python3 叫到 Microsoft Store 的空殼
$env:PYTHON = ".venv/Scripts/python.exe"

bash scripts/download_arkit.sh annotations
python scripts/select_scenes.py --n 40
bash scripts/download_arkit.sh frames data/selected_scenes.csv
python scripts/prepare_all.py
python scripts/run_dedup.py --source gt --tau 0.3 0.4 0.5 0.6 0.8
python scripts/summarize_dedup.py
python scripts/run_experiment.py --cond multi_image --limit 5   # M3 之後
python scripts/summarize.py
```

## 即時對話網頁

除了以 CSV 重播對話，本專案也提供與作者 notebook 相同方式的即時對話，可在終端機（`scripts/live_dialogue.py`）或本機網頁（`scripts/live_web.py`）中進行。兩者共用 `src/sdarepro/live.py` 的規則、紀錄格式與評分方式，執行前需先以 `fetch_visdial.sh` 取得作者資料。

### 直接在本機執行

以下指令在 bash 與 PowerShell 中相同，於 repo 根目錄執行。

```bash
python scripts/live_dialogue.py --dry_run          # 終端機版，模擬模型與輸入，不呼叫 API
python scripts/live_dialogue.py --only A1 A11      # 終端機版，正式執行（需 SDA_API_KEY 與 SDA_MODEL）

python scripts/live_web.py --dry_run               # 網頁版，模擬模型，不呼叫 API
python scripts/live_web.py                         # 網頁版，正式執行（需 SDA_API_KEY 與 SDA_MODEL）
```

網頁版啟動後以瀏覽器開啟 http://127.0.0.1:8765 。

### 以 Docker 執行

image 只包含 `pyproject.toml`、`src/` 與 `scripts/`，作者資料與結果於啟動時以 volume 掛載。`third_party/` 為唯讀，`results/` 可寫入（網頁啟動時會在 `results/visdial_check/target_only/` 產生影像，紀錄也寫在 `results/` 底下）。因此請先在主機上取得作者資料，再於 repo 根目錄執行下列指令。

macOS／Linux（bash）

```bash
bash scripts/fetch_visdial.sh                  # 資料放在 third_party/，不進 git 也不進 image

# 模擬模式，不呼叫 API 也不需金鑰，紀錄寫在 results/demo/docker_dry_run/
docker compose --profile dry up --build

# 正式模式，金鑰只放在目前 shell 的環境變數，或寫在 .env（已列入 .gitignore）
export SDA_API_KEY=...
export SDA_MODEL=<model id>
docker compose --profile live up --build

# 停止
docker compose --profile dry down              # 或 --profile live down
```

Windows（PowerShell）

```powershell
bash scripts/fetch_visdial.sh                  # 需要 Git Bash，資料放在 third_party/，不進 git 也不進 image

# 模擬模式，不呼叫 API 也不需金鑰，紀錄寫在 results/demo/docker_dry_run/
docker compose --profile dry up --build

# 正式模式，金鑰只放在目前 PowerShell 視窗的環境變數，或寫在 .env（已列入 .gitignore）
$env:SDA_API_KEY = "..."
$env:SDA_MODEL = "<model id>"
docker compose --profile live up --build

# 停止
docker compose --profile dry down              # 或 --profile live down
```

啟動後以瀏覽器開啟 http://127.0.0.1:8765 。兩種模式都使用 8765 port，同一時間只能啟動一種。若要確認 image 中不含資料或金鑰，可執行 `docker run --rm sdarepro-web ls -R /app`。

### 網路安全設計

- `docker-compose.yml` 將 port 設為 `"127.0.0.1:8765:8765"`，僅限本機連線。若改為 `"8765:8765"`，Docker 會在主機所有網路介面開放此 port，同一網路中的任何人都能開啟網頁，看到未經授權的作者影像，正式模式下更能以你的金鑰呼叫模型。在 Linux 上，Docker 開放的 port 還會繞過 ufw 等防火牆規則。
- 容器內的伺服器必須綁定 0.0.0.0，port 對應才能連入，因此 Dockerfile 設定了 `SDA_WEB_HOST=0.0.0.0`。在本機直接執行時請勿設定此變數，預設僅綁定 127.0.0.1。
- 網頁只接受 Host 為 127.0.0.1 或 localhost 的請求。POST 請求若帶有 Origin 標頭，僅接受 http://127.0.0.1:8765 與 http://localhost:8765，以阻擋同一瀏覽器中其他網站發出的請求。

## 專案結構

```
src/sdarepro/      核心程式（資料讀取、投影、標註、對話生成、提示詞、Claude 客戶端、指標、去重）
scripts/           實驗執行、結果彙整與人工檢查頁的產生程式
tests/             單元測試
results/           結果表、原始 JSONL 與執行紀錄（含影像的檢查頁不進 git）
PLAN.md            實驗計畫書，實驗定義以此為準
CLAUDE.md          Claude Code 的工作規範
Dockerfile         即時對話網頁的容器設定
docker-compose.yml 即時對話網頁的啟動設定（dry 與 live 兩種 profile）
```

## 資料與授權

- 作者公開的 SDA-LLM repo 未附授權檔，本專案僅於本機進行個人研究，不將其影像放入此 repo 或任何公開頁面。
- ARKitScenes 由 Apple 以非商業研究授權釋出，其影像同樣不進入版本控制。
- `data/`、`third_party/` 以及含資料集影像的檢查頁資料夾皆已列入 `.gitignore`。

## 致謝

SDA-LLM 的作者為 K.-L. Chen、T.-T. Wei、M.-L. Lee、L.-T. Yeh、E. Kao、Y.-C. Tseng 與 J.-J. Chen（國立陽明交通大學）。ARKitScenes 由 Apple 釋出。本 repo 為個人獨立的學生重現練習，與上述作者及 Apple 皆無隸屬關係。
