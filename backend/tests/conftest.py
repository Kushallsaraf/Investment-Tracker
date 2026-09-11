from __future__ import annotations

import os
from pathlib import Path

TEST_RUNTIME = Path("/tmp/portfolio-manager-pytest-runtime")
os.environ["PORTFOLIO_MANAGER_HOME"] = str(TEST_RUNTIME)
