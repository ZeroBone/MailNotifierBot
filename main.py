from src.bot import Bot
import logging


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("mail_bot.log")
file_handler.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # logging.ERROR

formatter = logging.Formatter("%(asctime)s (%(name)s) [%(levelname)s]: %(message)s")

file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)


def main():

    logger.info("Initializing...")

    try:
        Bot("config.ini").run()
    except:
        logger.error("A global error occured.")


if __name__ == "__main__":
    main()
