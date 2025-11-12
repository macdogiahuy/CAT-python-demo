"""Generate question banks using Ollama's cloud API (no third-party Python libs).

This module only uses the standard library (urllib) to call Ollama's
cloud/chat endpoint. It expects the environment variable OLLAMA_API_KEY to be
set with a valid API key for direct access to ollama.com's API.

The main function `generate_topic_banks_via_ollama` mirrors the project's
generate_topic_banks but delegates summarization and MCQ generation to a
cloud model.
"""
from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from typing import Dict, List, Tuple
from urllib import error, request

OLLAMA_API_URL = "https://ollama.com/api/chat"


def _post_chat(model: str, messages: List[Dict]) -> str:
    """Post a chat request to Ollama's cloud API and return raw text response.

    Uses OLLAMA_API_KEY environment variable for Authorization.
    """
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise EnvironmentError("OLLAMA_API_KEY not set. Create a key on ollama.com and set the OLLAMA_API_KEY environment variable.")

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
    }).encode("utf-8")

    req = request.Request(OLLAMA_API_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return raw
    except error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(f"Ollama API error: {e.code} {e.reason}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to contact Ollama API: {e}") from e


def _extract_json_block(s: str) -> str:
    """Try to extract the first JSON array/object from the model output.

    Models sometimes add text before/after JSON. We find the first '[' or '{'
    and the matching closing bracket to extract JSON. This is a best-effort
    recovery.
    """
    s = s.strip()
    # find first JSON start
    starts = [(s.find('['), '['), (s.find('{'), '{')]
    starts = [(i, ch) for i, ch in starts if i != -1]
    if not starts:
        raise ValueError("No JSON array or object found in model output")
    starts.sort()
    start_idx, ch = starts[0]
    # choose matching closing
    pairs = {'[': ']', '{': '}'}
    open_ch = ch
    close_ch = pairs[open_ch]
    depth = 0
    for i in range(start_idx, len(s)):
        if s[i] == open_ch:
            depth += 1
        elif s[i] == close_ch:
            depth -= 1
            if depth == 0:
                return s[start_idx:i+1]
    # fallback: raise
    raise ValueError("Could not find matching JSON closing bracket in model output")


def _make_prompt(document: str, requested: int) -> List[Dict]:
    """Construct messages for the Ollama chat API.

    The assistant must return a pure JSON array of MCQ items. Each item must
    have: question, options (array of 4 strings), answer (exact option string),
    source (string), difficulty (Easy/Medium/Hard).
    """
    # keep document reasonably sized
    doc_snip = document.strip()
    if len(doc_snip) > 20000:
        doc_snip = doc_snip[:20000] + "\n\n[TRUNCATED]"

    system = {
        "role": "system",
        "content": (
            "You are an assistant that reads a technical/theoretical document and produces high-quality multiple-choice questions (MCQs)."
        ),
    }

    user = {
        "role": "user",
        "content": textwrap.dedent(f"""
            Read the following document and produce up to {requested} multiple-choice questions focused on theoretical concepts (do NOT include questions that require interpreting code blocks or running code). Prioritize concise, unambiguous questions useful for assessment.

            Requirements:
            - Return a single JSON array only, with no surrounding commentary.
            - Each item in the array must be an object with keys: "question" (string), "options" (array of 4 strings), "answer" (one of the options exactly), "source" (a short sentence from the document), "difficulty" (Easy, Medium, or Hard).
            - Do not include code snippets in questions or options; if the source is code, skip it.
            - Prefer factual/conceptual questions and avoid literal page headers/metadata.

            Document:
            {doc_snip}
        """)
    }

    return [system, user]


def generate_topic_banks_via_ollama(input_dir: Path,
                                    out_dir: Path = Path("data"),
                                    target_per_topic: int = 150,
                                    model: str = "gpt-oss:120b-cloud",
                                    topic_keywords: Dict[str, List[str]] | None = None) -> Dict[str, Path]:
    """Generate per-topic MCQ banks by asking an Ollama cloud model to produce questions.

    This function groups files by inferred topic (using filename heuristics) and
    asks the model to produce up to `target_per_topic` theory questions for
    each topic. The model is expected to return a JSON array; we parse it and
    write a per-topic JSON file.
    """
    if topic_keywords is None:
        # minimal default topic keywords to match existing project
        topic_keywords = {
            "java": ["java", "jvm", "spring"],
            "python": ["python", "django"],
            "sql": ["sql", "mysql", "database"],
        }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # group files by topic using filename priority
    files_by_topic: Dict[str, List[Tuple[Path, str]]] = {}
    for p in Path(input_dir).glob("**/*"):
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        name = p.name.lower()
        topic = "general"
        for t, kws in topic_keywords.items():
            for kw in kws:
                if kw.lower() in name:
                    topic = t
                    break
            if topic != "general":
                break
        files_by_topic.setdefault(topic, []).append((p, text))

    written: Dict[str, Path] = {}
    for topic, file_list in files_by_topic.items():
        combined = "\n\n".join(t for (_, t) in file_list)
        messages = _make_prompt(combined, target_per_topic)
        raw = _post_chat(model, messages)
        # models may return a JSON string embedded; try to extract it
        try:
            jtext = _extract_json_block(raw)
            arr = json.loads(jtext)
        except Exception as e:
            raise RuntimeError(f"Failed to parse JSON from model output for topic '{topic}': {e}\nRaw output:\n{raw[:2000]}")

        # normalize items into expected schema
        mcq_items = []
        idx = 1
        for it in arr:
            q = it.get("question") or it.get("q") or ""
            opts = it.get("options") or it.get("choices") or []
            ans = it.get("answer") or it.get("correct") or ""
            src = it.get("source") or ""
            diff = it.get("difficulty") or "Medium"
            if not q or not opts or not ans:
                continue
            # ensure options list length 4
            if isinstance(opts, list) and len(opts) == 4:
                options = opts
            else:
                # if not 4, try to pad or truncate
                opts_list = list(opts) if isinstance(opts, (list, tuple)) else [str(x) for x in opts]
                options = opts_list[:4]
                while len(options) < 4:
                    options.append("None of the above")

            mcq_items.append({
                "id": idx,
                "question": q,
                "options": options,
                "answer": ans,
                "difficulty": diff,
                "source": src,
            })
            idx += 1

        safe = topic.replace(" ", "_") or "general"
        out_file = out_dir / f"{safe}.json"
        out_file.write_text(json.dumps(mcq_items, ensure_ascii=False, indent=2), encoding="utf-8")
        written[topic] = out_file
        print(f"Wrote {len(mcq_items)} items for topic '{topic}' -> {out_file}")

    return written
