import os
from pathlib import Path
import shutil
import sys
import tempfile


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Point the app at a throwaway directory before anything imports app.config,
# so a test run can never touch a real data directory.
TEST_DATA_DIR = tempfile.mkdtemp(prefix="invoice-receipt-tests-")
os.environ["DATA_DIR"] = TEST_DATA_DIR


def pytest_sessionfinish(session, exitstatus):
    del session, exitstatus
    from app.db import dispose_engine

    dispose_engine()
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
