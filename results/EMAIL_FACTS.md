# 寫信用的事實整理（2026-10-01 第二版）

這份文件裡的數字都是從結果檔重新讀出來的，沒有呼叫任何付費 API。計算直接讀 `results/raw_visdial/*.jsonl`、`results/human_office/answers.json`、`results/v2_check/answers.json`、`results/visdial_check/whiteboards_answers.json`，以及作者 repo `third_party/SDA-LLM`（commit c10ac74）裡的檔案。模型是 `claude-sonnet-5-5`（每筆紀錄的 `model` 欄），`SDA_THINKING=between_tools`。

V1 是 Office 的 15 題對話，每個條件跑 3 次，每次一個檔，例如 `trackA_multi_image__claude-sonnet-5-5__r1.jsonl` 到 `__r3.jsonl`。「找到」是每筆的 `found` 欄，T_A 是每筆的 `T_A` 欄，「contains」是 `target` 是否在 `preds` 最後一項裡，「最後集合大小」是 `preds` 最後一項的長度。先在每個檔內平均，再對 3 個檔平均。raw 檔的物件內部編號是作者編號加一（chair 1 是 2），白板 whiteboard 1 到 4 是 14 到 17。

四個發現依序如下，每一點最前面是可以直接放進信裡的一句話。

## 一 照 CSV 重播對話時達不到論文的 0.86

信裡可以這樣寫。我們照公開 CSV 一句一句重播 Office 的 15 題，連人自己看圖作答也只有 T_A 0.600，所以想請教論文 0.86 的評估流程是不是跟 CSV 重播不同，例如由實驗者即時對話、追問到確認為止。

- 人類（使用者本人）照同樣規則作答，找到 9／15 = 0.600，T_A 0.600。找到數來自 `results/human_office/answers.json` 的 `answers.<題號>.picks`，對照 raw 檔的 `target`。T_A 引自 `results/visdial_summary.md` 第一張表（`metrics.score_type_a` 算出）。論文 GPT-4o 的 0.860 引自 PLAN.md 第 1 節 RQ0。
- A0 與 A2 在 CSV 裡只有一句話（raw 檔 `gt_sets` 長度為 1，`Office_Multi-turn_dialogue.csv` 第 2、4 列只有第一欄有句子）。A1 有兩句。人類在這三題最後都停在兩張椅子，A0 與 A1 是 chair 1、chair 2，A2 是 chair 3、chair 4，正解都在其中。照 CSV 重播時沒有下一句可以再縮小範圍。
- 使用者原本說 A0 到 A2 都只有一句話，其實 A1 有兩句，但第二句「the one on the right」之後人類仍選兩張，結論不變。
- Claude 的 multi_image 在 A0 到 A2 三次也都沒有找到（raw 檔 `found` 皆為 false）。C5 強迫選一個時 A0 與 A2 三次都猜對，A1 三次都錯，所以這兩題能不能答對要靠「猜」，不是靠句子提供的資訊。
- 作者的 `Code/VLM.ipynb` 只有一個 code cell（cell 0，`execution_count` 為空），GPT-4o 的對話迴圈是人即時輸入，不是讀 CSV。關鍵行如下（cell 0 內的行號）。
  - 第 35 行，系統提示寫 `... Use each round of user input to refine your guesses until the unique object is confirmed by the user.`
  - 第 41 行 `while True:`
  - 第 43 行 `user_input = input("請輸入描述（輸入 'ee' 來結束）：")`
  - 第 47 到 48 行，使用者輸入 `ee` 才 `break`
  - 第 75 到 78 行，超過 10 輪時印出 `please ask again`、清空訊息並 `break`
  - 迴圈裡沒有「模型只回一個 ID 就停」的判斷。
- 同一個 cell 存下來的輸出是一段由人打字的三輪對話，句子跟 CSV 不同。例如第 2 輪是「Can you find the chair next to the table with the books on it?」，CSV 的 Question 4 是「Help me find the chair with the books on the table.」。第 3 輪 GPT-4o 回 Chair 3 之後，使用者輸入 `ee` 結束。
- `Code/llava.ipynb` cell 0 有同樣的迴圈（第 39 行 `while True:`、第 41 行 `input(...)`）。作者 7 個 notebook 都沒有讀 `*_Multi-turn_dialogue.csv` 的程式，`main.ipynb` 讀的 CSV 是深度資料（cell 3 第 75 行、cell 4 第 93 行的 `pd.read_csv(depthinfo_path)`）。
- 這些只說明公開程式是人即時對話，不能證明論文的 0.86 就是這樣算的，所以要用請教的語氣。

