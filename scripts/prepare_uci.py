from __future__ import annotations

import argparse
from pathlib import Path

from retailpulse.batch import prepare_uci

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="UCI Online Retail CSV export")
    parser.add_argument("--output", type=Path, default=Path("data/landing/uci"))
    args = parser.parse_args()
    print(prepare_uci(args.source, args.output))
