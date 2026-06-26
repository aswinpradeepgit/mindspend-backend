"""Level math — ported from frontend lib/gamification/levels.ts. Keep in sync."""

import math


def xp_for_level(n: int) -> int:
    if n <= 1:
        return 0
    return math.floor(100 * (n - 1) ** 1.6)


def level_from_xp(xp: int) -> int:
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
        if level >= 50:
            break
    return level