## 二 Claude 的錯多半是不肯選一個，強迫選一個之後接近人類

信裡可以這樣寫。我們用 Claude 重跑時發現它常把正解留在兩三個候選裡不肯收斂，加一句「請只回一個最可能的 ID」之後找到比例從 0.18 升到 0.58，想請教 GPT-4o 在你們的實驗裡是否也有類似情況，或提示詞有沒有其他讓它收斂的設計。

| 條件 | 找到（3 次平均） | 3 次各自找到幾題 | contains | 最後集合大小 | T_A（3 次平均） | T_A 3 次各自 |
| --- | --- | --- | --- | --- | --- | --- |
| 論文 GPT-4o | 無 | 無 | 無 | 無 | 0.860 | 無 |
| 人類（一人） | 0.600 | 9 | 0.800 | 1.20 | 0.600 | 無 |
| multi_image | 0.178 | 3、2、3 | 0.622 | 1.667 | 0.100 | 0.113、0.073、0.113 |
| forced_choice（C5） | 0.578 | 8、9、9 | 0.578 | 1.000 | 0.457 | 0.446、0.451、0.473 |

- multi_image 與 C5 的數字來自 `results/raw_visdial/trackA_multi_image__claude-sonnet-5-5__r{1,2,3}.jsonl` 與 `trackA_forced_choice__claude-sonnet-5-5__r{1,2,3}.jsonl` 的 `found`、`T_A`、`target`、`preds` 欄。
- 人類的 contains 是最後勾選含正解的題數 12／15，來源同上一點。
- 只看椅子題（A0 到 A10，3 次共 33 題次），multi_image 找到 8 次，C5 找到 26 次。C5 在 A0、A2、A5、A7、A8 三次都對，multi_image 在這五題三次都停在兩到三張椅子，而且正解都在集合裡。
- multi_image 的 contains 0.622 遠高於找到 0.178，表示多數時候正解有在候選裡，只是沒有縮到一個。
- C5 仍有不穩定的題目。A4 三次分別答 chair 3、chair 4、chair 6，正解是 chair 5。A1 三次都錯。
- 只有 15 題、一個場景、一個模型，差 1 題就是 0.067。

## 三 Office 四題白板的作者正解可能錯位（兩個人的判斷還沒一致）

信裡可以這樣寫。Office 的四題白板題，人和 Claude 在前三題都一致答成作者正解的下一號白板，想請教這四題的正解標註是否可能有錯位，或是我們對「旁邊」的理解跟你們不同。

| 題號 | 第一句 | 作者正解 | 人類作答 | Claude 四個影像條件 3 次（共 12 次） |
| --- | --- | --- | --- | --- |
| A11 | whiteboard with a heart next to it | wb1 | wb2 | 12 次都是 wb2 |
| A12 | whiteboard with writing on it | wb2 | wb3 | 12 次都是 wb3 |
| A13 | whiteboard next to the whiteboard with writing on it | wb3 | wb4 | 12 次都是 wb4 |
| A14 | whiteboard next to the cable | wb4 | wb4 | 12 次都是 wb1 |

- Claude 的答案來自 multi_image、grid、multi_image_text、forced_choice 各 3 個 raw 檔的 `preds` 最後一項，作者正解來自同一筆的 `target`。text_only 3 次都列出全部 4 塊白板，不算在內。人類作答來自 `results/human_office/answers.json` 的 `A11` 到 `A14`。

使用者看裁切圖後的判斷（`results/visdial_check/whiteboards_answers.json`，2026-10-01 存檔）與我在 LOG.md 2026-09-30 寫下的判斷比較如下。

| 線索 | 使用者判斷 | Claude 判斷 | 一致 |
| --- | --- | --- | --- |
| 愛心（`heart`） | whiteboard 2 | whiteboard 2（view 2） | 是 |
| 寫字（`writing`） | whiteboard 4 | whiteboard 3（view 4） | 否 |
| 電線（`cable`） | whiteboard 1 | whiteboard 1（view 0） | 是 |

