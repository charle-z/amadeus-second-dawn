"""Run a real single-decision vertical slice with python -m amadeus.demo."""
import argparse
import json
from pathlib import Path
from .core import Experiment
from .muse import MuseAgent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="amadeus.sqlite3")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--world", choices=("v1", "v2"), default="v1")
    args = parser.parse_args()
    exp = Experiment(Path(args.db))
    try:
        model = MuseAgent()
        start = exp.start(args.world, args.seed)
        result = exp.step(start["id"], model)
        restarted = exp.restart(start["id"])
        # Ensure the kill operation is demonstrated even when the first decision won.
        final = exp.restart(restarted["id"])
        print(json.dumps({"first_generation": start, "real_model_result": result,
                          "killed_generation": exp.get_generation(restarted["id"]),
                          "restart": final, "memory_count": len(exp.memories()),
                          "model": "muse-spark-1.3", "usage": model.last_usage}, indent=2))
    finally:
        exp.close()


if __name__ == "__main__":
    main()
