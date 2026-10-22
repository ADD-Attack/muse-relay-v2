"""Receiver-timed resting permits.

A challenge is issued on this process's monotonic clock and can be used
once. The motion permit ends at issuance plus the gateway's remaining
lease, and never later than issuance plus SYNC_PERMIT_S (2 seconds).
That cap is not the 900/30/3600 advisory claim lease.

Epochs are persisted before a permit is enabled. Sequences live only for
this boot. A newer epoch wins even when its sequence is lower. A rolled
or older epoch does not revive motion. Persistence failure leaves the
current permit untouched and records sync_error.
"""
import json
import os
import secrets
import uuid

SYNC_PERMIT_S = 2.0
SYNC_REFRESH_S = 0.5


class ClaimSync:
    def __init__(self, directory):
        self.directory = os.path.abspath(directory)
        self.path = os.path.join(self.directory, "accepted-epoch.json")
        self.boot = str(uuid.uuid4())
        self.challenges = {}
        self.consumed = {}
        self.accepted_epoch = 0
        self.accepted_seq = -1
        self.pairing = None
        self.identity = None
        self.sync_error = None
        self._load()

    def issue(self, now):
        token = secrets.token_urlsafe(18)
        self.challenges[token] = {"boot": self.boot, "issued": float(now), "used": False}
        return {"ok": True, "challenge": token, "boot": self.boot}

    def rotate_boot(self):
        """New hands boot: grants die with the old boot. The epoch floor stays."""
        self.boot = str(uuid.uuid4())
        self.challenges.clear()
        self.consumed.clear()
        self.accepted_seq = -1
        self.identity = None
        self._load()

    def evaluate(self, message, now, resting):
        if not _shaped(message):
            return {"applied": False, "invalid": True}
        epoch = message["epoch"]
        seq = message["seq"]
        held = message["held"]
        pairing = message["pairing"]
        boot = message["boot"]
        token = message["challenge"]
        claim_id = message.get("claim_id")
        identity = (epoch, seq, bool(held), claim_id)
        record = self.challenges.get(token)
        if boot != self.boot or record is None or record["boot"] != self.boot:
            return {"applied": False}
        if record["used"]:
            if self.consumed.get(token) == identity:
                return {"applied": True}
            return {"applied": False}
        issued = record["issued"]
        record["used"] = True
        self.consumed[token] = identity
        if now > issued + SYNC_PERMIT_S:
            return {"applied": False}
        if self.pairing is not None and pairing != self.pairing:
            return {"applied": False}
        if epoch < self.accepted_epoch or (epoch == self.accepted_epoch and seq < self.accepted_seq):
            return {"applied": False}
        if epoch == self.accepted_epoch and seq == self.accepted_seq:
            if self.identity == identity:
                return {"applied": True}
            return {"applied": False}
        expires_in = float(message["expires_in"])
        deadline = None
        if held and expires_in > 0:
            cap = min(expires_in, SYNC_PERMIT_S)
            if now >= issued + cap:
                return {"applied": False}
            deadline = issued + cap
        if not self._persist(epoch, pairing):
            return {"applied": False}
        self.accepted_epoch = epoch
        self.accepted_seq = seq
        self.pairing = pairing
        self.identity = identity
        _apply(resting, held, deadline, seq, now, message.get("claim_id"))
        return {"applied": True}

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                record = json.load(handle)
            epoch = record.get("epoch")
            pairing = record.get("pairing")
            if type(epoch) is not int or isinstance(epoch, bool) or epoch < 1:
                raise ValueError("epoch")
            if not isinstance(pairing, str) or not pairing:
                raise ValueError("pairing")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.sync_error = f"accepted epoch unreadable: {exc}"
            self.accepted_epoch = 0
            self.pairing = None
            return
        self.accepted_epoch = epoch
        self.pairing = pairing
        self.sync_error = None

    def _persist(self, epoch, pairing):
        try:
            os.makedirs(self.directory, exist_ok=True)
            temporary = self.path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"epoch": epoch, "pairing": pairing}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            self.sync_error = f"accepted epoch was not stored: {exc}"
            return False
        self.sync_error = None
        return True


def _shaped(message):
    if not isinstance(message, dict):
        return False
    epoch, seq = message.get("epoch"), message.get("seq")
    held, expires = message.get("held"), message.get("expires_in")
    if type(epoch) is not int or isinstance(epoch, bool) or epoch < 1:
        return False
    if type(seq) is not int or isinstance(seq, bool) or seq < 1:
        return False
    if not isinstance(held, bool):
        return False
    if isinstance(expires, bool) or not isinstance(expires, (int, float)):
        return False
    if not isinstance(message.get("pairing"), str) or not message.get("pairing"):
        return False
    if not isinstance(message.get("boot"), str) or not message.get("boot"):
        return False
    if not isinstance(message.get("challenge"), str) or not message.get("challenge"):
        return False
    claim_id = message.get("claim_id", None)
    if claim_id is not None and not isinstance(claim_id, str):
        return False
    return True


def _apply(resting, held, deadline, seq, now, claim_id):
    with resting._lock:
        was_held = resting.claim_held(now)
        previous = getattr(resting, "claim_id", None)
        same_claim = isinstance(claim_id, str) and claim_id != "" and claim_id == previous
        resting.claim_seq = seq
        resting.claim_id = claim_id
        if held and deadline is not None and deadline > now:
            resting.claim_until = deadline
            # A gap in the same claim must not restart the ramp or clear an owner stop.
            if not was_held and not same_claim:
                resting.last_act_end = now
                resting.owner_stopped = False
        else:
            resting.claim_until = None
            resting._end()
