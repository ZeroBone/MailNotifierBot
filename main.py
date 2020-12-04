from src.bot import Bot


def main():
    print("[LOG]: Initializing...")

    Bot("config.ini").run()


if __name__ == "__main__":
    main()
