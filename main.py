import datetime


def show_status():
    now = datetime.datetime.now()

    print("=" * 40)
    print("        AMS31 MONITORING SYSTEM")
    print("=" * 40)
    print(f"Время: {now.strftime('%H:%M:%S')}")
    print(f"Дата:  {now.strftime('%d.%m.%Y')}")
    print("Статус системы: ONLINE")
    print("=" * 40)


if __name__ == "__main__":
    show_status()