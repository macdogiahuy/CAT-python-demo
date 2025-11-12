import json
from pathlib import Path

import numpy as np
import pandas as pd

bank = Path('data') / 'Java_Course_150_questions.json'
out = Path('data') / 'simulated_responses_3pl.csv'

items = json.loads(bank.read_text(encoding='utf-8'))
ids = [str(it['id']) for it in items]

n_respondents = 500
# sample respondent abilities
rng = np.random.default_rng(12345)
thetas = rng.normal(loc=0.0, scale=1.0, size=n_respondents)

# compute per-item ps for each theta using 3PL: P = c + (1-c)/(1+exp(-a*(theta - b)))
ps = np.zeros((n_respondents, len(items)))
for j, it in enumerate(items):
    a = float(it.get('param_a', 1.0) or 1.0)
    b = float(it.get('param_b', 0.0) or 0.0)
    c = float(it.get('param_c', 0.0) or 0.0)
    # vectorized
    p = c + (1.0 - c) / (1.0 + np.exp(-a * (thetas - b)))
    ps[:, j] = p

# sample responses
responses = rng.binomial(1, ps)

# write CSV with columns = item ids
df = pd.DataFrame(responses, columns=ids)
df.to_csv(out, index=False)
print(f'Wrote 3PL simulated responses to {out} ({n_respondents}x{len(ids)})')
