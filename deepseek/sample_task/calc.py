"""매출 집계 도우미."""


def parse_amount(text):
    """'1,234원', '₩5,000', ' 300 ' 같은 금액 글자를 정수로 바꾼다."""
    return int(text.replace(",", ""))


def average(values):
    """평균. 빈 목록이면 0."""
    return sum(values) // len(values)


def total_by_team(rows):
    """[(팀, 금액글자), ...] → {팀: 합계}"""
    totals = {}
    for team, amount in rows:
        totals[team] = parse_amount(amount)
    return totals
