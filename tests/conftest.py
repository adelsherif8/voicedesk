import os
import tempfile

# Point the app at a throwaway database before anything imports app.main / app.db,
# so tests never write to data/voicedesk.db.
os.environ.setdefault("VOICEDESK_DB", os.path.join(tempfile.mkdtemp(prefix="voicedesk-test-"), "test.db"))
os.environ.pop("EVALS_INGEST_TOKEN", None)
os.environ.pop("ADMIN_TOKEN", None)


def pytest_terminal_summary(terminalreporter):
    """Report redaction precision/recall in the test output (tests/test_pii.py)."""
    try:
        from tests.test_pii import METRICS
    except Exception:
        return
    for name, m in METRICS.items():
        terminalreporter.write_line(f"PII redaction [{name}]: precision {m['precision']:.2f}, recall {m['recall']:.2f} "
                                    f"(tp {m['tp']}, fp {m['fp']}, fn {m['fn']})")
