"""Evaluate item quality from response data and compare with generated IRT params.

Usage examples:
  python eval_items.py --responses data/responses.csv --bank data/java.json --out data/eval

Expectations:
- responses CSV: rows = respondents, columns = item ids (matching bank 'id' fields) or positional columns.
  Values may be 0/1 (binary) or letters (A/B/C/D). If letters, the script will map to correctness
  using the bank file's labeled 'answer' field (e.g., 'B) text').
- bank JSON: list of items produced by generator (fields: id, options, answer, param_a, param_b, param_c)

Outputs:
- item_stats.csv (p-value, point-biserial, original params, flags)
- distractors.csv (option counts and top/bottom group breakdowns if letter responses provided)

Dependencies: pandas, numpy, scipy
Install: pip install pandas numpy scipy
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats


def load_bank(bank_path: Path) -> Tuple[List[Dict], Dict[str, str], Dict[str, Dict[int, str]]]:
    items = json.loads(bank_path.read_text(encoding="utf-8"))
    # build answer_key: id -> letter (e.g. 'B') and option_text map
    answer_key: Dict[str, str] = {}
    option_texts: Dict[str, Dict[int, str]] = {}
    for it in items:
        iid = str(it.get("id"))
        ans = it.get("answer", "")
        # ans like 'B) the bundling...'
        letter = None
        if isinstance(ans, str) and ")" in ans:
            letter = ans.split(")")[0].strip()
        elif isinstance(ans, str) and len(ans) > 0:
            # maybe just a single char
            letter = ans.strip()
        else:
            letter = None
        answer_key[iid] = letter
        opts = it.get("options", []) or []
        # map index->text, also map letter->text
        letter_map = {}
        for idx, o in enumerate(opts):
            if isinstance(o, str) and ")" in o:
                lab = o.split(")")[0].strip()
                text = o.split(maxsplit=1)[1].strip() if len(o.split(maxsplit=1)) > 1 else ""
            else:
                lab = chr(ord('A') + idx)
                text = o
            letter_map[lab] = text
        option_texts[iid] = letter_map
    return items, answer_key, option_texts


def detect_response_format(df: pd.DataFrame) -> str:
    # examine values: if all 0/1 -> 'binary', else if strings of letters -> 'letter'
    sample = df.fillna("").iloc[: min(50, len(df))]
    all_binary = True
    for c in sample.columns:
        col = sample[c]
        vals = set([v for v in col.unique() if v is not None and (not (isinstance(v, float) and math.isnan(v)))])
        for v in vals:
            if v in {0, 1, '0', '1'}:
                continue
            # also accept True/False
            if isinstance(v, (int, float)) and (v == 0 or v == 1):
                continue
            all_binary = False
            break
        if not all_binary:
            break
    if all_binary:
        return "binary"
    # else check if mostly single-letter strings
    letter_like = 0
    total = 0
    for c in sample.columns:
        for v in sample[c].astype(str).values:
            total += 1
            if len(v.strip()) == 1 and v.strip().upper() in list("ABCD"):
                letter_like += 1
    if total > 0 and (letter_like / total) > 0.5:
        return "letter"
    # fallback assume binary
    return "binary"


def to_binary(df: pd.DataFrame, bank_answer_key: Dict[str, str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (df_binary, df_choices). df_binary: 0/1, df_choices: original values (letters or NaN).
    If input df already 0/1, df_choices will be empty DataFrame.
    """
    fmt = detect_response_format(df)
    if fmt == "binary":
        # convert possible '0'/'1' strings to ints
        dfb = df.copy()
        for c in dfb.columns:
            dfb[c] = pd.to_numeric(dfb[c], errors='coerce').fillna(0).astype(int)
        return dfb, pd.DataFrame()

    # else letter-coded
    df_choices = df.copy().astype(str).applymap(lambda x: x.strip().upper() if pd.notna(x) else x)
    df_binary = pd.DataFrame(index=df.index)
    # matching columns: if column name matches bank id use that, else if column index used map by order
    bank_ids = list(bank_answer_key.keys())
    cols = list(df_choices.columns)
    mapping = {}
    # try to map by exact id match
    for c in cols:
        if c in bank_answer_key:
            mapping[c] = c
    # for unmapped, map by position
    unmapped_cols = [c for c in cols if c not in mapping]
    pos = 0
    for c in unmapped_cols:
        if pos < len(bank_ids):
            mapping[c] = bank_ids[pos]
        else:
            mapping[c] = None
        pos += 1
    # now create binary
    for col, mapped in mapping.items():
        if mapped is None:
            # cannot map: set zeros
            df_binary[col] = 0
            continue
        correct = (df_choices[col] == (bank_answer_key.get(mapped) or "")).astype(int)
        df_binary[col] = correct
    # reorder df_binary columns to be bank ids (if mapping produced columns per bank id)
    # create df_bin with columns = bank_ids
    dfb2 = pd.DataFrame(index=df.index)
    for c in cols:
        mapped = mapping.get(c)
        if mapped:
            dfb2[str(mapped)] = df_binary[c]
    return dfb2.fillna(0).astype(int), df_choices


