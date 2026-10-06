"""The shared six-calendar-month publication window for M28 interviews."""

from calendar import monthrange
from datetime import datetime, timedelta, timezone
import re


NEWSPAPER_INTERVIEWS_VERSION = 3
INTERVIEW_CATEGORY = "访谈与对话"
INTERVIEW_MONTHS = 6
SHANGHAI = timezone(timedelta(hours=8))


def has_interview_label(title):
    """Use explicit editorial labels, without judging fame or limiting subjects."""
    if not isinstance(title, str):
        return False
    if re.search(r"专访|访谈|对谈|独家对话|(?:^|[|｜丨])\s*(?:interview|Q\s*&\s*A)\b|\ban interview with\b",
                 title, re.I):
        return True
    # A diplomatic dialogue or a conference is not automatically an interview.
    if re.search(r"对话会|对话机制|战略对话|高层对话|高级别对话|文明对话|经贸对话|安全对话", title):
        return False
    return bool(re.search(r"(?:^|[|｜丨])\s*对话[^：:\n]{1,40}[：:]|对话\s*[|｜丨]", title))


def retain_interviews(articles, limit):
    """Reserve bounded feed slots for interviews, retaining display chronology."""
    selected = sorted(enumerate(articles), key=lambda pair: pair[1].get("category") != INTERVIEW_CATEGORY)[:limit]
    return [article for _, article in sorted(selected, key=lambda pair: pair[0])]


def interview_cutoff(now):
    """Subtract six calendar months in Beijing, clamping month-end dates."""
    local = now.astimezone(SHANGHAI)
    year, month = divmod(local.year * 12 + local.month - 1 - INTERVIEW_MONTHS, 12)
    month += 1
    return local.replace(year=year, month=month, day=min(local.day, monthrange(year, month)[1]))


def is_recent_interview(article, now=None):
    """Require a real, timezone-aware publication within the past six months."""
    if not isinstance(article, dict) or article.get("category") != INTERVIEW_CATEGORY:
        return False
    value = article.get("published_at")
    if not isinstance(value, str) or article.get("time_basis", "published") != "published":
        return False
    try:
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    current = now or datetime.now(SHANGHAI)
    return (published.tzinfo is not None and current.tzinfo is not None
            and interview_cutoff(current) <= published <= current)


def without_expired_interviews(articles, now=None):
    """Recheck cached editions without altering other sections or saved records."""
    current = now or datetime.now(SHANGHAI)
    return [article for article in articles
            if article.get("category") != INTERVIEW_CATEGORY or is_recent_interview(article, current)]
