import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datu_avoti import SOURCES, jsonstat_to_rows


def test_jsonstat_parseris():
    js = {"id": ["hf", "geo", "time"], "size": [2, 1, 2],
          "dimension": {"hf": {"category": {"index": {"HF1": 0, "HF3": 1}}},
                        "geo": {"category": {"index": {"LV": 0}}},
                        "time": {"category": {"index": {"2021": 0, "2022": 1}}}},
          "value": {"0": 60.0, "1": 61.0, "3": 33.5}}
    rows = jsonstat_to_rows(js)
    assert {"hf": "HF3", "geo": "LV", "time": "2022", "value": 33.5} in rows
    assert len(rows) == 3


def test_avotu_registrs():
    assert len({s["id"] for s in SOURCES}) == len(SOURCES)
    assert all(s["url"].startswith("https://") for s in SOURCES)
