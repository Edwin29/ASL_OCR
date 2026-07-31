from __future__ import annotations

import re

BOOK_ID = "ebs-2027-math1"
PROFILE_HINT = "EBS_SUNEUNG_TEUKGANG"
ZIP_PAGE_RE = re.compile(r"_(\d+)\.png$", re.IGNORECASE)
GOLDEN_CANDIDATES = [3, 4, 8, 12, 19, 20, 54, 102, 120, 140, 150]
