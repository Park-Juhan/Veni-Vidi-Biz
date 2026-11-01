from datetime import datetime, timedelta, timezone


def korean_time(iso_timestamp):
    """Store UTC internally; display Asia/Seoul (+09:00, no DST)."""
    return datetime.fromisoformat(iso_timestamp).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S KST')
