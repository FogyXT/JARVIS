"""
Structured logging system for JARVIS.

Použitie:
    from tools.jarvis_logging import log

    log.info("Správa", module="memory")
    log.debug("Detail", module="episodic", data={"key": "value"})
    log.error("Chyba", exc_info=True)

    @log.trace()
    def moja_funkcia(x, y):
        return x + y

Konfigurácia:
    LOG_LEVEL=DEBUG  v .env  (default: INFO)
    LOG_FILE=jarvis.log       (default)
    LOG_JSON=true             (JSON output pre strojové parsovanie)
"""

import os
import sys
import json
import time
import logging
import traceback
import functools
import inspect
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional, Any, Callable

# ── Config ────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT)
LOG_FILE = os.environ.get("LOG_FILE", os.path.join(LOG_DIR, "jarvis.log"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_JSON = os.environ.get("LOG_JSON", "").lower() in ("true", "1", "yes")

# ── Color codes (Windows compatible via colorama if available) ───────────

try:
    import colorama
    colorama.init()
    COLORS = {
        "DEBUG": colorama.Fore.CYAN,
        "INFO": colorama.Fore.GREEN,
        "WARN": colorama.Fore.YELLOW,
        "ERROR": colorama.Fore.RED,
        "RESET": colorama.Style.RESET_ALL,
        "DIM": colorama.Style.DIM,
        "BRIGHT": colorama.Style.BRIGHT,
    }
except ImportError:
    COLORS = {k: "" for k in ["DEBUG", "INFO", "WARN", "ERROR", "RESET", "DIM", "BRIGHT"]}


# ── JSON Formatter ────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """Structured JSON log output for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "module": getattr(record, "module_name", record.name),
            "function": getattr(record, "func_name", record.funcName),
            "line": record.lineno,
            "message": record.getMessage(),
        }
        # Include extra data if present
        extra = getattr(record, "extra_data", None)
        if extra:
            data["data"] = extra
        # Include exception if present
        if record.exc_info and record.exc_info[1]:
            data["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }
        return json.dumps(data, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-friendly colored console output."""

    def format(self, record: logging.LogRecord) -> str:
        color = COLORS.get(record.levelname, "")
        reset = COLORS["RESET"]
        dim = COLORS["DIM"]
        bright = COLORS["BRIGHT"]

        ts = datetime.now().strftime("%H:%M:%S")
        level = f"{color}{record.levelname:<5}{reset}"
        module = getattr(record, "module_name", record.name)
        mod_str = f"{dim}[{module}]{reset}"
        msg = f"{bright}{record.getMessage()}{reset}"

        line = f"{dim}{ts}{reset} {level} {mod_str} {msg}"

        # Add extra data on new line if present
        extra = getattr(record, "extra_data", None)
        if extra:
            line += f"\n{dim}  ╰─ {json.dumps(extra, ensure_ascii=False, default=str)}{reset}"

        # Exception on new line
        if record.exc_info and record.exc_info[1]:
            tb = traceback.format_exception(*record.exc_info)
            line += f"\n{color}" + "".join(tb) + reset

        return line


# ── Logger setup ──────────────────────────────────────────────────────────

_logger: Optional[logging.Logger] = None
_tracer_depth = 0  # pre odsadenie trace výstupov


def _get_logger() -> logging.Logger:
    """Lazy init loggera s rotating file handlerom."""
    global _logger
    if _logger is not None:
        return _logger

    _logger = logging.getLogger("jarvis")
    _logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    _logger.propagate = False

    # File handler (rotating: 10MB max, keep 3 backups)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)  # file always gets DEBUG
    if LOG_JSON:
        fh.setFormatter(JsonFormatter())
    else:
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-5s] [%(module_name)s] %(func_name)s:%(lineno)d — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    _logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    ch.setFormatter(ConsoleFormatter())
    _logger.addHandler(ch)

    return _logger


# ── Public API ────────────────────────────────────────────────────────────

class LogProxy:
    """Proxy objekt — lazy init, aby prvý import nebol ťažký."""

    def _log(self, level: int, msg: str, module: str = "root", data: Any = None, exc_info: bool = False):
        logger = _get_logger()
        extra = {"module_name": module, "func_name": "—", "extra_data": data}
        # Zisti volajúcu funkciu
        frame = sys._getframe(2)
        extra["func_name"] = frame.f_code.co_name
        logger.log(level, msg, extra=extra, exc_info=exc_info)

    def debug(self, msg: str, module: str = "root", data: Any = None):
        self._log(logging.DEBUG, msg, module=module, data=data)

    def info(self, msg: str, module: str = "root", data: Any = None):
        self._log(logging.INFO, msg, module=module, data=data)

    def warn(self, msg: str, module: str = "root", data: Any = None):
        self._log(logging.WARNING, msg, module=module, data=data)

    def error(self, msg: str, module: str = "root", data: Any = None, exc_info: bool = False):
        self._log(logging.ERROR, msg, module=module, data=data, exc_info=exc_info)

    def trace(self, module: str = None):
        """Decorator: loguje volanie funkcie s argumentami, návratovou hodnotou a trvaním.

        Použitie:
            @log.trace(module="memory")
            def moja_funkcia(x):
                return x * 2
        """
        def decorator(func: Callable) -> Callable:
            mod = module or func.__module__.split(".")[-1]

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                global _tracer_depth
                indent = "  " * _tracer_depth
                _tracer_depth += 1

                # Skráť argumenty pre log
                args_repr = []
                for a in args:
                    s = str(a)
                    if len(s) > 80:
                        s = s[:77] + "..."
                    args_repr.append(s)
                for k, v in kwargs.items():
                    s = str(v)
                    if len(s) > 80:
                        s = s[:77] + "..."
                    args_repr.append(f"{k}={s}")

                self.debug(f"{indent}▶ {func.__name__}({', '.join(args_repr)})", module=mod)
                t0 = time.perf_counter()

                try:
                    result = func(*args, **kwargs)
                    elapsed = (time.perf_counter() - t0) * 1000
                    res_repr = str(result)
                    if len(res_repr) > 100:
                        res_repr = res_repr[:97] + "..."
                    self.debug(f"{indent}◀ {func.__name__} → {res_repr} ({elapsed:.1f}ms)", module=mod)
                    return result
                except Exception:
                    elapsed = (time.perf_counter() - t0) * 1000
                    self.error(
                        f"{indent}✕ {func.__name__} FAILED ({elapsed:.1f}ms)",
                        module=mod,
                        exc_info=True,
                    )
                    raise
                finally:
                    _tracer_depth -= 1

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                global _tracer_depth
                indent = "  " * _tracer_depth
                _tracer_depth += 1

                self.debug(f"{indent}▶ {func.__name__}() [async]", module=module or "root")
                t0 = time.perf_counter()

                try:
                    result = await func(*args, **kwargs)
                    elapsed = (time.perf_counter() - t0) * 1000
                    self.debug(f"{indent}◀ {func.__name__} → ... ({elapsed:.1f}ms)", module=module or "root")
                    return result
                except Exception:
                    elapsed = (time.perf_counter() - t0) * 1000
                    self.error(
                        f"{indent}✕ {func.__name__} FAILED ({elapsed:.1f}ms)",
                        module=module or "root",
                        exc_info=True,
                    )
                    raise
                finally:
                    _tracer_depth -= 1

            if inspect.iscoroutinefunction(func):
                return async_wrapper
            return wrapper
        return decorator


log = LogProxy()

# ── Quick self-test ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== LOG SYSTEM SELF-TEST ===\n")

    log.info("Systém logovania spustený", module="logging")
    log.debug("Debug informácia", module="logging", data={"test": True, "value": 42})
    log.warn("Varovanie — toto je test", module="logging")

    @log.trace(module="test")
    def test_func(a, b):
        return a + b

    @log.trace(module="test")
    def failing_func(x):
        raise ValueError(f"Testovacia chyba: {x}")

    print("\n--- Testing trace decorator ---")
    result = test_func(3, 4)
    print(f"  test_func result: {result}")

    print("\n--- Testing error trace ---")
    try:
        failing_func("bad input")
    except ValueError:
        print("  Exception caught (see log above)")

    log.info("Self-test dokončený", module="logging", data={"log_file": LOG_FILE})
    print(f"\n=== Log file: {LOG_FILE} ===")
