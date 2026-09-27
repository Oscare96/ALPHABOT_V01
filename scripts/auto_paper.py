"""Run one guarded weekly paper rebalance attempt."""
import json

from src.auto_paper import run_automatic_paper


if __name__ == "__main__":
    print(json.dumps(run_automatic_paper(), indent=2))
