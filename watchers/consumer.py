"""Read one published generation. Contact and a heartbeat are not freshness."""
import os

from publish import Incomplete, read_published
from telemetry import load_status, observation_label


class Consumer:
    def __init__(self):
        self.high_water = None

    def check(self, root, status_path, now, stale_s, evidence_path=None, evidence_mark=None):
        status = load_status(status_path)
        label, stale = observation_label(status, now, stale_s)
        reason = None
        published = None
        try:
            published = read_published(root)
        except Incomplete:
            published = None
            if label == "fresh":
                label = "unknown"
                reason = "unpublished"
        generation = None if published is None else published["manifest"].get("generation")
        if generation is not None and self.high_water is not None and generation < self.high_water:
            label = "unknown"
            reason = "generation_reset"
        elif generation is not None:
            self.high_water = generation
        evidence = None
        if evidence_path is not None:
            try:
                size = os.path.getsize(evidence_path)
            except OSError:
                size = None
            evidence = "advanced" if size is not None and evidence_mark is not None and size > evidence_mark else "not_advanced"
        accepted = label == "fresh" and (evidence is None or evidence == "advanced")
        return {
            "label": label,
            "stale": stale,
            "reason": reason,
            "generation": generation,
            "evidence": evidence,
            "accepted": accepted,
            "published": published,
            "status": status,
        }
