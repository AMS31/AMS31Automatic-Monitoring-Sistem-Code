import datetime
import psutil
import time
import os
import subprocess
import json
import re


CPU_WARNING = 80
RAM_WARNING = 80
DISK_CRITICAL = 90
GPU_WARNING = 80

UPDATE_INTERVAL = 1


previous_net = psutil.net_io_counters()
previous_disk = psutil.disk_io_counters()
previous_time = time.time()


def format_speed(value):
    return f"{value / 1024 / 1024:.2f} MB/s"


def format_size(value):
    return f"{value / 1024 / 1024 / 1024:.2f} GB"


def run_powershell(script):
    try:
        full_script = (
            "[Console]::OutputEncoding = "
            "[System.Text.Encoding]::UTF8; "
            + script
        )

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                full_script
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=5
        )

        if result.returncode != 0:
            return None

        output = result.stdout.strip()

        if not output:
            return None

        return output

    except Exception:
        return None


def get_health(cpu, ram, disk, gpus):
    warnings = []

    if cpu >= CPU_WARNING:
        warnings.append(
            f"WARNING: CPU {cpu:.1f}%"
        )

    if ram >= RAM_WARNING:
        warnings.append(
            f"WARNING: RAM {ram:.1f}%"
        )

    if disk >= DISK_CRITICAL:
        warnings.append(
            f"CRITICAL: DISK {disk:.1f}%"
        )

    for gpu in gpus:
        load = gpu.get("load")

        if (
            load is not None
            and load >= GPU_WARNING
        ):
            warnings.append(
                f"WARNING: GPU "
                f"{gpu['name']} "
                f"{load:.1f}%"
            )

    if warnings:
        return warnings

    return ["SYSTEM HEALTH: OK"]


def get_speeds():
    global previous_net
    global previous_disk
    global previous_time

    try:
        current_net = psutil.net_io_counters()
        current_disk = psutil.disk_io_counters()
        current_time = time.time()

        elapsed = current_time - previous_time

        if elapsed <= 0:
            elapsed = 1

        download = (
            current_net.bytes_recv
            - previous_net.bytes_recv
        ) / elapsed

        upload = (
            current_net.bytes_sent
            - previous_net.bytes_sent
        ) / elapsed

        disk_read = (
            current_disk.read_bytes
            - previous_disk.read_bytes
        ) / elapsed

        disk_write = (
            current_disk.write_bytes
            - previous_disk.write_bytes
        ) / elapsed

        previous_net = current_net
        previous_disk = current_disk
        previous_time = current_time

        return (
            max(download, 0),
            max(upload, 0),
            max(disk_read, 0),
            max(disk_write, 0)
        )

    except Exception:
        return 0, 0, 0, 0


def get_windows_gpu_list():
    gpus = []

    script = """
    Get-CimInstance Win32_VideoController |
    Select-Object Name,AdapterRAM,DeviceID |
    ConvertTo-Json -Compress
    """

    output = run_powershell(script)

    if output is None:
        return []

    try:
        data = json.loads(output)

        if isinstance(data, dict):
            data = [data]

        for item in data:
            name = item.get("Name")

            if not name:
                name = "Unknown GPU"

            vram = None

            try:
                raw_vram = item.get("AdapterRAM")

                if raw_vram is not None:
                    raw_vram = int(raw_vram)

                    if raw_vram > 0:
                        vram = (
                            raw_vram
                            / 1024
                            / 1024
                            / 1024
                        )

            except (ValueError, TypeError):
                vram = None

            gpus.append({
                "name": str(name),
                "vram": vram,
                "load": None,
                "temperature": None,
                "device_id": item.get("DeviceID")
            })

    except Exception:
        return []

    return gpus


def get_gpu_engine_data():
    script = """
    Get-CimInstance `
    Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine `
    -ErrorAction SilentlyContinue |
    Select-Object Name,UtilizationPercentage |
    ConvertTo-Json -Compress
    """

    output = run_powershell(script)

    if output is None:
        return []

    try:
        data = json.loads(output)

        if isinstance(data, dict):
            data = [data]

        return data

    except Exception:
        return []


def get_gpu_load_groups():
    engine_data = get_gpu_engine_data()

    groups = {}

    for item in engine_data:
        try:
            instance_name = str(
                item.get("Name", "")
            )

            value = item.get(
                "UtilizationPercentage"
            )

            if value is None:
                continue

            value = float(value)

            if value < 0:
                continue

            match = re.search(
                r"luid_"
                r"(0x[0-9a-fA-F]+)_"
                r"(0x[0-9a-fA-F]+)_"
                r"phys_(\d+)",
                instance_name
            )

            if match:
                key = (
                    match.group(1),
                    match.group(2),
                    match.group(3)
                )
            else:
                key = "unknown"

            if key not in groups:
                groups[key] = []

            groups[key].append(value)

        except Exception:
            continue

    result = []

    for key, values in groups.items():
        if not values:
            continue

        #
        # Windows создаёт отдельные
        # счётчики для 3D, Copy,
        # Video Decode и других
        # GPU engines.
        #
        # AMS31 берёт реальную загрузку
        # самого занятого engine.
        #
        # Значения не складываются
        # и не распределяются.
        #
        load = max(values)

        load = max(
            0.0,
            min(load, 100.0)
        )

        result.append({
            "key": key,
            "load": load
        })

    return result


