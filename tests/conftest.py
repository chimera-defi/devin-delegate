import os
import sys
from pathlib import Path

# Core modules still live in this repo.
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if _SCRIPTS.is_dir() and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# "Extras" tooling was moved out of this repo into the delegate-skill install.
# Add it so tests covering moved modules resolve.
_EXTRAS = Path(
    os.environ.get(
        "DELEGATE_EXTRAS_DIR",
        str(Path.home() / ".claude" / "skills" / "delegate-skill" / "delegate-extras" / "devin"),
    )
)
if _EXTRAS.is_dir() and str(_EXTRAS) not in sys.path:
    sys.path.insert(0, str(_EXTRAS))

# These test modules import tooling that now lives only in delegate-extras.
# When the install path is absent (e.g. minimal CI), skip them instead of
# failing collection with ImportError.
collect_ignore = []
if not _EXTRAS.is_dir():
    collect_ignore += [
        "test_coverage_new.py",
        "test_coverage_new2.py",
        "test_tune_timeouts.py",
        "test_review_devin_delegate.py",
    ]
