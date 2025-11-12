import json
from pathlib import Path

import numpy as np
import pandas as pd

bank = Path('data') / 'ch-ng-1-question-bank-20251111-202150.json'
out = Path('data') / 'simulated_responses.csv'

items = json.loads(bank.read_text(encoding='utf-8'))
ids = [str(it['id']) for it in items]

n_respondents = 200
# simulate binary responses with p(correct) varying by item difficulty proxy using param_a/param_b if available
ps = []
for it in items:
    a = float(it.get('param_a', 1.0) or 1.0)
    b = float(it.get('param_b', 0.0) or 0.0)
    # simple logistic to get base p
    p = 1.0 / (1.0 + np.exp(- (a * (-b))))
    # clamp
    p = float(np.clip(p, 0.08, 0.92))
    ps.append(p)

arr = np.zeros((n_respondents, len(ids)), dtype=int)
for j, p in enumerate(ps):
    arr[:, j] = np.random.binomial(1, p, size=n_respondents)

df = pd.DataFrame(arr, columns=ids)
df.to_csv(out, index=False)
print(f'Wrote simulated responses to {out} ({n_respondents}x{len(ids)})')
