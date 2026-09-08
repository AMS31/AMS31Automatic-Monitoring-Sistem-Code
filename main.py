import datetime
import psutil
import time


def format_speed(bytes_per_second):
    mb = bytes_per_second / 1024 / 1024
    return f"{mb:.2f} MB/s"


def show_status():
    now = datetime.datetime.now()

    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")

    net_before = psutil.net_io_counters()
    time.sleep(1)
    net_after = psutil.net_io_counters()

    download = net_after.bytes_recv - net_before.bytes_recv
    upload = net_after.bytes_sent - net_before.bytes_sent

    print("=" * 55)
    print("              AMS31 MONITORING SYSTEM")
    print("=" * 55)
    print(f"Time:   {now.strftime('%H:%M:%S')}")
    print(f"Date:   {now.strftime('%d.%m.%Y')}")
    print("System: ONLINE")
    print(f"CPU:    {cpu}%")
    print(f"RAM:    {ram.percent}%")
    print(f"DISK:   {disk.percent}%")
    print(f"NET ↓:  {format_speed(download)}")
    print(f"NET ↑:  {format_speed(upload)}")
    print("=" * 55)


if __name__ == "__main__":
    show_status()