def cronbach_alpha(df_scores: pd.DataFrame) -> float:
    item_vars = df_scores.var(axis=0, ddof=1)
    total_var = df_scores.sum(axis=1).var(ddof=1)
    n_items = df_scores.shape[1]
    if n_items <= 1 or total_var == 0:
        return float('nan')
    return (n_items / (n_items - 1)) * (1 - item_vars.sum() / total_var)


def point_biserial_per_item(df_binary: pd.DataFrame) -> pd.Series:
    total = df_binary.sum(axis=1)
    r_pb = {}
    for col in df_binary.columns:
        item = df_binary[col]
        total_minus = total - item
        # use Pearson between binary item and total_minus
        try:
            r, p = stats.pearsonr(item, total_minus)
        except Exception:
            r = float('nan')
        r_pb[col] = r
    return pd.Series(r_pb)


def distractor_report(df_choices: pd.DataFrame, bank_option_texts: Dict[str, Dict[int, str]], top_frac: float = 0.27) -> Dict[str, dict]:
    reports = {}
    if df_choices.empty:
        return reports
    # compute total score for splitting
    # Note: df_choices may have columns named different; try to map columns to bank ids if possible
    # assume df_choices columns were mapped corresponding to bank positions earlier in to_binary
    for col in df_choices.columns:
        s = df_choices[col].dropna()
        counts = s.value_counts(dropna=False)
        total = counts.sum()
        freq = (counts / total).to_dict()
        reports[col] = {
            'total_counts': counts.to_dict(),
            'freq': {k: float(v / total) for k, v in counts.items()},
        }
    return reports


def evaluate(responses_path: Path, bank_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    items, answer_key, option_texts = load_bank(bank_path)

    # load responses
    df_raw = pd.read_csv(responses_path, dtype=str, keep_default_na=False, na_values=[''])
    # try convert empties to NaN
    df_raw = df_raw.replace({'': None})

    df_binary, df_choices = to_binary(df_raw, answer_key)

    if df_binary.shape[1] == 0:
        print("No mapped items found between responses and bank. Check headers or provide positional columns.")
        return

    # ensure columns are string ids
    df_binary.columns = [str(c) for c in df_binary.columns]

    # p-values
    p_vals = df_binary.mean(axis=0)
    r_pb = point_biserial_per_item(df_binary)
    alpha = cronbach_alpha(df_binary)

    # assemble report
    rows = []
    for it in items:
        iid = str(it.get('id'))
        p = float(p_vals.get(iid, float('nan')))
        r = float(r_pb.get(iid, float('nan')))
        a = it.get('param_a')
        b = it.get('param_b')
        c = it.get('param_c')
        flag = []
        if not math.isnan(p):
            if p < 0.15:
                flag.append('too_hard')
            if p > 0.9:
                flag.append('too_easy')
        if not math.isnan(r) and r < 0.2:
            flag.append('low_discrimination')
        rows.append({
            'id': iid,
            'question': it.get('question')[:200] if it.get('question') else None,
            'p_value': p,
            'point_biserial': r,
            'param_a': a,
            'param_b': b,
            'param_c': c,
            'flags': ";".join(flag) if flag else "ok",
        })

    df_items = pd.DataFrame(rows).set_index('id')

    # correlations between generated params and empirical stats
    corr_a_r = df_items[['param_a', 'point_biserial']].dropna()
    corr_b_p = df_items[['param_b', 'p_value']].dropna()
    corr_report = {}
    if not corr_a_r.empty:
        try:
            corr_report['a_vs_r_pb'] = float(corr_a_r['param_a'].corr(corr_a_r['point_biserial']))
        except Exception:
            corr_report['a_vs_r_pb'] = None
    else:
        corr_report['a_vs_r_pb'] = None
    if not corr_b_p.empty:
        try:
            corr_report['b_vs_p'] = float(corr_b_p['param_b'].corr(corr_b_p['p_value']))
        except Exception:
            corr_report['b_vs_p'] = None
    else:
        corr_report['b_vs_p'] = None

    # distractor report
    distractors = distractor_report(df_choices, option_texts)

    # write outputs
    df_items.to_csv(out_dir / 'item_stats.csv')
    with open(out_dir / 'corr_report.json', 'w', encoding='utf-8') as f:
        json.dump(corr_report, f, ensure_ascii=False, indent=2)
    with open(out_dir / 'distractors.json', 'w', encoding='utf-8') as f:
        json.dump(distractors, f, ensure_ascii=False, indent=2)

    # summary
    print(f"Wrote item_stats.csv ({len(df_items)} items), distractors.json, corr_report.json to {out_dir}")
    print("Cronbach alpha:", alpha)
    print("Correlation a vs point-biserial:", corr_report.get('a_vs_r_pb'))
    print("Correlation b vs p-value:", corr_report.get('b_vs_p'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--responses', required=True, help='CSV of responses (rows=respondents, cols=items)')
    p.add_argument('--bank', required=True, help='Generated question bank JSON (e.g. data/java.json)')
    p.add_argument('--out', default='data/eval', help='Output directory for reports')
    args = p.parse_args()

    evaluate(Path(args.responses), Path(args.bank), Path(args.out))


if __name__ == '__main__':
    main()
