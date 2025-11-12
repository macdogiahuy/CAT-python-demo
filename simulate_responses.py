"""Simulate respondent answers from a generated bank (3PL model) and write CSV of letter choices.

Outputs: data/simulated_responses.csv

Usage: python simulate_responses.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

BANK = Path('data') / 'ch-ng-1-question-bank-20251111-202150.json'
OUT = Path('data') / 'simulated_responses.csv'
N_RESPONDENTS = 400
SEED = 42

rng = np.random.default_rng(SEED)

items = json.loads(BANK.read_text(encoding='utf-8'))
# keep items that have an 'id' and 'options' and 'answer'
bank = []
for it in items:
    if 'id' in it and 'options' in it and it['options']:
        bank.append(it)

# prepare mapping: id -> correct_letter, option_letters
id_list = [str(it['id']) for it in bank]
correct_map = {}
option_letters = {}
for it in bank:
    iid = str(it['id'])
    ans = it.get('answer','')
    # try parse letter like 'B) ...' or 'B'
    letter = None
    if isinstance(ans, str) and ')' in ans:
        letter = ans.split(')')[0].strip()
    elif isinstance(ans, str) and len(ans.strip())==1:
        letter = ans.strip()
    else:
        # fallback assume first option is A
        if it['options']:
            letter = 'A'
    correct_map[iid] = letter
    # derive letters available (A,B,C,...)
    opts = it['options']
    letters = []
    for idx, o in enumerate(opts):
        letters.append(chr(ord('A') + idx))
    option_letters[iid] = letters

# function for 3PL probability
def three_pl_prob(a, b, c, theta):
    # logistic with scaling 1.7
    return c + (1 - c) / (1 + np.exp(-1.7 * a * (theta - b)))

rows = []
for r in range(N_RESPONDENTS):
    theta = rng.normal(0, 1)
    row = {}
    for it in bank:
        iid = str(it['id'])
        a = float(it.get('param_a', 1.0) or 1.0)
        b = float(it.get('param_b', 0.0) or 0.0)
        c = float(it.get('param_c', 0.2) or 0.2)
        p_corr = three_pl_prob(a, b, c, theta)
        is_correct = rng.random() < p_corr
        letters = option_letters.get(iid, ['A','B','C','D'])
        corr_letter = correct_map.get(iid, 'A')
        if is_correct:
            choice = corr_letter
        else:
            wrongs = [L for L in letters if L != corr_letter]
            if wrongs:
                choice = rng.choice(wrongs)
            else:
                choice = corr_letter
        row[iid] = choice
    rows.append(row)

# create dataframe with columns in bank id order
df = pd.DataFrame(rows, columns=id_list)
OUT.parent.mkdir(parents=True, exist_ok=True)
# write without index
df.to_csv(OUT, index=False)
print(f'Wrote simulated responses: {OUT} ({len(df)} respondents, {len(df.columns)} items)')
