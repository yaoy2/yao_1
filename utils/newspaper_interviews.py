"""The shared publication window for M28's weekly interview column."""

from datetime import datetime, timedelta, timezone


INTERVIEW_CATEGORY = "访谈与对话"
INTERVIEW_WINDOW = timedelta(days=7)
SHANGHAI = timezone(timedelta(hours=8))


def is_recent_interview(article, now=None):
    """Require a real, timezone-aware publication within the past seven days."""
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
            and current - INTERVIEW_WINDOW <= published <= current)


def without_expired_interviews(articles, now=None):
    """Recheck cached editions without altering other sections or saved records."""
    current = now or datetime.now(SHANGHAI)
    return [article for article in articles
            if article.get("category") != INTERVIEW_CATEGORY or is_recent_interview(article, current)]
