import asyncio
import functools
import threading
import time
from datetime import datetime


class TradingWatchdog:
    def __init__(self, alert_urls: list[str] | None = None):
        self.alert_urls = alert_urls or []
        self._watchdogs: dict[str, datetime] = {}
        self._watchdog_started: set[str] = set()
        self._ops = None
        self._lock = threading.Lock()

    def _fire_alert(self, name: str, elapsed: float):
        msg = f"[CRITICAL] {name} 已 {elapsed:.0f} 秒無心跳。時間：{datetime.now().isoformat()}"
        print(msg)
        if self._ops:
            try:
                self._ops.fire_critical(msg)
            except Exception:
                pass

    def monitor(self, name: str, timeout_seconds: float = 30.0):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with self._lock:
                    self._watchdogs[name] = datetime.now()

                if name not in self._watchdog_started:
                    self._watchdog_started.add(name)

                    def watchdog_loop():
                        while True:
                            time.sleep(timeout_seconds / 2)
                            with self._lock:
                                last = self._watchdogs.get(name)
                            if last:
                                elapsed = (datetime.now() - last).total_seconds()
                                if elapsed > timeout_seconds:
                                    self._fire_alert(name, elapsed)

                    t = threading.Thread(target=watchdog_loop, daemon=True)
                    t.start()

                return func(*args, **kwargs)
            return wrapper
        return decorator

    def instrument_async(self, name: str, timeout_seconds: float = 30.0):
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                self._watchdogs[name] = datetime.now()

                if name not in self._watchdog_started:
                    self._watchdog_started.add(name)

                    async def watchdog_loop():
                        while True:
                            await asyncio.sleep(timeout_seconds / 2)
                            last = self._watchdogs.get(name)
                            if last:
                                elapsed = (datetime.now() - last).total_seconds()
                                if elapsed > timeout_seconds:
                                    self._fire_alert(name, elapsed)

                    asyncio.create_task(watchdog_loop())

                return await func(*args, **kwargs)
            return wrapper
        return decorator
