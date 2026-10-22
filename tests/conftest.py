import os
import tempfile

# Point the app at a throwaway database before anything imports app.main / app.db,
# so tests never write to data/voicedesk.db.
os.environ.setdefault("VOICEDESK_DB", os.path.join(tempfile.mkdtemp(prefix="voicedesk-test-"), "test.db"))
os.environ.pop("EVALS_INGEST_TOKEN", None)
