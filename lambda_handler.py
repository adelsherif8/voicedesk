"""AWS Lambda entrypoint (Lambda function URL -> Mangum -> FastAPI).

Lambda's filesystem is read-only except /tmp, so the bundled SQLite snapshot is copied to /tmp on a
cold start (VOICEDESK_DB=/tmp/voicedesk.db), the same reset-on-deploy behaviour as the free Render disk."""
import os
import shutil

DB = os.environ.setdefault("VOICEDESK_DB", "/tmp/voicedesk.db")
SEED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "voicedesk.db")
if not os.path.exists(DB) and os.path.exists(SEED):
    shutil.copyfile(SEED, DB)

from mangum import Mangum  # noqa: E402
from app.main import app  # noqa: E402

handler = Mangum(app, lifespan="auto")