def get_gpu_info():
    gpus = get_windows_gpu_list()

    if not gpus:
        return []

    load_groups = get_gpu_load_groups()

    #
    # Если Windows обнаружила только
    # одну GPU, все GPU Engine counters
    # относятся именно к ней.
    #
    # Поэтому значение можно связать
    # без угадывания.
    #
    if len(gpus) == 1:
        if load_groups:
            loads = [
                group["load"]
                for group in load_groups
            ]

            if loads:
                gpus[0]["load"] = max(loads)

        return gpus

    #
    # Несколько GPU.
    #
    # Performance Counters Windows
    # используют внутренний LUID,
    # а Win32_VideoController возвращает
    # другое имя устройства.
    #
    # Без дополнительного API или
    # драйверной библиотеки нельзя
    # гарантированно определить,
    # какой LUID принадлежит какой GPU.
    #
    # Поэтому AMS31 ничего не угадывает.
    #
    for gpu in gpus:
        gpu["load"] = None

    return gpus


def safe_cpu_percent():
    try:
        return psutil.cpu_percent(
            interval=0.1
        )
    except Exception:
        return 0.0


def safe_ram():
    try:
        return psutil.virtual_memory()
    except Exception:
        return None


def safe_disk():
    try:
        return psutil.disk_usage("C:/")
    except Exception:
        return None


def show_status():
    cpu = safe_cpu_percent()
    ram = safe_ram()
    disk = safe_disk()

    (
        download,
        upload,
        disk_read,
        disk_write
    ) = get_speeds()

    gpus = get_gpu_info()

    now = datetime.datetime.now()

    lines = [
        "=" * 70,
        "                    AMS31 MONITORING SYSTEM",
        "=" * 70,
        f"Time:       {now.strftime('%H:%M:%S')}",
        f"Date:       {now.strftime('%d.%m.%Y')}",
        "System:     ONLINE",
        "-" * 70,
        f"CPU:        {cpu:6.1f}%"
    ]

    if ram is not None:
        lines.append(
            f"RAM:        {ram.percent:6.1f}%"
        )
    else:
        lines.append(
            "RAM:           N/A"
        )

    lines.extend([
        "-" * 70,
        "DISK C:"
    ])

    if disk is not None:
        lines.extend([
            f"Usage:      {disk.percent:6.1f}%",
            f"Used:       {format_size(disk.used):>12}",
            f"Free:       {format_size(disk.free):>12}",
            f"Read:       {format_speed(disk_read):>12}",
            f"Write:      {format_speed(disk_write):>12}"
        ])
    else:
        lines.extend([
            "Usage:         N/A",
            "Used:          N/A",
            "Free:          N/A",
            "Read:          N/A",
            "Write:         N/A"
        ])

    lines.extend([
        "-" * 70,
        "GPU:"
    ])

    if gpus:
        for i, gpu in enumerate(gpus):
            lines.append(
                f"GPU {i}:      {gpu['name']}"
            )

            if gpu["load"] is not None:
                lines.append(
                    f"Load:       {gpu['load']:6.1f}%"
                )
            else:
                lines.append(
                    "Load:          N/A"
                )

            if (
                gpu["vram"] is not None
                and gpu["vram"] > 0
            ):
                lines.append(
                    f"VRAM:       {gpu['vram']:6.2f} GB"
                )
            else:
                lines.append(
                    "VRAM:          N/A"
                )

            if gpu["temperature"] is not None:
                lines.append(
                    f"Temp:       "
                    f"{gpu['temperature']:6.1f} C"
                )
            else:
                lines.append(
                    "Temp:           N/A"
                )

            lines.append("")

    else:
        lines.append(
            "No GPU information available."
        )

    lines.extend([
        "-" * 70,
        "NETWORK:",
        f"Download:   {format_speed(download):>12}",
        f"Upload:     {format_speed(upload):>12}",
        "-" * 70
    ])

    ram_percent = (
        ram.percent
        if ram is not None
        else 0
    )

    disk_percent = (
        disk.percent
        if disk is not None
        else 0
    )

    lines.extend(
        get_health(
            cpu,
            ram_percent,
            disk_percent,
            gpus
        )
    )

    lines.extend([
        "=" * 70,
        "Updating every second... Press CTRL+C to stop."
    ])

    print(
        "\033[H",
        end=""
    )

    for line in lines:
        print(
            f"\033[2K{line}"
        )

    print(
        "\033[J",
        end=""
    )


if __name__ == "__main__":
    os.system("cls")

    try:
        while True:
            show_status()

            time.sleep(
                UPDATE_INTERVAL
            )

    except KeyboardInterrupt:
        print("\n")
        print("=" * 70)
        print(
            "AMS31 MONITORING SYSTEM STOPPED."
        )
        print("=" * 70)