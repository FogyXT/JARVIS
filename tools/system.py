import subprocess
import os


def execute_command(command, timeout=15, working_dir=None):
    """Spustí shell príkaz cez PowerShell a vráti stdout/stderr/exit kód.

    Args:
        command: PowerShell príkaz na spustenie
        timeout: max sekúnd (None = bez timeoutu)
        working_dir: pracovný adresár (None = aktuálny)
    """
    try:
        # Plytký timeout: ak je 0 alebo záporný, berieme ako None (bez timeoutu)
        effective_timeout = None
        if timeout is not None and timeout > 0:
            effective_timeout = float(timeout)

        kwargs = {
            "args": ["powershell", "-NoProfile", "-Command", command],
            "capture_output": True,
            "text": True,
            "errors": "replace",
        }
        if effective_timeout is not None:
            kwargs["timeout"] = effective_timeout
        if working_dir:
            kwargs["cwd"] = working_dir

        result = subprocess.run(**kwargs)

        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        parts = []
        if out:
            parts.append(f"STDOUT:\n{out[:2000]}")
        if err:
            parts.append(f"STDERR:\n{err[:1000]}")
        parts.append(f"Exit: {result.returncode}")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"Timeout po {timeout}s (príkaz: {command[:80]}...)"
    except FileNotFoundError:
        return "PowerShell sa nenašiel (chybí v systéme?)."
    except Exception as e:
        return f"Chyba execute_command: {e}"
