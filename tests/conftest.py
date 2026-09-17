import os
import pathlib
import sys
import tempfile

# Test isolation: point the app at a throwaway data file BEFORE app.main is
# imported (the store is created at import time). The live demo state under
# data/ must never be touched by the suite.
_TEST_DATA = pathlib.Path(tempfile.gettempdir()) / "carecap-test-carecap.json"
if _TEST_DATA.exists():
    _TEST_DATA.unlink()
os.environ["CARECAP_DATA"] = str(_TEST_DATA)

# Make `app` importable regardless of how pytest is invoked.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
