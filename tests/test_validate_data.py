import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


FILES = sorted(DATA_DIR.glob("*.json"))


@pytest.mark.parametrize("path", FILES)
def test_json_loadable_and_top_level_list(path: Path):
    data = load_json(path)
    assert isinstance(data, list), f"{path} top-level JSON is not a list"


@pytest.mark.parametrize("path", FILES)
def test_items_schema_and_consistency(path: Path):
    data = load_json(path)
    ids = set()
    for idx, item in enumerate(data, start=1):
        assert isinstance(item, dict), f"Item {idx} in {path} is not an object"

        # id
        assert "id" in item, f"Missing 'id' in item {idx} of {path}"
        assert isinstance(item["id"], int), f"'id' must be int in item {idx} of {path}"
        assert item["id"] not in ids, f"Duplicate id {item['id']} in {path}"
        ids.add(item["id"])

        # question
        assert "question" in item and isinstance(item["question"], str) and item["question"].strip(), (
            f"Empty or missing 'question' in item id {item.get('id')} of {path}"
        )

        # options
        assert "options" in item and isinstance(item["options"], list), (
            f"'options' missing or not a list in item id {item.get('id')} of {path}"
        )
        assert len(item["options"]) >= 2, f"Less than 2 options in item id {item.get('id')} of {path}"
        for opt in item["options"]:
            assert isinstance(opt, str), f"Option not a string in item id {item.get('id')} of {path}"

        # answer
        assert "answer" in item and isinstance(item["answer"], str), (
            f"'answer' missing or not a string in item id {item.get('id')} of {path}"
        )
        assert item["answer"] in item["options"], (
            f"'answer' value not present in 'options' for item id {item.get('id')} of {path}"
        )

        # difficulty
        assert "difficulty" in item and isinstance(item["difficulty"], str), (
            f"'difficulty' missing or not a string in item id {item.get('id')} of {path}"
        )
        assert item["difficulty"].lower() in {"easy", "medium", "hard"}, (
            f"'difficulty' should be one of Easy/Medium/Hard in item id {item.get('id')} of {path}"
        )

        # params
        for p in ("param_a", "param_b", "param_c"):
            assert p in item, f"Missing '{p}' in item id {item.get('id')} of {path}"
            assert isinstance(item[p], (int, float)), f"'{p}' must be numeric in item id {item.get('id')} of {path}"

        # param_c should be a probability-like value
        assert 0.0 <= float(item["param_c"]) <= 1.0, (
            f"'param_c' expected in [0,1] in item id {item.get('id')} of {path}"
        )


def test_data_files_found():
    assert FILES, f"No JSON files found in {DATA_DIR}"
