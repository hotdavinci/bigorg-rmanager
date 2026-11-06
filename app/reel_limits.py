"""Local lifetime publication totals, independent of removable activity/insights."""
from sqlalchemy import Integer, String, cast, func, select
from sqlalchemy.orm import Session
from .models import ApplicationSetting, ScheduledPost, PostStatus


def reel_limit(session: Session) -> int:
    item=session.get(ApplicationSetting,"account_reel_limit")
    return max(0,int(item.value)) if item else 0


def published_total_expression(account_id):
    """Filter before the scheduler candidate limit, so blocked accounts cannot starve others."""
    saved=select(cast(ApplicationSetting.value,Integer)).where(
        ApplicationSetting.key=="account-published-total-"+cast(account_id, String)
    ).correlate_except(ApplicationSetting).scalar_subquery()
    history=select(func.count(ScheduledPost.id)).where(
        ScheduledPost.account_id==account_id,ScheduledPost.status==PostStatus.PUBLISHED
    ).correlate_except(ScheduledPost).scalar_subquery()
    return func.coalesce(saved,history,0)


def published_total(session: Session, account_id: int) -> int:
    item=session.get(ApplicationSetting,f"account-published-total-{account_id}")
    if item: return int(item.value)
    return session.scalar(select(func.count()).select_from(ScheduledPost).where(
        ScheduledPost.account_id==account_id,ScheduledPost.status==PostStatus.PUBLISHED)) or 0


def limit_reached(session: Session, account_id: int) -> bool:
    limit=reel_limit(session)
    return bool(limit and published_total(session,account_id)>=limit)


def save_published_total(session: Session, account_id: int, total: int|None=None):
    key=f"account-published-total-{account_id}"
    item=session.get(ApplicationSetting,key)
    if total is None:
        if item: return
        total=published_total(session,account_id)
    if item is None: item=ApplicationSetting(key=key); session.add(item)
    item.value=str(total)


def preserve_published_totals(session: Session):
    """Freeze legacy totals in the same transaction that removes published history."""
    for account_id in session.scalars(select(ScheduledPost.account_id).where(
            ScheduledPost.status==PostStatus.PUBLISHED).distinct()):
        save_published_total(session,account_id)
