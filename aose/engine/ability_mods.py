_MOD_TABLE = {
    3: -3,
    4: -2, 5: -2,
    6: -1, 7: -1, 8: -1,
    9: 0, 10: 0, 11: 0, 12: 0,
    13: 1, 14: 1, 15: 1,
    16: 2, 17: 2,
    18: 3,
}


def ability_modifier(score: int) -> int:
    if score < 3:
        return -3
    if score > 18:
        return 3
    return _MOD_TABLE[score]


def prime_requisite_xp_multiplier(score: int) -> float:
    if score <= 5:
        return 0.80
    if score <= 8:
        return 0.90
    if score <= 12:
        return 1.00
    if score <= 15:
        return 1.05
    return 1.10
