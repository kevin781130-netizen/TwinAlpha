import hashlib
import json
from datetime import datetime
from pathlib import Path


class VerifiableAuditLog:
    def __init__(self, log_path: str = "./data_lake/audit/events.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._prev_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        if not self.log_path.exists():
            return "0" * 64
        last_hash = "0" * 64
        with open(self.log_path) as f:
            for line in f:
                try:
                    record = json.loads(line)
                    last_hash = record.get("hash", last_hash)
                except Exception:
                    continue
        return last_hash

    def append(self, event_type: str, data: dict) -> dict:
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type, "data": data,
            "prev_hash": self._prev_hash,
        }
        canonical = json.dumps(event, sort_keys=True, default=str)
        event["hash"] = hashlib.sha256(canonical.encode()).hexdigest()

        with open(self.log_path, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")

        self._prev_hash = event["hash"]
        return event

    def log_decision(self, symbol, action, reasoning, signal_sources):
        return self.append("TRADE_DECISION", {
            "symbol": symbol, "action": action,
            "reasoning": reasoning, "signal_sources": signal_sources,
        })

    def log_order(self, order_id, symbol, side, qty, price, status):
        return self.append("ORDER_EVENT", {
            "order_id": order_id, "symbol": symbol, "side": side,
            "qty": qty, "price": price, "status": status,
        })

    def log_risk_check(self, symbol, approved, reason):
        return self.append("RISK_CHECK", {
            "symbol": symbol, "approved": approved, "reason": reason,
        })

    def build_merkle_root(self, start_idx: int = 0, end_idx: int | None = None) -> str:
        hashes = []
        with open(self.log_path) as f:
            for i, line in enumerate(f):
                if i < start_idx:
                    continue
                if end_idx and i >= end_idx:
                    break
                try:
                    hashes.append(json.loads(line).get("hash", ""))
                except Exception:
                    continue

        if not hashes:
            return "0" * 64

        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])
            hashes = [
                hashlib.sha256((hashes[i] + hashes[i + 1]).encode()).hexdigest()
                for i in range(0, len(hashes), 2)
            ]
        return hashes[0]

    def verify_integrity(self) -> dict:
        prev_hash = "0" * 64
        errors = []
        count = 0

        if not self.log_path.exists():
            return {"total_records": 0, "errors": 0, "valid": True, "error_details": []}

        with open(self.log_path) as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    errors.append({"line": i, "error": "json parse failed"})
                    continue

                if record.get("prev_hash") != prev_hash:
                    errors.append({"line": i, "error": "hash chain broken",
                                   "expected": prev_hash,
                                   "actual": record.get("prev_hash")})

                actual_hash = record.get("hash")
                check = {k: v for k, v in record.items() if k != "hash"}
                canonical = json.dumps(check, sort_keys=True, default=str)
                expected_hash = hashlib.sha256(canonical.encode()).hexdigest()

                if actual_hash != expected_hash:
                    errors.append({"line": i, "error": "hash mismatch",
                                   "expected": expected_hash,
                                   "actual": actual_hash})

                prev_hash = actual_hash or prev_hash
                count += 1

        return {"total_records": count, "errors": len(errors),
                "valid": len(errors) == 0, "error_details": errors[:10]}
