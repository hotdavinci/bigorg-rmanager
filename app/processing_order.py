"""Order only unprocessed occurrences; preserve completed checkpoint prefixes."""
import random


def order_pending_jobs(jobs: list[dict], completed: int = 0) -> None:
    if not 0 <= completed <= len(jobs):
        raise ValueError("Cursor de processamento inválido")
    for job in jobs[completed:]:
        if "planned_minute" not in job:
            if "when" in job:
                when = job["when"]
                job["planned_minute"] = (when.date() - job["current"]).days * 1440 + when.hour * 60 + when.minute
            else:
                job["planned_minute"] = random.Random(job["slot_key"]).randint(job["low"], job["high"])
    jobs[completed:] = sorted(jobs[completed:], key=lambda job: (
        job["current"].toordinal() * 1440 + job["planned_minute"],
        job["account_id"], job["slot_key"],
    ))
