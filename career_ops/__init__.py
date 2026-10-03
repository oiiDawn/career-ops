"""Local job-search business operations."""

import os
from pathlib import Path
import sys

if Path(sys.argv[0]).resolve().is_relative_to(Path(__file__).resolve().parents[1] / "tests"):
    # Offline tests and the CLI processes they spawn never send traces unless a test opts in.
    os.environ.setdefault("LANGFUSE_TRACING_ENABLED", "false")
