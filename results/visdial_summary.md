# Track V results

Model(s): claude-sonnet-5-5. Every number is the mean over repeats, the range over repeats is in brackets. Type A scoring stops at the first single-ID answer (PLAN.md section 7). 'contains' is a lenient measure: the final answer set includes the target, whatever its size.

## V1 Office, Type A (15 dialogues)

| condition | repeats | dialogues per repeat | found | contains | final set size | SR | AS | T_A | turns used | cost per repeat (USD) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| paper, GPT-4o | 1 | 15 | - | - | - | 0.866 | 0.835 | 0.860 | - | - |
| human (same protocol, one person) | 1 | 15 | 0.600 | 0.800 | 1.20 | 0.600 | 0.600 | 0.600 | 1.067 | - |
| multi_image | 3 | 15 | 0.178 [0.13–0.20] | 0.622 [0.60–0.67] | 1.667 [1.53–1.80] | 0.093 [0.07–0.11] | 0.125 [0.10–0.14] | 0.100 [0.07–0.11] | 1.556 [1.53–1.60] | 0.093 |
| grid | 3 | 15 | 0.200 [0.20–0.20] | 0.489 [0.47–0.53] | 2.133 [1.80–2.33] | 0.100 [0.10–0.10] | 0.150 [0.15–0.15] | 0.110 [0.11–0.11] | 1.644 [1.60–1.67] | 0.034 |
| text_only | 3 | 15 | 0.000 [0.00–0.00] | 0.867 [0.73–0.93] | 7.667 [7.00–8.33] | 0.000 [0.00–0.00] | 0.000 [0.00–0.00] | 0.000 [0.00–0.00] | 1.667 [1.67–1.67] | 0.092 |
| multi_image_text | 3 | 15 | 0.222 [0.20–0.27] | 0.667 [0.67–0.67] | 1.689 [1.60–1.80] | 0.118 [0.11–0.14] | 0.151 [0.14–0.18] | 0.124 [0.11–0.15] | 1.533 [1.53–1.53] | 0.125 |
| forced_choice | 3 | 15 | 0.578 [0.53–0.60] | 0.578 [0.53–0.60] | 1.000 [1.00–1.00] | 0.446 [0.44–0.46] | 0.500 [0.47–0.51] | 0.457 [0.45–0.47] | 1.556 [1.47–1.67] | 0.095 |

## Per dialogue: final answers

Chair numbers are shown bare (3 = chair 3), wb2 = whiteboard 2. Each condition cell lists the final answer of repeats 1 / 2 / 3, and * marks a correct single answer.

| # | first sentence | author target | human | multi_image | grid | text_only | multi_image_text | forced_choice |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A0 | chair closest to the glass wall. | 1 | 1,2 | 1,2 / 1,2 / 1,2 | 1,2,3,4,5,6 / 1,2,3,4 / 1,2,3,4,5,6 | 1,6,9,10 / 1,2,6,9,10 / 6,9,10 | 1,2 / 1,2 / 1,2,10,11 | 1* / 1* / 1* |
| A1 | chair with the desk lamp on the table. | 2 | 1,2 | 4 / 3,4 / 3,4 | 2* / 2* / 2* | 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 / 10,11 | 2* / 3,4 / 2,4 | 3 / 4 / 3 |
| A2 | chair with the white water bottle on the table. | 3 | 3,4 | 3,4 / 3,4 / 3,4 | 7,8,9 / 7,8,9 / 7,8,9 | 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 | 3,4 / 3,4 / 3,4 | 3* / 3* / 3* |
| A3 | chair with the books on the table. | 4 | 4* | 3,4 / 3 / 3,4 | 5,6,7,8,9 / 11 / 5,6,7,8,9 | 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 | 3,4 / 3,4 / 3,4 | 3 / 4* / 4* |
| A4 | chair with an umbrella on the table. | 5 | 5* | 6 / 5,6 / 3,4,5,6 | 6 / 6 / 6 | 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 | 4,6 / 5,6 / 4,6 | 3 / 4 / 6 |
| A5 | chair with the fire extinguisher on the table. | 6 | 6* | 5,6 / 5,6 / 5,6 | 5,6 / 5,6 / 5,6 | 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 | 5,6 / 5,6 / 5,6 | 6* / 6* / 6* |
| A6 | chair with the paint bucket on the table. | 7 | 7* | 7* / 7,8 / 7* | 7,8,9 / 7,8,9 / 7,8,9 | 5,6,9,10,11 / 5,6,9,10,11 / 6,9,11 | 7* / 7* / 7* | 7* / 7* / 7* |
| A7 | chair with the safety helmet on the table. | 8 | 8* | 7,8,9 / 7,8,9 / 7,8,9 | 7,8,9 / 7,8,9 / 7,8,9 | 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 | 7,8,9 / 7,8,9 / 7,8,9 | 8* / 8* / 8* |
| A8 | chair with the laptop on the table. | 9 | 9* | 7,8,9 / 7,8,9 / 7,8,9 | 1,2,7,8 / 1,2,8 / 1,2,7,8,9 | 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 | 7,8,9 / 7,8,9 / 7,8,9 | 9* / 9* / 9* |
| A9 | chair with many cardboard boxes on the table. | 10 | 10* | 10* / 10* / 10* | 10* / 10* / 10* | 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 / 1,2,3,4,5,6,7,8,9,10,11 | 10* / 10* / 10* | 10* / 10* / 10* |
| A10 | chair with many cardboard boxes on the table. | 11 | 11* | 11* / 11* / 11* | 11* / 11* / 11* | 10,11 / 1,2,3,4,5,6,7,8,9,10,11 / 3,4,7,8 | 11* / 11* / 11* | 11* / 11* / 11* |
| A11 | whiteboard with a heart next to it. | wb1 | wb2 | wb2 / wb2 / wb2 | wb2 / wb2 / wb2 | wb1,wb2,wb3,wb4 / wb1,wb2,wb3,wb4 / wb1,wb2,wb3,wb4 | wb2 / wb2 / wb2 | wb2 / wb2 / wb2 |
| A12 | whiteboard with writing on it. | wb2 | wb3 | wb3 / wb3 / wb3 | wb3 / wb3 / wb3 | wb1,wb2,wb3,wb4 / wb1,wb2,wb3,wb4 / wb1,wb2,wb3,wb4 | wb3 / wb3 / wb3 | wb3 / wb3 / wb3 |
| A13 | whiteboard next to the whiteboard with writing on it. | wb3 | wb4 | wb4 / wb4 / wb4 | wb4 / wb4 / wb4 | wb1,wb2,wb3,wb4 / wb1,wb2,wb3,wb4 / wb1,wb2,wb3,wb4 | wb4 / wb4 / wb4 | wb4 / wb4 / wb4 |
| A14 | whiteboard next to the cable. | wb4 | wb4* | wb1 / wb1 / wb1 | wb1 / wb1 / wb1 | wb1,wb2,wb3,wb4 / wb1,wb2,wb3,wb4 / wb1,wb2,wb3,wb4 | wb1 / wb1 / wb1 | wb1 / wb1 / wb1 |