- 寫字這一項不一致。我重看了 `results/visdial_check/wb/view4_full.jpg`，寫著「What is ∠B?」與餘弦定理算式的那一塊，框的標籤是 whiteboard3，右邊標 whiteboard4 的那一塊是空白的。使用者在作答表 A12（with writing on it）也是答 whiteboard 3。所以這一項可能是裁切頁上點錯，也可能是使用者對框的理解跟我不同，需要使用者再看一次。
- 照指示，判斷不一致時不改正解，所以這一輪沒有建立修正檔，也沒有執行 `summarize_visdial.py --fix`，敏感度欄還沒有數字。
- 如果兩人最後都同意寫字在 whiteboard 3，四題正解就像整組往後錯一格（A11 應為 wb2、A12 應為 wb3、A13 應為 wb4、A14 應為 wb1）。如果寫字是在 whiteboard 4，則 A12 應為 wb4，A13 要看 wb4 旁邊是哪一塊，錯位的說法就不成立。

## 四 V2 數量答對不代表指對了物件

信裡可以這樣寫。Type B 只有數量的正解，我們另外人工看了模型描述的位置，發現最後一輪數量對的 34 組裡只有 23 組真的指到對的物件，想請教論文的 Type B 是否也只用數量評分，以及有沒有保留每題實際指的是哪一個物件。

| 項目 | 數字 | 來源 |
| --- | --- | --- |
| 對話數 | 40 | `results/raw_visdial/trackB_count__claude-sonnet-5-5__r1.jsonl` 行數 |
| 每輪數量完全正確（先算每組再平均） | 0.496 | 同檔 `count_exact_rate` 欄的平均 |
| 每輪數量完全正確（98 輪合併計算） | 45／98 = 0.459 | 同檔 `turns[].gt` 與 `turns[].pred` |
| 最後一輪數量正確 | 34／40 = 0.850 | 同檔 `final_exact` 欄 |
| 作者最後一輪數量為 1 | 40／40 | 同檔 `turns[-1].gt` |
| 模型最後一輪數量為 1 | 34／40 | 同檔 `turns[-1].pred` |
| 使用者判為指對 | 27 | `results/v2_check/answers.json` 的 `verdict` 欄 |
| 使用者判為指錯 | 6 | 同上 |
| 使用者判為看不出來 | 7 | 同上 |
| AR（指對／全部 40 組） | 27／40 = 0.675 | 同上 |
| AR（指對／指對加指錯，不算看不出來） | 27／33 = 0.818 | 同上 |

最後一輪數量正確與人工判斷的交叉表（`final_exact` 對 `verdict`）。

| | 指對 | 指錯 | 看不出來 | 合計 |
| --- | --- | --- | --- | --- |
| 數量正確 | 23 | 5 | 6 | 34 |
| 數量錯誤 | 4 | 1 | 1 | 6 |
| 合計 | 27 | 6 | 7 | 40 |

- 數量正確的 34 組裡只有 23 組指對（0.676），數量錯誤的 6 組裡反而有 4 組指對。只看數量的 0.850 會高估模型真的找到物件的比例。
- 兩種 AR 的定義是我依手上的資料推的，若交接文檔的定義不同，以它為準再重算。

13 組問題案例（6 組指錯、7 組看不出來），作者數量與模型數量依輪次列出，`where` 只摘前段。

| 對話 | 判斷 | 作者數量 | 模型數量 | 模型最後的 where（摘要） |
| --- | --- | --- | --- | --- |
| Cafeteria_1-B3 | 指錯 | 3、2、1 | 1、1、1 | view 7 黃色檯面上的消毒濕巾罐 |
| Cafeteria_1-B4 | 指錯（使用者註記 view4、view5 有板擦） | 2、1 | 0、0 | 說桌上找不到板擦 |
| Classroom_1-B3 | 指錯 | 2、1 | 1、1 | view 3 玻璃門右邊牆上的消毒液機 |
| Classroom_1-B4 | 指錯 | 1 | 1 | view 6 後方取餐區旁的小平板 |
| Classroom_2-B0 | 指錯 | 3、1 | 3、1 | view 1 後方左側的玻璃雙開門 |
| Meeting_room_II-B4 | 指錯 | 75、2、1 | 3、2、1 | view 2 右後方桌上的書 |
| Cafeteria_3-B1 | 看不出來 | 1 | 1 | view 0 與 1 長木檯上的乾洗手瓶 |
| Classroom_2-B1 | 看不出來 | 25、10、6、1 | 40、6、1、1 | view 3 前景的矮圓桌 |
| Classroom_2-B2 | 看不出來 | 30、10、1 | 40、6、1 | view 7 左中的高腳圓桌 |
| Classroom_3-B0 | 看不出來 | 1 | 1 | view 2 與 3 藍色門右邊的 TRAY RETURN 告示 |
| Classroom_3-B3 | 看不出來 | 25、15、3、1 | 24、無法解析、1、1 | view 0 中央的灰色吊燈 |
| Classroom_3-B4 | 看不出來 | 1 | 2 | view 2 與 3 公告欄下方的綠色容器 |
| Meeting_room_II-B1 | 看不出來 | 30、3、2、1 | 25、3、1、1 | view 2 右後方紙箱旁的紅色旋轉椅 |

