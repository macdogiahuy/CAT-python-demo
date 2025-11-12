"""Minimal question generator pipeline (rule-based) for offline testing.

This script is intentionally lightweight so you can run it without large ML
dependencies. It reads plain text files from an input directory, splits them
into chunks, applies simple rule-based question-generation heuristics, tags
chunks by topic keywords, and writes a JSON file containing generated items.

Each generated item includes simple IRT params (a,b,c) so it can be imported
into the project's `McqQuestions` table for CAT experiments.

Usage (example):
    python question_generator.py --input data --output generated_questions.json

Note: This is a starting point. For higher-quality questions replace the
`rule_generate_qa` implementation with a transformer/LLM-based generator.
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import random
import re
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


def read_text_files(input_dir: Path) -> Iterable[Tuple[Path, str]]:
    for p in input_dir.glob("**/*"):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf in {".txt", ".md"}:
            yield p, p.read_text(encoding="utf-8", errors="ignore")
        elif suf == ".docx":
            txt = extract_text_from_docx(p)
            if txt:
                yield p, txt
        elif suf == ".pdf":
            txt = extract_text_from_pdf(p)
            if txt:
                yield p, txt


def simple_sentence_split(text: str) -> List[str]:
    # Very small heuristic splitter (keeps abbreviations naive)
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def summarize_text(text: str, max_sentences: int = 8) -> str:
    """Lightweight extractive summarizer: score sentences by word frequency.

    Returns the top `max_sentences` sentences in original order joined as a summary.
    This is intentionally simple and dependency-free.
    """
    sents = simple_sentence_split(text)
    if not sents:
        return ""

    # small stopword list
    stop = {
        'the', 'and', 'a', 'an', 'of', 'to', 'in', 'for', 'that', 'is', 'it', 'with',
        'as', 'on', 'are', 'this', 'by', 'be', 'or', 'from', 'at', 'which', 'have', 'has'
    }

    # build word frequency from document
    freq: Dict[str, int] = {}
    for s in sents:
        for w in re.findall(r"\w+", s.lower()):
            if w in stop or len(w) < 2:
                continue
            freq[w] = freq.get(w, 0) + 1

    if not freq:
        # fallback: return first few sentences
        return " ".join(sents[:max_sentences])

    # score sentences by sum of word frequencies
    scores: List[Tuple[int, int]] = []  # (score, index)
    for i, s in enumerate(sents):
        sc = 0
        for w in re.findall(r"\w+", s.lower()):
            sc += freq.get(w, 0)
        scores.append((sc, i))

    # pick top sentences
    scores_sorted = sorted(scores, key=lambda x: x[0], reverse=True)
    top_idx = set(i for (_, i) in scores_sorted[:max_sentences])

    # preserve original order
    summary_sents = [sents[i] for i in range(len(sents)) if i in top_idx]
    return " ".join(summary_sents)


def chunk_text(sentences: List[str], max_words: int = 120) -> List[str]:
    chunks = []
    cur: List[str] = []
    cur_words = 0
    for s in sentences:
        w = len(s.split())
        if cur_words + w > max_words and cur:
            chunks.append(" ".join(cur))
            cur = [s]
            cur_words = w
        else:
            cur.append(s)
            cur_words += w
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def is_code_text(s: str) -> bool:
    """Detect whether a string appears to contain source code or code fragments.

    This is heuristic: looks for common code tokens/constructs that appear in
    textbook excerpts (semicolons, braces, method signatures, file extensions,
    'System.out', 'public static', arrows, etc.).
    """
    if not s:
        return False
    low = s.lower()
    # common code signs
    code_tokens = ["{", "}", ";", "//", "/*", "*/", "public static", "system.out", ".java", ".class", "#include", "printf(", "cout<<", "->", "=>"]
    for t in code_tokens:
        if t in low:
            return True
    # method-like pattern: word(...){ or word(...) throws
    if re.search(r"\b[a-z_][a-z0-9_]*\s*\([^)]{0,60}\)\s*\{", s, flags=re.IGNORECASE):
        return True
    # short lines with many symbols
    sym_count = len(re.findall(r"[=+\-*/<>%]", s))
    if sym_count >= 3:
        return True
    return False


def normalize_text(s: str) -> str:
    """Normalize text for simple similarity comparisons."""
    if not s:
        return ""
    t = s.lower()
    # replace punctuation with spaces, keep alphanumerics
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_similar(a: str, b: str, threshold: float = 0.85) -> bool:
    """Return True if normalized strings a and b are similar above threshold."""
    if not a or not b:
        return False
    # short-circuit exact match
    if a == b:
        return True
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return ratio >= threshold


def topic_tag(chunk: str, topic_keywords: Dict[str, List[str]]) -> str:
    low = chunk.lower()
    scores: Dict[str, int] = {t: 0 for t in topic_keywords}
    for t, kws in topic_keywords.items():
        for kw in kws:
            if kw.lower() in low:
                scores[t] += 1
    # return topic with highest matches or 'general'
    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else "general"


def rule_generate_qa(chunk: str) -> List[Dict[str, str]]:
    """Generate simple Q/A pairs from a chunk using heuristics.

    Heuristics implemented:
    - Extract sentences like "X is Y" / "X are Y" -> Q: "What is X?" A: "Y"
    - Convert definitional sentences starting with "<term> is/are".
    - If no pattern found, take a declarative sentence and make a fill-in-the-blank.
    """
    sents = simple_sentence_split(chunk)
    qas: List[Dict[str, str]] = []
    # pattern: subject (short) + is/are/was/are + predicate
    pat = re.compile(r"^(?P<subj>[A-Za-z0-9_\- ]{1,80}?)\s+(?:is|are|was|were|refers to)\s+(?P<pred>.+)$",
                     flags=re.IGNORECASE)
    for s in sents:
        m = pat.match(s)
        if m:
            subj = m.group("subj").strip(" ,")
            pred = m.group("pred").strip(" .,")
            if len(subj.split()) <= 6 and len(pred.split()) <= 40:
                question = f"What is {subj}?"
                answer = pred
                qas.append({"question": question, "answer": answer, "source": s})
                continue

    # fallback: generate cloze from a long declarative sentence
    if not qas:
        for s in sents:
            words = s.split()
            if len(words) >= 6:
                # blank out a middle noun-ish chunk
                mid = len(words) // 2
                span = slice(max(0, mid - 2), min(len(words), mid + 2))
                answer = " ".join(words[span])
                question = s.replace(answer, "_____", 1)
                qas.append({"question": question, "answer": answer, "source": s})
                break

    return qas


def generate_items_from_dir(input_dir: Path,
                            topic_keywords: Dict[str, List[str]],
                            max_chunks_per_file: int = 20) -> List[Dict]:
    items = []
    for path, text in read_text_files(input_dir):
        sents = simple_sentence_split(text)
        chunks = chunk_text(sents, max_words=120)
        for i, chunk in enumerate(chunks[:max_chunks_per_file]):
            topic = topic_tag(chunk, topic_keywords)
            qas = rule_generate_qa(chunk)
            for qa in qas:
                item = {
                    "id": str(uuid.uuid4()),
                    "question": qa["question"],
                    "answer": qa["answer"],
                    "topic": topic,
                    "source_file": str(path.name),
                    "source_text": qa.get("source", chunk)[:1000],
                    # default IRT params (can be re-estimated later)
                    "param_a": 1.0,
                    "param_b": 0.0,
                    "param_c": 0.2,
                }
                items.append(item)
    return items


def estimate_p_for_item(answer: str, question: str, source_text: str) -> float:
    """Heuristic estimate of probability of a typical examinee answering item correctly (p-value).

    Returns a float in (0,1). Uses simple signals:
    - frequency of answer text in source (more occurrences -> easier)
    - definitional question ("What is ...") -> slightly easier
    - short answers are slightly easier
    - punctuation/complex tokens reduce ease slightly
    """
    if not answer:
        return 0.5
    s = source_text.lower() if source_text else ""
    a = answer.lower().strip()
    # frequency score (normalize by 5 occurrences)
    occ = s.count(a) if a else 0
    freq_score = min(occ / 5.0, 1.0)

    q = question.lower().strip() if question else ""
    type_score = 0.12 if q.startswith("what is") or q.startswith("what are") or q.startswith("define") else 0.0

    words = len(a.split())
    if words <= 2:
        length_score = 0.10
    elif words >= 5:
        length_score = -0.05
    else:
        length_score = 0.0

    punct_pen = -0.06 if re.search(r"[^\w\s]", a) else 0.0

    base = 0.45 + 0.35 * freq_score + type_score + length_score + punct_pen
    # clamp
    p = max(0.04, min(0.96, base))
    return p


def derive_irt_from_p(p_target: float, a_hint: float | None = None) -> Tuple[float, float, float]:
    """Derive (a,b,c) so that at theta=0 the probability is ~ p_target.

    - pick a (discrimination) around 1.0 with small noise unless a_hint given
    - pick a lower guessing c in [0.02, 0.15]
    - invert the 3PL formula at theta=0 to get b
    """
    # choose discrimination
    if a_hint is None:
        a = max(0.4, min(2.5, random.gauss(1.05, 0.25)))
    else:
        a = max(0.4, min(2.5, float(a_hint)))

    # guessing parameter: lower default (most items not pure guess)
    c = round(random.uniform(0.02, 0.15), 2)

    # ensure p_target is above c by a small margin
    p = max(p_target, c + 0.01)

    # Solve for b at theta=0: p = c + (1-c) / (1+exp(1.7*a*b))
    denom = (1 - c) / (p - c) - 1
    if denom <= 0:
        b = 0.0
    else:
        try:
            b = math.log(denom) / (1.7 * a)
        except Exception:
            b = 0.0

    return round(a, 2), round(b, 2), round(c, 2)


def score_item_quality(question: str, answer: str, source_text: str) -> float:
    """Score item quality between 0 and 1 using lightweight heuristics.

    A higher score means the question is more likely to be meaningful and
    learnable. Signals used:
    - answer appears verbatim in the source text (strong signal)
    - reasonable answer length (1-5 tokens)
    - question is an explicit WH-question (what/when/which/why/how) gives bonus
    - cloze items ('_____') must have the answer present in the source sentence
    """
    if not answer or not question:
        return 0.0
    ans = answer.strip()
    src = source_text or ""
    low_src = src.lower()
    low_ans = ans.lower()

    # presence in source
    presence = 1.0 if low_ans in low_src and len(low_ans) >= 2 else 0.0

    # length heuristic
    toks = ans.split()
    if 1 <= len(toks) <= 5:
        length_score = 1.0
    elif len(toks) == 6:
        length_score = 0.6
    else:
        length_score = 0.2

    # avoid generic/placeholder answers
    bad_phrases = ("depends", "not applicable", "none of the above", "both a and b", "not sure")
    if any(b in low_ans for b in bad_phrases):
        return 0.0

    # question type bonus
    qlow = question.strip().lower()
    q_bonus = 0.5 if qlow.startswith(("what", "who", "when", "where", "how", "which", "why")) else 0.0

    # cloze consistency
    cloze_ok = 1.0
    if "_____" in question or "____" in question:
        cloze_ok = 1.0 if low_ans in low_src else 0.0

    # combine weights (tunable)
    score = 0.35 * presence + 0.25 * length_score + 0.2 * q_bonus + 0.2 * cloze_ok
    return max(0.0, min(1.0, score))


def make_mcq_options(answer: str, source_text: str, pool_extra: List[str] = None) -> Tuple[List[str], str]:
    """Create 4 options (A-D) including the correct answer and simple distractors.

    Returns (options_list, labeled_answer) where options are like "A) foo" and
    labeled_answer is the string matching the style in the existing JSON (e.g. "C) final").
    This is heuristic and intended for offline testing only.
    """
    pool_extra = pool_extra or []
    ans = answer.strip().strip('`"\'')
    cand = []
    # gather candidates from the source text (short phrases)
    tokens = re.findall(r"\b[A-Za-z0-9_\-()\.]+\b", source_text)
    short_tokens = [t for t in tokens if 1 <= len(t) <= 30 and t.lower() != ans.lower()]
    cand.extend(short_tokens)

    # small curated tech-term pool to help distractors for programming questions
    curated = [
        "static", "final", "const", "immutable", "class", "object", "new",
        "main()", "start()", "boolean", "int", "String", ".java", ".class",
        "=", "==", "+=", "for loop", "while loop", "do-while loop",
        "public", "private", "protected", "package"
    ]
    cand.extend(curated)
    cand.extend(pool_extra)

    # deduplicate, prefer different-case uniqueness
    seen = set()
    candidates = []
    for c in cand:
        key = c.lower()
        if key not in seen and c and len(c.strip()) > 0:
            seen.add(key)
            candidates.append(c)

    # remove items that are identical to answer
    candidates = [c for c in candidates if c.lower() != ans.lower()]

    # build options: include correct answer and sample up to 3 distractors
    distractors = []
    random.shuffle(candidates)
    for c in candidates:
        # simple filter: distractor should be reasonably short
        if len(distractors) >= 3:
            break
        if 1 <= len(c) <= 60:
            distractors.append(c)

    # fallback generic distractors if not enough
    generic = ["None of the above", "Depends on context", "Not applicable", "Both A and B"]
    while len(distractors) < 3:
        for g in generic:
            if g not in distractors and g.lower() != ans.lower():
                distractors.append(g)
                if len(distractors) >= 3:
                    break

    options_plain = [ans] + distractors[:3]
    random.shuffle(options_plain)

    labels = ["A)", "B)", "C)", "D)"]
    options = [f"{lab} {txt}" for lab, txt in zip(labels, options_plain)]
    # find labeled answer
    labeled = None
    for opt in options:
        if opt.split(maxsplit=1)[1].strip().lower() == ans.lower():
            labeled = opt
            break
    # if exact match not found (e.g. whitespace/case), choose the option that contains answer substring
    if not labeled:
        for opt in options:
            if ans.lower() in opt.lower():
                labeled = opt
                break
    # final fallback: set answer to first option
    if not labeled:
        labeled = options[0]

    return options, labeled


def extract_text_from_docx(path: Path) -> str:
    """Extract text from .docx using python-docx if available.

    Returns empty string on failure (and prints a helpful message).
    """
    try:
        import docx  # python-docx
    except Exception:
        print("[warning] python-docx not installed — cannot extract .docx files. Install with: pip install python-docx")
        return ""
    try:
        doc = docx.Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(paragraphs)
    except Exception as e:
        print(f"[warning] failed to extract text from {path.name}: {e}")
        return ""


def extract_text_from_pdf(path: Path) -> str:
    """Extract text from PDF using pypdf if available.

    Returns empty string on failure (and prints a helpful message).
    """
    try:
        import pypdf
    except Exception:
        # older systems may have PyPDF2 under different names — keep message simple
        print("[warning] pypdf (or PyPDF2) not installed — cannot extract .pdf files. Install with: pip install pypdf")
        return ""
    try:
        reader = pypdf.PdfReader(str(path))
        pages = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t:
                pages.append(t)
        return "\n".join(pages)
    except Exception as e:
        print(f"[warning] failed to extract text from {path.name}: {e}")
        return ""


def generate_items_from_file(path: Path, text: str, topic_keywords: Dict[str, List[str]],
                             target: int = 150,
                             prefer_non_code: bool = False,
                             max_variants_per_sentence: int = 3,
                             similarity_threshold: float = 0.85,
                             quality_threshold: float = 0.45) -> List[Dict]:
    """Generate up to `target` raw QA items from a single file's text.

    The function uses rule-based extraction and then synthesizes additional
    cloze-style questions by blanking different spans until the target count is
    reached or no more unique items can be produced.
    """
    sents = simple_sentence_split(text)
    # summarize document first to focus on key sentences/knowledge
    summary = summarize_text(text, max_sentences=12)
    sents = simple_sentence_split(summary or text)
    chunks = chunk_text(sents, max_words=80)  # smaller chunks give more candidates
    items: List[Dict] = []
    seen_questions = set()
    # store normalized forms for similarity-based deduplication
    norm_questions: List[str] = []

    # Step 1: extract from chunks
    for chunk in chunks:
        # if preferring non-code, skip chunks that appear to contain code
        if prefer_non_code and is_code_text(chunk):
            continue
        topic = topic_tag(chunk, topic_keywords)
        qas = rule_generate_qa(chunk)
        for qa in qas:
            qtext = qa["question"].strip()
            # normalized form for similarity checking
            nq = normalize_text(qtext)
            too_similar = any(is_similar(nq, existing, threshold=similarity_threshold) for existing in norm_questions)
            if not too_similar and len(items) < target:
                seen_questions.add(qtext)
                norm_questions.append(nq)
                items.append({
                    "id": str(uuid.uuid4()),
                    "question": qtext,
                    "answer": qa["answer"].strip(),
                    "topic": topic,
                    "source_file": str(path.name),
                    # use the summary as the canonical source_text when available
                    "source_text": (qa.get("source", chunk)[:1000] if qa.get("source") else summary[:1000]),
                })

    # Step 2: synthesize cloze/fill-in-the-blank from sentences until we hit target
    # For each sentence, create multiple cloze variants by blanking different spans
    for s in sents:
        if len(items) >= target:
            break
        words = s.split()
        if len(words) < 4:
            continue
        # skip sentence if it looks like code and we prefer non-code
        if prefer_non_code and is_code_text(s):
            continue
        # limit number of cloze variants per sentence to avoid many near-duplicates
        variants_for_sentence = 0
        # produce up to 3 cloze variants per sentence (short spans)
        for span_width in (1, 2, 3):
            if len(items) >= target:
                break
            for start in range(0, max(1, len(words) - span_width + 1)):
                if len(items) >= target:
                    break
                if variants_for_sentence >= max_variants_per_sentence:
                    break
                span = words[start:start + span_width]
                answer = " ".join(span).strip(" ,.")
                if len(answer) < 1 or len(answer.split()) > 6:
                    continue
                question = s.replace(" ".join(span), "_____", 1)
                qtext = question.strip()
                nq = normalize_text(qtext)
                if any(is_similar(nq, existing, threshold=similarity_threshold) for existing in norm_questions):
                    continue
                seen_questions.add(qtext)
                norm_questions.append(nq)
                variants_for_sentence += 1
                items.append({
                    "id": str(uuid.uuid4()),
                    "question": qtext,
                    "answer": answer,
                    "topic": topic_tag(s, topic_keywords),
                    "source_file": str(path.name),
                    "source_text": s[:1000],
                })
                if len(items) >= target:
                    break

    # If still short, create simple definitional questions from single nouns/terms
    # by turning 'X is Y' segments into 'What is X?'
    if len(items) < target:
        for s in sents:
            if len(items) >= target:
                break
            # skip code-like sentences if requested
            if prefer_non_code and is_code_text(s):
                continue

            m = re.match(r"^(?P<subj>[A-Za-z0-9_\- ]{1,80}?)\s+(?:is|are|was|were)\s+(?P<pred>.+)$",
                         s, flags=re.IGNORECASE)
            if m:
                subj = m.group("subj").strip(" ,")
                pred = m.group("pred").strip(" .,")
                question = f"What is {subj}?"
                nq = normalize_text(question)
                if any(is_similar(nq, existing, threshold=similarity_threshold) for existing in norm_questions):
                    continue
                # quality check
                qscore = score_item_quality(question, pred, s)
                if qscore < quality_threshold:
                    continue
                seen_questions.add(question)
                norm_questions.append(nq)
                items.append({
                    "id": str(uuid.uuid4()),
                    "question": question,
                    "answer": pred,
                    "topic": topic_tag(s, topic_keywords),
                    "source_file": str(path.name),
                    "source_text": s[:1000],
                })

    # Filter low-quality items using a lightweight heuristic score. This removes
    # many meaningless cloze or definitional items that don't appear to be
    # grounded in the source text.
    scored: List[Dict] = []
    for it in items:
        q = it.get("question", "")
        a = it.get("answer", "")
        src = it.get("source_text", "")
        s = score_item_quality(q, a, src)
        if s >= 0.45:  # threshold: tuneable; 0.45 filters very weak items
            it["quality_score"] = round(s, 2)
            scored.append(it)

    # If scoring filtered out too many items, fall back to original items
    if not scored:
        return items[:target]

    # sort by score (desc) and return up to target
    scored_sorted = sorted(scored, key=lambda x: x.get("quality_score", 0), reverse=True)
    return scored_sorted[:target]


def default_topic_keywords() -> Dict[str, List[str]]:
    return {
        "java": ["java", "jvm", "spring", "hibernate", "jdk", "oop", "object-oriented", "object oriented"],
        "python": ["python", "django", "flask", "pandas", "numpy"],
        "sql": ["sql", "mysql", "postgres", "database", "query", "select", "insert"],
        "economics": ["economy", "inflation", "gdp", "market", "demand", "supply"],
        "general": []
    }


def infer_topic_for_file(path: Path, text: str, topic_keywords: Dict[str, List[str]]) -> str:
    """Infer topic for a file, preferring filename matches first.

    Heuristic:
    - If any topic keyword appears in the filename -> choose that topic.
    - Else if the text is present and long, use `topic_tag` on the text.
    - Else return 'general'.
    """
    name = path.name.lower()
    for t, kws in topic_keywords.items():
        for kw in kws:
            if kw.lower() in name:
                return t
    if text and len(text) > 20:
        return topic_tag(text, topic_keywords)
    return "general"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--input", "-i", default="data", help="Input directory with plain text files")
    p.add_argument("--output", "-o", default="generated_questions.json", help="Output JSON file")
    p.add_argument("--max-chunks", type=int, default=20, help="Max chunks per file")
    p.add_argument("--mcq", action="store_true", help="Emit MCQ items matching existing JSON schema (ids, options, labeled answer)")
    p.add_argument("--base-json", default=None, help="Path to an existing JSON question bank to continue numeric IDs from")
    p.add_argument("--seed", type=int, default=None, help="Optional random seed for reproducible output")
    p.add_argument("--target-per-file", type=int, default=0, help="If >0, generate this many MCQ items per input file and write per-file outputs to the --output directory")
    p.add_argument("--out-dir", default="data", help="Directory to write per-file outputs when --target-per-file is used (default: data)")
    args = p.parse_args(argv)

    input_dir = Path(args.input)
    if not input_dir.exists():
        raise SystemExit(f"Input dir not found: {input_dir}")

    topics = default_topic_keywords()

    if args.seed is not None:
        random.seed(args.seed)

    # If target-per-file specified, generate per-topic outputs (or when called programmatically use generate_topic_banks)
    if args.target_per_file and args.target_per_file > 0:
        generate_topic_banks(input_dir=input_dir,
                             out_dir=Path(args.out_dir),
                             target_per_topic=args.target_per_file,
                             base_json=Path(args.base_json) if args.base_json else None,
                             seed=args.seed,
                             topic_keywords=topics)
        return


def generate_topic_banks(input_dir: Path,
                         out_dir: Path = Path("data"),
                         target_per_topic: int = 150,
                         base_json: Path | None = None,
                         seed: int | None = None,
                         topic_keywords: Dict[str, List[str]] | None = None) -> Dict[str, Path]:
    """Programmatic API: generate question banks grouped by inferred topic.

    Returns a dict mapping topic -> output Path written.

    Parameters
    - input_dir: directory containing .txt/.md input files
    - out_dir: directory to write topic JSON files
    - target_per_topic: number of items to generate per topic
    - base_json: optional Path to existing JSON to continue numeric IDs from
    - seed: optional random seed for reproducibility
    - topic_keywords: optional topic keywords dict (defaults to `default_topic_keywords()`)
    """
    if topic_keywords is None:
        topic_keywords = default_topic_keywords()

    if seed is not None:
        random.seed(seed)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # determine starting numeric ID
    start_id = 1
    if base_json and base_json.exists():
        try:
            base_items = json.loads(base_json.read_text(encoding="utf-8"))
            maxid = max((it.get("id", 0) for it in base_items if isinstance(it.get("id", None), int)), default=0)
            start_id = maxid + 1
        except Exception:
            start_id = 1

    cur_id = start_id

    # group files by inferred topic
    files_by_topic: Dict[str, List[Tuple[Path, str]]] = {}
    for path, text in read_text_files(input_dir):
        topic = topic_tag(text, topic_keywords) if text and len(text) > 20 else topic_tag(path.name, topic_keywords)
        files_by_topic.setdefault(topic, []).append((Path(path), text))

    written: Dict[str, Path] = {}
    for topic, file_list in files_by_topic.items():
        combined_text = "\n\n".join(t for (_, t) in file_list)
        # use first file's Path as representative for source info
        items = generate_items_from_file(file_list[0][0], combined_text, topic_keywords, target=target_per_topic)
        mcq_items: List[Dict] = []
        for it in items:
            options, labeled = make_mcq_options(it["answer"], it.get("source_text", combined_text))
            # estimate target p (probability of correct at theta=0) from heuristics
            p_est = estimate_p_for_item(it.get("answer", ""), it.get("question", ""), it.get("source_text", combined_text))
            a, b, c = derive_irt_from_p(p_est)
            # label difficulty by p (higher p -> easier)
            if p_est >= 0.75:
                difficulty = "Easy"
            elif p_est >= 0.4:
                difficulty = "Medium"
            else:
                difficulty = "Hard"
            mcq = {
                "id": cur_id,
                "question": it["question"],
                "options": options,
                "answer": labeled,
                "difficulty": difficulty,
                "param_a": float(a),
                "param_b": float(b),
                "param_c": float(c),
            }
            mcq_items.append(mcq)
            cur_id += 1

        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", topic).strip("_- ") or "general"
        out_file = out_dir / f"{safe}.json"
        out_file.write_text(json.dumps(mcq_items, ensure_ascii=False, indent=2), encoding="utf-8")
        written[topic] = out_file
        srcs = [p.name for (p, _) in file_list]
        print(f"Wrote {len(mcq_items)} items for topic '{topic}' (from files: {', '.join(srcs)}) -> {out_file}")

    return written


def generate_topic_theoretical_banks(input_dir: Path,
                                     out_dir: Path = Path("data"),
                                     target_per_topic: int = 150,
                                     base_json: Path | None = None,
                                     seed: int | None = None,
                                     topic_keywords: Dict[str, List[str]] | None = None) -> Dict[str, Path]:
    """Generate per-topic banks but prefer theoretical (non-code) items.

    This function will attempt to generate `target_per_topic` items per topic
    using only non-code sentences. If insufficient items are found with strict
    settings, it will perform a relaxed second pass to gather more candidates.
    """
    if topic_keywords is None:
        topic_keywords = default_topic_keywords()
    if seed is not None:
        random.seed(seed)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: Dict[str, Path] = {}
    # group files by inferred topic
    files_by_topic: Dict[str, List[Tuple[Path, str]]] = {}
    for path, text in read_text_files(input_dir):
        topic = infer_topic_for_file(Path(path), text, topic_keywords)
        files_by_topic.setdefault(topic, []).append((Path(path), text))

    for topic, file_list in files_by_topic.items():
        combined_text = "\n\n".join(t for (_, t) in file_list)
        # First, strict pass: prefer non-code, stricter similarity and quality
        items = generate_items_from_file(file_list[0][0], combined_text, topic_keywords,
                                         target=target_per_topic,
                                         prefer_non_code=True,
                                         max_variants_per_sentence=3,
                                         similarity_threshold=0.88,
                                         quality_threshold=0.50)

        # If not enough, do a relaxed pass and merge additional unique items
        if len(items) < target_per_topic:
            more = generate_items_from_file(file_list[0][0], combined_text, topic_keywords,
                                            target=target_per_topic * 2,
                                            prefer_non_code=True,
                                            max_variants_per_sentence=5,
                                            similarity_threshold=0.77,
                                            quality_threshold=0.35)
            # merge while preserving uniqueness
            existing_norms = {normalize_text(it["question"]) for it in items}
            for it in more:
                if len(items) >= target_per_topic:
                    break
                n = normalize_text(it["question"])
                if n not in existing_norms:
                    items.append(it)
                    existing_norms.add(n)

        # final trim/pad: if still short, we'll accept fewer items (do not duplicate)
        final = items[:target_per_topic]

        # assemble MCQ entries
        mcq_items: List[Dict] = []
        cur_id = 1
        for it in final:
            options, labeled = make_mcq_options(it["answer"], it.get("source_text", combined_text))
            p_est = estimate_p_for_item(it.get("answer", ""), it.get("question", ""), it.get("source_text", combined_text))
            a, b, c = derive_irt_from_p(p_est)
            difficulty = "Easy" if p_est >= 0.75 else ("Medium" if p_est >= 0.4 else "Hard")
            mcq_items.append({
                "id": cur_id,
                "question": it["question"],
                "options": options,
                "answer": labeled,
                "difficulty": difficulty,
                "param_a": float(a),
                "param_b": float(b),
                "param_c": float(c),
            })
            cur_id += 1

        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", topic).strip("_- ") or "general"
        out_file = out_dir / f"{safe}.json"
        out_file.write_text(json.dumps(mcq_items, ensure_ascii=False, indent=2), encoding="utf-8")
        written[topic] = out_file
        srcs = [p.name for (p, _) in file_list]
        print(f"Wrote {len(mcq_items)} theoretical items for topic '{topic}' (from files: {', '.join(srcs)}) -> {out_file}")

    return written

    # default behavior: generate a flat list
    items = generate_items_from_dir(input_dir, topics, max_chunks_per_file=args.max_chunks)

    # If user asked for MCQ style output (schema like Java_Course_150_questions.json)
    if args.mcq:
        # determine starting ID (optionally from base file)
        start_id = 1
        if args.base_json:
            base = Path(args.base_json)
            if base.exists():
                try:
                    base_items = json.loads(base.read_text(encoding="utf-8"))
                    maxid = max((it.get("id", 0) for it in base_items if isinstance(it.get("id", None), int)), default=0)
                    start_id = maxid + 1
                except Exception:
                    start_id = 1

        mcq_items = []
        cur_id = start_id
        for it in items:
            # build options and labeled answer
            options, labeled = make_mcq_options(it["answer"], it.get("source_text", ""))

            # estimate p from heuristics and derive IRT params so p and difficulty align
            p_est = estimate_p_for_item(it.get("answer", ""), it.get("question", ""), it.get("source_text", ""))
            a, b, c = derive_irt_from_p(p_est)

            if p_est >= 0.75:
                difficulty = "Easy"
            elif p_est >= 0.4:
                difficulty = "Medium"
            else:
                difficulty = "Hard"

            mcq = {
                "id": cur_id,
                "question": it["question"],
                "options": options,
                "answer": labeled,
                "difficulty": difficulty,
                "param_a": float(a),
                "param_b": float(b),
                "param_c": float(c),
            }
            mcq_items.append(mcq)
            cur_id += 1

        out = Path(args.output)
        out.write_text(json.dumps(mcq_items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {len(mcq_items)} generated MCQ items to {out}")
    else:
        out = Path(args.output)
        out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {len(items)} generated items to {out}")


if __name__ == "__main__":
    main()
