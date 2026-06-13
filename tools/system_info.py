import subprocess
import datetime


def _run_ps(script):
    """Spustí PowerShell script a vráti stdout."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        return r.stdout.strip()
    except Exception as e:
        return f"Chyba: {e}"


def system_info(category="all"):
    """Získa informácie o systéme: disk, CPU, RAM, GPU, uptime.

    category: 'all' | 'disk' | 'cpu' | 'ram' | 'gpu' | 'uptime'
    """
    parts = []

    if category in ("all", "disk"):
        out = _run_ps(
            "Get-PSDrive C | Select-Object Used, Free | ForEach-Object { "
            "'Disk C: {0:F1} GB free / {1:F1} GB total' -f ($_.Free/1GB), (($_.Used+$_.Free)/1GB) }"
        )
        parts.append(out or "Disk C: nedostupné")

    if category in ("all", "cpu"):
        out = _run_ps(
            "Get-CimInstance Win32_Processor | "
            "ForEach-Object { 'CPU: {0} - {1}% vyuzitie' -f $_.Name, $_.LoadPercentage }"
        )
        parts.append(out or "CPU: nedostupné")

    if category in ("all", "ram"):
        out = _run_ps(
            "Get-CimInstance Win32_OperatingSystem | "
            "ForEach-Object { "
            "'RAM: {0:F1} GB free / {1:F1} GB total ({2}%)' -f "
            "($_.FreePhysicalMemory/1MB), ($_.TotalVisibleMemorySize/1MB), "
            "[math]::Round(($_.TotalVisibleMemorySize - $_.FreePhysicalMemory) / $_.TotalVisibleMemorySize * 100) }"
        )
        parts.append(out or "RAM: nedostupné")

    if category in ("all", "gpu"):
        out = _run_ps(
            "Get-CimInstance Win32_VideoController | "
            "ForEach-Object { "
            "'GPU: {0} | VRAM: {1:F1} GB | Driver: {2} | {3}x{4}' -f "
            "$_.Name, ($_.AdapterRAM/1GB), $_.DriverVersion, "
            "$_.CurrentHorizontalResolution, $_.CurrentVerticalResolution }"
        )
        parts.append(out or "GPU: nedostupné")

    if category in ("all", "uptime"):
        out = _run_ps(
            "$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime; "
            "$uptime = [datetime]::Now - $boot; "
            "'Uptime: {0} dni, {1} hodin, {2} minut' -f $uptime.Days, $uptime.Hours, $uptime.Minutes"
        )
        parts.append(out or "Uptime: nedostupné")

    return "\n".join(parts)
