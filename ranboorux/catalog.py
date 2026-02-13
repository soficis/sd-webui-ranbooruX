from __future__ import annotations

import csv
import os
from typing import Tuple


def validate_catalog_csv(path: str) -> Tuple[bool, str]:
    candidate = (path or "").strip()
    if not candidate:
        return False, "No CSV path provided"
    if not os.path.isfile(candidate):
        return False, f"File not found: {candidate}"
    try:
        with open(candidate, "r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            first_row = next(reader)
            if len(first_row) < 3:
                return False, f"Expected at least 3 columns, got {len(first_row)}"
            lowered = [str(cell or "").strip().lower() for cell in first_row]
            has_header = (
                len(lowered) >= 3 and lowered[0] in ("tag", "name") and lowered[1] == "category"
            )
            if not has_header:
                try:
                    int(str(first_row[1]).strip())
                    int(str(first_row[2]).strip())
                except Exception:
                    return False, "Headerless format requires numeric category/count in columns 2/3"
            checked = 0
            for row in reader:
                if not row:
                    continue
                if len(row) < 3:
                    return False, f"Row has {len(row)} columns; expected at least 3"
                try:
                    int(str(row[1]).strip())
                    int(str(row[2]).strip())
                except Exception:
                    return False, "Found non-numeric category/count values"
                checked += 1
                if checked >= 10:
                    break
        return True, "Valid CSV format"
    except StopIteration:
        return False, "CSV file is empty"
    except UnicodeDecodeError:
        return False, "CSV is not valid UTF-8"
    except Exception as exc:
        return False, str(exc)
