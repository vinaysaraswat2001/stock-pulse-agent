import logging
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "data_lineage.log"

_logger = logging.getLogger("data_lineage")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _logger.addHandler(_handler)


def log_fetch(query_type: str, source: str, question: str = "") -> None:
    """Record where an answer's underlying data actually came from —
    which Lakehouse file, notebook, or agent was hit, and for what question."""
    _logger.info(f"query={query_type} | source={source} | question={question!r}")