- 判斷與註記來自 `results/v2_check/answers.json`，數量來自 raw 檔的 `turns[].gt` 與 `turns[].pred`，where 來自 `turns[-1].where`。Classroom_3-B3 第 2 輪的 `pred` 是 null。

## Type B 資料夾名稱與內容（只記觀察）

- 我打開了 `results/v2_check/img/` 的圖（由作者 `Dataset/Type_B_Dataset/` 各資料夾的 8 張圖縮小而來），看了 Classroom_1 view 0、Classroom_2 view 1、Classroom_3 view 2、Cafeteria_1 view 0、Cafeteria_2 view 0、Cafeteria_3 view 0、Meeting_room_II view 0。
- Classroom_1 到 3 的圖是學生餐廳，有成排的餐桌、桌上的紙巾盒與鹽罐、高腳桌、取餐區，Classroom_3 view 2 的藍色門旁有 TRAY RETURN 告示。資料夾裡 CSV 的對話也在講取餐線、午餐付款的 iPad、餐盤回收、鹽罐、叉子，所以圖和對話彼此是一致的，只有資料夾名稱寫 Classroom。
- 順帶看到 Cafeteria_1 view 0 是有兩台螢幕和會議桌的會議室，Cafeteria_2 與 Cafeteria_3 view 0 是黃牆的辦公桌，對話在講白板筆、滑鼠、QR code、板擦。Meeting_room_II view 0 是教室門口，牆上有教室編號 D202 與給學生的告示。
- 看起來三類名稱跟內容像是互相錯開（Classroom 資料夾是餐廳、Cafeteria 資料夾是會議室與辦公區、Meeting_room_II 像教室）。這只是看圖的觀察，Classroom_4 沒有打開，也沒有跟論文的場景表比對。如果要寫進信裡，建議當成順帶一提的小問題。

## 和現有文件的差異

使用者提到的交接文檔不在 repo 裡，所以下面是跟 `results/LOG.md` 與 `results/visdial_summary.md` 比對的結果。V1 各條件的找到、contains、集合大小、SR、AS、T_A 重算後與 `visdial_summary.md` 第一張表到小數第三位一致。

- LOG.md 2026-09-30 Track V 全跑那一段寫「40 組最後一輪都是 1 個」。作者的最後一輪數量 40 組都是 1，但模型的最後一輪數量只有 34 組是 1。`visdial_summary.md` 的欄名「last turn count is 1」指的是作者的數量。
- 「每輪數量完全正確 0.496」是先算每組再平均，98 輪合併計算是 0.459。
- 使用者這一輪的指示說 A0 到 A2 都只有一句話，CSV 裡 A1 其實有兩句。

## SDA-LLM 作者與 GitHub 帳號

- IROS 2025 正式版（`third_party/SDA-LLM/IROS25_2024_FI.pdf` 第一頁，與附 DOI 10.1109/IROS60139.2025.11246115 的下載版相同）作者依序為 Kuan-Lin Chen、Tzu-Ti Wei、Ming-Lun Lee、Li-Tzu Yeh、Elaine Kao、Yu-Chee Tseng、Jen-Jee Chen，註腳寫作者都在陽明交大人工智慧學院。
- arXiv 2410.12802 v1（2024-09-30）題目是 Resolving Positional Ambiguity in Dialogues by Vision-Language Models for Robot Navigation，作者比正式版少 Ming-Lun Lee。
- GitHub CKL9001 顯示名稱 Chen Kuan Lin，沒有填 bio、公司或地點，公開 repo 只有 SDA-LLM 與 AlloEgo-VLM，SDA-LLM 的 commit 作者都是 Chen Kuan Lin。
- AlloEgo-VLM 是 arXiv 2608.15605（2026-08-16），作者依序為 Kuan-Lin Chen、Tzu-Ti Wei、Chao-Chi Liao、Yu-Chee Tseng、Jen-Jee Chen。
- 兩篇的作者名單都沒有 Cheng-Kuan Lin。證據支持 CKL9001 是第一作者 Kuan-Lin Chen，沒有找到任何證據顯示它是林政寬老師。