## Dialogues whose final answer differs between repeats

- multi_image A1，目標 chair 2。第 1 次 {chair 4}，第 2 次 {chair 3, chair 4}，第 3 次 {chair 3, chair 4}。對話為 Help me find the chair with the desk lamp on the table. / Help me find the chair with the desk lamp on the table, the one on the right.
- multi_image A3，目標 chair 4。第 1 次 {chair 3, chair 4}，第 2 次 {chair 3}，第 3 次 {chair 3, chair 4}。對話為 Help me find the chair with the books on the table. / Help me find the chair with the books on the table, where there is a water bottle to the left of the books. / Help me find the chair with the books on the table, where there is a water bottle to the left of the books and an umbrella to the right of the books.
- multi_image A4，目標 chair 5。第 1 次 {chair 6}，第 2 次 {chair 5, chair 6}，第 3 次 {chair 3, chair 4, chair 5, chair 6}。對話為 Help me find the chair with an umbrella on the table. / Help me find the chair to the right of the umbrella.
- multi_image A6，目標 chair 7。第 1 次 {chair 7} 對，第 2 次 {chair 7, chair 8}，第 3 次 {chair 7} 對。對話為 Help me find the chair with the paint bucket on the table. / Help me find the chair with the paint bucket on the table, with a recessed wall behind it. / Help me find the chair with the paint bucket on the table, with a recessed wall behind it and a backpack in front of it. / Help me find the chair with the paint bucket on the table, with a recessed wall behind it, a backpack in front of it, and positioned between two windows. / Help me find the chair with the paint bucket on the table, with a recessed wall behind it, a backpack in front of it, positioned between two windows, and with a safety helmet on the right side.
- grid A0，目標 chair 1。第 1 次 {chair 1, chair 2, chair 3, chair 4, chair 5, chair 6}，第 2 次 {chair 1, chair 2, chair 3, chair 4}，第 3 次 {chair 1, chair 2, chair 3, chair 4, chair 5, chair 6}。對話為 Help me find the chair closest to the glass wall.
- grid A3，目標 chair 4。第 1 次 {chair 5, chair 6, chair 7, chair 8, chair 9}，第 2 次 {chair 11}，第 3 次 {chair 5, chair 6, chair 7, chair 8, chair 9}。對話為 Help me find the chair with the books on the table. / Help me find the chair with the books on the table, where there is a water bottle to the left of the books. / Help me find the chair with the books on the table, where there is a water bottle to the left of the books and an umbrella to the right of the books.
- grid A8，目標 chair 9。第 1 次 {chair 1, chair 2, chair 7, chair 8}，第 2 次 {chair 1, chair 2, chair 8}，第 3 次 {chair 1, chair 2, chair 7, chair 8, chair 9}。對話為 Help me find the chair with the laptop on the table.
- text_only A0，目標 chair 1。第 1 次 {chair 1, chair 6, chair 9, chair 10}，第 2 次 {chair 1, chair 2, chair 6, chair 9, chair 10}，第 3 次 {chair 6, chair 9, chair 10}。對話為 Help me find the chair closest to the glass wall.
- text_only A1，目標 chair 2。第 1 次 {chair 1, chair 2, chair 3, chair 4, chair 5, chair 6, chair 7, chair 8, chair 9, chair 10, chair 11}，第 2 次 {chair 1, chair 2, chair 3, chair 4, chair 5, chair 6, chair 7, chair 8, chair 9, chair 10, chair 11}，第 3 次 {chair 10, chair 11}。對話為 Help me find the chair with the desk lamp on the table. / Help me find the chair with the desk lamp on the table, the one on the right.
- text_only A6，目標 chair 7。第 1 次 {chair 5, chair 6, chair 9, chair 10, chair 11}，第 2 次 {chair 5, chair 6, chair 9, chair 10, chair 11}，第 3 次 {chair 6, chair 9, chair 11}。對話為 Help me find the chair with the paint bucket on the table. / Help me find the chair with the paint bucket on the table, with a recessed wall behind it. / Help me find the chair with the paint bucket on the table, with a recessed wall behind it and a backpack in front of it. / Help me find the chair with the paint bucket on the table, with a recessed wall behind it, a backpack in front of it, and positioned between two windows. / Help me find the chair with the paint bucket on the table, with a recessed wall behind it, a backpack in front of it, positioned between two windows, and with a safety helmet on the right side.
- text_only A10，目標 chair 11。第 1 次 {chair 10, chair 11}，第 2 次 {chair 1, chair 2, chair 3, chair 4, chair 5, chair 6, chair 7, chair 8, chair 9, chair 10, chair 11}，第 3 次 {chair 3, chair 4, chair 7, chair 8}。對話為 Help me find the chair with many cardboard boxes on the table. / Help me find the chair with many cardboard boxes on the table, the one on the right.
- multi_image_text A0，目標 chair 1。第 1 次 {chair 1, chair 2}，第 2 次 {chair 1, chair 2}，第 3 次 {chair 1, chair 2, chair 10, chair 11}。對話為 Help me find the chair closest to the glass wall.
- multi_image_text A1，目標 chair 2。第 1 次 {chair 2} 對，第 2 次 {chair 3, chair 4}，第 3 次 {chair 2, chair 4}。對話為 Help me find the chair with the desk lamp on the table. / Help me find the chair with the desk lamp on the table, the one on the right.
- multi_image_text A4，目標 chair 5。第 1 次 {chair 4, chair 6}，第 2 次 {chair 5, chair 6}，第 3 次 {chair 4, chair 6}。對話為 Help me find the chair with an umbrella on the table. / Help me find the chair to the right of the umbrella.
- forced_choice A1，目標 chair 2。第 1 次 {chair 3}，第 2 次 {chair 4}，第 3 次 {chair 3}。對話為 Help me find the chair with the desk lamp on the table. / Help me find the chair with the desk lamp on the table, the one on the right.
- forced_choice A3，目標 chair 4。第 1 次 {chair 3}，第 2 次 {chair 4} 對，第 3 次 {chair 4} 對。對話為 Help me find the chair with the books on the table. / Help me find the chair with the books on the table, where there is a water bottle to the left of the books. / Help me find the chair with the books on the table, where there is a water bottle to the left of the books and an umbrella to the right of the books.
- forced_choice A4，目標 chair 5。第 1 次 {chair 3}，第 2 次 {chair 4}，第 3 次 {chair 6}。對話為 Help me find the chair with an umbrella on the table. / Help me find the chair to the right of the umbrella.

## V2 Type B, object counts (40 dialogues)

| repeats | dialogues | per-turn count exact | last turn exact | last turn count is 1 (needs a human check of `where`) | cost (USD) |
| --- | --- | --- | --- | --- | --- |
| 1 | 40 | 0.496 | 0.850 | 40 | 0.706 |

| scene | dialogues | per-turn exact | last turn exact |
| --- | --- | --- | --- |
| Cafeteria_1 | 5 | 0.37 | 0.80 |
| Cafeteria_2 | 5 | 0.73 | 1.00 |
| Cafeteria_3 | 5 | 0.83 | 1.00 |
| Classroom_1 | 5 | 0.53 | 1.00 |
| Classroom_2 | 5 | 0.42 | 0.80 |
| Classroom_3 | 5 | 0.42 | 0.80 |
| Classroom_4 | 5 | 0.17 | 0.40 |
| Meeting_room_II | 5 | 0.50 | 1.00 |

## Tokens and cost

Uncached input 178999, output 52583, cache read 3893263, cache write 144155 tokens. At 2.0/10.0/0.2/2.5 USD per million (input/output/cache read/cache write) this is 2.023 USD.
