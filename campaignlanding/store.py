"""Where the signups live.

One file, one line per person, appended under a lock. No database, no third-party
form service, no analytics, no trackers. For a page whose whole argument is that
you can check its claims, a mailing list you can read with `cat` is not a
limitation, it is the point.

Everything here takes a data directory rather than reading configuration, so it
can be used and tested without an app.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path


class SignupStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.file = self.data_dir / "signups.jsonl"
        # Watermark for the admin tag: what had been seen the last time the list
        # was opened. Kept beside the data rather than in the cookie, so the tag
        # is right on a device that has never seen it.
        self.seen_file = self.data_dir / "admin_seen.json"

    # ---- writing ---------------------------------------------------------

    def append(self, record: dict) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(self.file, "a", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        try:
            os.chmod(self.file, 0o600)
        except OSError:
            pass

    # ---- reading ---------------------------------------------------------

    def all(self) -> list[dict]:
        """Every stored signup, oldest first. Unparseable lines are skipped rather
        than raising: one bad line should never make the whole list unreadable."""
        if not self.file.exists():
            return []
        out: list[dict] = []
        with open(self.file, encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
            try:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return out

    def read_seen(self) -> tuple[str, int]:
        try:
            data = json.loads(self.seen_file.read_text(encoding="utf-8"))
            return str(data.get("seen_ts") or ""), int(data.get("seen_count") or 0)
        except (OSError, ValueError, TypeError):
            return "", 0

    def write_seen(self, ts: str, count: int) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.seen_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"seen_ts": ts, "seen_count": count}), encoding="utf-8")
        os.replace(tmp, self.seen_file)  # atomic: never a half-written watermark
        try:
            os.chmod(self.seen_file, 0o600)
        except OSError:
            pass

    def state(self) -> dict:
        """Total, how many are new, and whether the tag should be lit.

        Both a timestamp and a count are compared. The count alone would go wrong
        the first time a junk entry is deleted; the timestamp alone would go
        wrong for two signups inside the same second, since timestamps are second
        resolution. Either one moving means there is something unseen.
        """
        recs = self.all()
        total = len(recs)
        newest = max((str(r.get("ts") or "") for r in recs), default="")
        seen_ts, seen_count = self.read_seen()
        unseen = max(total - seen_count, 0)
        active = bool(total) and (total != seen_count or newest > seen_ts)
        return {
            "total": total,
            "unseen": unseen,
            "active": active,
            "newest": newest,
            "records": recs,
        }
