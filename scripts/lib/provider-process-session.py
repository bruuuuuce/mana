#!/usr/bin/env python3
"""Exec one provider as leader of a fresh process session.

There is intentionally no policy input here: the caller supplies only argv.
The worker supervisor can therefore signal the negative child PID to reach the
entire provider process group.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        return 2
    os.setsid()
    os.execv(sys.argv[1], sys.argv[1:])
    return 126


if __name__ == "__main__":
    raise SystemExit(main())
