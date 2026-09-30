# Cross-view de-duplication

Precision, recall and F1 of 'same object' links, pooled over scenes. N/A = no predicted links.

| source | method | tau (m) | scenes | links (gt) | precision | recall | F1 | count error (mean) | abs count error (mean) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gt | none | - | 8 | 117 | N/A | 0.00 | 0.00 | +10.75 | 10.75 |
| gt | geometric | 0.3 | 8 | 117 | 0.62 | 0.21 | 0.32 | +7.00 | 7.00 |
| gt | geometric_mask | 0.3 | 8 | 117 | 0.94 | 0.26 | 0.41 | +7.00 | 7.00 |
| gt | geometric | 0.4 | 8 | 117 | 0.56 | 0.33 | 0.42 | +5.12 | 5.12 |
| gt | geometric_mask | 0.4 | 8 | 117 | 0.88 | 0.37 | 0.52 | +5.62 | 5.62 |
| gt | geometric | 0.5 | 8 | 117 | 0.53 | 0.43 | 0.47 | +3.88 | 3.88 |
| gt | geometric_mask | 0.5 | 8 | 117 | 0.66 | 0.50 | 0.57 | +3.12 | 3.12 |
| gt | geometric | 0.6 | 8 | 117 | 0.43 | 0.54 | 0.48 | +2.12 | 2.62 |
| gt | geometric_mask | 0.6 | 8 | 117 | 0.43 | 0.66 | 0.52 | +0.75 | 1.50 |
| gt | geometric | 0.8 | 8 | 117 | 0.24 | 0.66 | 0.35 | -0.62 | 2.12 |
| gt | geometric_mask | 0.8 | 8 | 117 | 0.30 | 0.81 | 0.43 | -1.38 | 2.12 |
