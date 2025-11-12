"""Simple runner that imports the question generator API and runs it with
default parameters so you don't need to call the CLI.

Usage:
    python run_generation.py

You can also import `generate_topic_banks` from `question_generator` and call it
from other Python code.
"""
from pathlib import Path

from question_generator import (default_topic_keywords,
                                generate_topic_theoretical_banks)


def main():
    input_dir = Path("docs")
    out_dir = Path("data")
    # generate 150 theoretical (non-code) items per topic by default
    generate_topic_theoretical_banks(input_dir=input_dir,
                                     out_dir=out_dir,
                                     target_per_topic=150,
                                     base_json=Path("data/Java_Course_150_questions.json"),
                                     seed=42,
                                     topic_keywords=default_topic_keywords())


if __name__ == "__main__":
    main()
