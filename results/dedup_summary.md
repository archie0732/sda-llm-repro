# Cross-view de-duplication

Precision, recall and F1 of 'same object' links, pooled over scenes. N/A = no predicted links.

| source | method | tau (m) | scenes | links (gt) | precision | recall | F1 | count error (mean) | abs count error (mean) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gt | none | - | 8 | 91 | N/A | 0.00 | 0.00 | +8.38 | 8.38 |
| gt | geometric | 0.3 | 8 | 91 | 0.83 | 0.27 | 0.41 | +5.00 | 5.00 |
| gt | geometric_mask | 0.3 | 8 | 91 | 0.95 | 0.38 | 0.55 | +4.25 | 4.25 |
| gt | geometric | 0.4 | 8 | 91 | 0.73 | 0.45 | 0.56 | +3.62 | 3.62 |
| gt | geometric_mask | 0.4 | 8 | 91 | 0.96 | 0.49 | 0.65 | +3.50 | 3.50 |
| gt | geometric | 0.5 | 8 | 91 | 0.64 | 0.54 | 0.58 | +2.38 | 2.38 |
| gt | geometric_mask | 0.5 | 8 | 91 | 0.93 | 0.59 | 0.72 | +2.50 | 2.50 |
| gt | geometric | 0.6 | 8 | 91 | 0.52 | 0.58 | 0.55 | +1.38 | 2.12 |
| gt | geometric_mask | 0.6 | 8 | 91 | 0.56 | 0.63 | 0.59 | +1.12 | 1.88 |
| gt | geometric | 0.8 | 8 | 91 | 0.34 | 0.68 | 0.45 | -0.88 | 1.88 |
| gt | geometric_mask | 0.8 | 8 | 91 | 0.33 | 0.79 | 0.47 | -1.12 | 1.62 |
