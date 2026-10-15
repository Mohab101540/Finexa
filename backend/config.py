import os
from datetime import date

TODAY = date.fromisoformat(os.getenv("FINEXA_TODAY", "2026-10-20"))
