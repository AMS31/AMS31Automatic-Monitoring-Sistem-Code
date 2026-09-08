import datetime
import psutil


def show_status():
    now = datetime.datetime.now()

    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk= psutil.disk_usage("C:/")

    print("=" * 40)
    print("        AMS31 MONITORING SYSTEM")
    print("=" * 40)
    print(f"Время: {now.strftime('%H:%M:%S')}")
    print(f"Дата:  {now.strftime('%d.%m.%Y')}")
    print("Статус системы: ONLINE")
    print(f"CPU: {cpu}%")
    print(f"RAM: {ram.percent}%")
    print(f"DISK C:{disk.percent}%")
    print("=" * 40)


if __name__ == "__main__":
    show_status()