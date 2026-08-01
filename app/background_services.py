import threading
from typing import Any

from .store import (
    SETTING_NINE_G_TRACE_PRODUCER_ENABLED,
    SETTING_VJ_WEB_SESSION_WARMER_ENABLED,
)


class BackgroundServiceManager:
    def __init__(self, nine_g_trace_producer: Any, vj_web_session_warmer: Any) -> None:
        self._nine_g_trace_producer = nine_g_trace_producer
        self._vj_web_session_warmer = vj_web_session_warmer
        self._lock = threading.RLock()

    def apply(self, settings: dict[str, Any]) -> None:
        with self._lock:
            if bool(settings.get(SETTING_NINE_G_TRACE_PRODUCER_ENABLED, True)):
                self._nine_g_trace_producer._start_producer()
            else:
                self._nine_g_trace_producer._stop_producer()

            if bool(settings.get(SETTING_VJ_WEB_SESSION_WARMER_ENABLED, True)):
                self._vj_web_session_warmer._start_warmer()
            else:
                self._vj_web_session_warmer._stop_warmer()

    def stop_all(self) -> None:
        with self._lock:
            self._vj_web_session_warmer._stop_warmer()
            self._nine_g_trace_producer._stop_producer()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "nineGTraceProducer": self._nine_g_trace_producer.producer_status(),
                "vjWebSessionWarmer": self._vj_web_session_warmer.warmer_status(),
            }
