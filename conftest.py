import os
import shutil
import sys
import tempfile

# Keep every test artifact (state, logs, lyrics cache, user config) out of the
# repo's data/ directory and away from a running production/dev server.
# Must run before any test module imports `config`.
TEST_DATA_DIR = tempfile.mkdtemp(prefix="sc-sp-remote-test-")
os.environ["SC_SP_REMOTE_DATA_DIR"] = TEST_DATA_DIR
os.environ.pop("SC_SP_REMOTE_CONFIG", None)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))


def pytest_sessionfinish(session, exitstatus):
    # Best effort: Windows may still hold the session log file open.
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
