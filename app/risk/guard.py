import json
from datetime import datetime, timedelta
from pathlib import Path


class RiskGuard:
    def __init__(
        self,
        market: str = "TW",
        max_position_pct: float = 0.15,
        max_daily_loss_pct: float = 0.025,
        max_drawdown_pct: float = 0.12,
        cooldown_minutes: int = 60,
        kelly_fraction: float = 0.4,
        circuit_breaker_levels: dict | None = None,
    ):
        self.market = market
        self.max_position_pct = max_position_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.cooldown_minutes = cooldown_minutes
        self.kelly_fraction = kelly_fraction

        self.circuit_breaker_levels = circuit_breaker_levels or {
            "reduce": 0.06, "halt": 0.10, "kill": 0.15,
        }

        self.peak_equity = 0.0
        self.daily_start_equity = 0.0
        self.circuit_breaker_until = None
        self.circuit_breaker_level = "normal"
        self.kill_switch_active = False

    def update_equity(self, equity: float):
        if equity > self.peak_equity:
            self.peak_equity = equity

    def reset_daily(self, equity: float):
        self.daily_start_equity = equity

    def check_order(
        self, symbol, side, qty, price,
        portfolio_value, current_position_value=0.0, current_equity=1_000_000.0,
    ) -> dict:
        now = datetime.now()

        if self.kill_switch_active:
            return {"approved": False, "reason": "KILL_SWITCH_ACTIVE"}

        if self.circuit_breaker_until and now < self.circuit_breaker_until:
            return {
                "approved": False,
                "reason": f"CIRCUIT_BREAKER_{self.circuit_breaker_level.upper()}",
                "until": self.circuit_breaker_until.isoformat(),
            }

        if self.peak_equity > 0:
            dd = (self.peak_equity - current_equity) / self.peak_equity

            if dd >= self.circuit_breaker_levels["kill"]:
                self.circuit_breaker_until = now + timedelta(minutes=self.cooldown_minutes)
                self.circuit_breaker_level = "kill"
                return {"approved": False, "reason": f"KILL_DRAWDOWN_{dd:.2%}"}

            if dd >= self.circuit_breaker_levels["halt"]:
                self.circuit_breaker_level = "halt"
                return {"approved": False, "reason": f"HALT_DRAWDOWN_{dd:.2%}"}

            if dd >= self.circuit_breaker_levels["reduce"]:
                self.circuit_breaker_level = "reduce"
                return {"approved": True,
                        "adjusted_qty": max(0, int(qty * 0.5)),
                        "reason": f"REDUCE_DRAWDOWN_{dd:.2%}"}

        if self.daily_start_equity > 0:
            daily_loss = (self.daily_start_equity - current_equity) / self.daily_start_equity
            if daily_loss > self.max_daily_loss_pct:
                return {"approved": False, "reason": f"DAILY_LOSS_{daily_loss:.2%}"}

        if side == "BUY" and price > 0:
            new_position = current_position_value + qty * price
            position_pct = new_position / (portfolio_value + 1e-9)

            if position_pct > self.max_position_pct:
                max_qty = int((self.max_position_pct * portfolio_value - current_position_value) / price)
                max_qty = max(0, max_qty)
                return {"approved": True, "adjusted_qty": max_qty,
                        "reason": f"POSITION_LIMIT_{position_pct:.2%}"}

        return {"approved": True, "adjusted_qty": qty, "reason": "PASS"}

    def kelly_position(self, win_rate, avg_win, avg_loss, portfolio_value) -> float:
        if avg_loss <= 0:
            return 0.0
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p
        kelly = (p * b - q) / (b + 1e-9)
        kelly = max(0.0, min(kelly, 0.25))
        return portfolio_value * kelly * self.kelly_fraction

    def activate_kill_switch(self, reason: str = "manual"):
        self.kill_switch_active = True
        self.circuit_breaker_until = datetime.now() + timedelta(minutes=self.cooldown_minutes)
        return {"kill_switch": "ACTIVE", "reason": reason}

    def deactivate_kill_switch(self):
        self.kill_switch_active = False
        self.circuit_breaker_until = None
        return {"kill_switch": "INACTIVE"}

    def persist(self, path: str):
        state = {
            "market": self.market,
            "peak_equity": self.peak_equity,
            "daily_start_equity": self.daily_start_equity,
            "circuit_breaker_until": (
                self.circuit_breaker_until.isoformat()
                if self.circuit_breaker_until else None
            ),
            "circuit_breaker_level": self.circuit_breaker_level,
            "kill_switch_active": self.kill_switch_active,
            "saved_at": datetime.now().isoformat(),
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f, indent=2)

    def load(self, path: str):
        try:
            with open(path) as f:
                state = json.load(f)
            self.peak_equity = state.get("peak_equity", 0.0)
            self.daily_start_equity = state.get("daily_start_equity", 0.0)
            self.circuit_breaker_level = state.get("circuit_breaker_level", "normal")
            self.kill_switch_active = state.get("kill_switch_active", False)
            cb = state.get("circuit_breaker_until")
            self.circuit_breaker_until = datetime.fromisoformat(cb) if cb else None
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"RiskGuard load error: {e}")


def build_tw_guard() -> RiskGuard:
    return RiskGuard(market="TW", max_position_pct=0.15,
                     max_daily_loss_pct=0.025, max_drawdown_pct=0.12,
                     kelly_fraction=0.4)


def build_us_guard() -> RiskGuard:
    return RiskGuard(market="US", max_position_pct=0.20,
                     max_daily_loss_pct=0.03, max_drawdown_pct=0.15,
                     kelly_fraction=0.5)
