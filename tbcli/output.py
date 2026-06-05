"""Output formatting — JSON by default, --pretty for human tables."""

import json
import sys
import io

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def output(data, pretty=False):
    """Print data as JSON or as a human-readable table."""
    if not pretty:
        print(json.dumps(data, indent=2, default=str))
        return

    if isinstance(data, list) and data:
        if isinstance(data[0], dict):
            print_table(data)
        else:
            for item in data:
                print(item)
    elif isinstance(data, dict):
        max_key = max(len(str(k)) for k in data.keys()) if data else 0
        for k, v in data.items():
            print(f"  {str(k).ljust(max_key)}  {v}")
    else:
        print(data)


def print_table(rows):
    """Print a list of dicts as an aligned table."""
    if not rows:
        return
    # Pick columns: use keys from first row
    cols = list(rows[0].keys())
    # Compute widths
    widths = {c: len(c) for c in cols}
    str_rows = []
    for r in rows:
        sr = {}
        for c in cols:
            val = r.get(c, "")
            if val is None:
                val = ""
            elif isinstance(val, bool):
                val = "Y" if val else ""
            elif isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            else:
                val = str(val)
            # Truncate long values
            if len(val) > 60:
                val = val[:57] + "..."
            sr[c] = val
            widths[c] = max(widths[c], len(val))
        str_rows.append(sr)

    # Header
    header = "  ".join(c.upper().ljust(widths[c]) for c in cols)
    print(header)
    print("  ".join("-" * widths[c] for c in cols))
    for sr in str_rows:
        print("  ".join(sr[c].ljust(widths[c]) for c in cols))
