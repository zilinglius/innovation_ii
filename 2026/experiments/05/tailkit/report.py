"""统计与结果文件（给定）。分位数用最近秩法，与第 06 讲一致。"""

import json
import math
from pathlib import Path
import statistics

RESULTS = Path("/tmp/lab05-results")


def rank(values, p):
    """最近秩分位数：从小到大第 ceil(p·n) 个。"""
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p * len(ordered))) - 1]


def describe(values):
    return {
        "n": len(values),
        "p50": rank(values, 0.5),
        "p90": rank(values, 0.9),
        "p99": rank(values, 0.99),
        "max": max(values),
        "mean": statistics.fmean(values),
    }


def line(block):
    return (f"n={block['n']} p50={block['p50']:.1f} p90={block['p90']:.1f} "
            f"p99={block['p99']:.1f} max={block['max']:.1f} mean={block['mean']:.1f}")


def save(result, label):
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{label}.json"
    path.write_text(json.dumps(result))
    return path


def load(label_or_path):
    path = Path(label_or_path)
    if not path.exists():
        path = RESULTS / f"{label_or_path}.json"
    return json.loads(path.read_text())
