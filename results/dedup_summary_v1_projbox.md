# Cross-view de-duplication

Precision, recall and F1 of 'same object' links, pooled over scenes. N/A = no predicted links.

| source | method | tau (m) | scenes | links (gt) | precision | recall | F1 | count error (mean) | abs count error (mean) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gt | none | - | 7 | 27 | N/A | 0.00 | 0.00 | +3.57 | 3.57 |
| gt | geometric | 0.3 | 7 | 27 | 0.27 | 0.70 | 0.39 | +0.14 | 1.29 |
| gt | geometric | 0.4 | 7 | 27 | 0.25 | 0.81 | 0.39 | -0.29 | 1.43 |
| gt | geometric | 0.5 | 7 | 27 | 0.26 | 0.85 | 0.39 | -0.57 | 1.43 |
| gt | geometric | 0.6 | 7 | 27 | 0.24 | 0.85 | 0.38 | -0.86 | 1.14 |
| gt | geometric | 0.8 | 7 | 27 | 0.22 | 0.89 | 0.35 | -1.86 | 1.86 |
