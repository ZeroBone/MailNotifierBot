import configparser
import io
import os
import tempfile
import time
import json
import logging

import mailparser
from imapclient import IMAPClient
from imapclient.exceptions import LoginError
from telebot import TeleBot


logger = logging.getLogger(__name__)

message_breakers = ["\n", ", "]


def split(text: str, max_message_length: int = 4091) -> list:
    if len(text) >= max_message_length:
        last_index = max(
            map(
                lambda separator: text.rfind(separator, 0, max_message_length),
                message_breakers,
            )
        )
        good_part = text[:last_index]
        bad_part = text[last_index + 1:]
        return [good_part] + split(bad_part, max_message_length)
    else:
        return [text]


class Bot:

    def __init__(self, config_file):

        self.config_file = config_file

        self.parser = configparser.ConfigParser()
        self.parser.read(config_file)

        self.host = self.parser.get("mail", "host")
        self.login = self.parser.get("mail", "login")
        self.password = self.parser.get("mail", "password")
        self.last_uid = self.parser.getint("mail", "last_uid", fallback=0)
        self.read_only = self.parser.getboolean("mail", "read_only", fallback=False)
        self.criteria = self.parser.get("mail", "criteria", fallback="UNSEEN")
        self.folder = self.parser.get("mail", "folder", fallback="INBOX")
        self.ssl = self.parser.get("mail", "ssl", fallback=False)

        self.whitelist = [v for (k, v) in self.parser.items("whitelist")]

        if len(self.whitelist) > 0:
            logger.info("Whitelist enabled: %s", ",".join(self.whitelist))

        if self.read_only:
            try:
                with open(".mnbs") as bot_state_file:

                    bot_state = json.load(bot_state_file)

                    self.last_uid = max(self.last_uid, int(bot_state["last_uid"]))
            except FileNotFoundError:
                logger.warning("The state file was not found, is this the first startup?")
                logger.info("Creating bot state file...")

                bot_state = {"last_uid": 0}

                with open(".mnbs", "w") as state_file:
                    json.dump(bot_state, state_file)

        self.bot_token = self.parser.get("tg", "token")
        self.chat = self.parser.get("tg", "chat_id")

        self.bot = None

    def get_emails(self):

        with IMAPClient(self.host, ssl=self.ssl) as server:

            try:
                server.login(self.login, self.password)
            except LoginError:
                logger.error("Could not authenticate.")
                return

            server.select_folder(self.folder, readonly=self.read_only)

            mails = server.search(self.criteria)

            for uid, message_data in server.fetch(mails, "RFC822").items():

                if uid <= self.last_uid:
                    continue

                try:
                    mail = mailparser.parse_from_bytes(message_data[b"RFC822"])
                except TypeError:
                    pass
                else:
                    yield mail, uid

    def send_mail(self, mail: mailparser.MailParser) -> bool:

        subject = mail.subject

        sender_email_raw = mail.from_[0][1]

        if len(self.whitelist) > 0 and sender_email_raw not in self.whitelist:
            logger.info("Ignoring email from: %s", sender_email_raw)
            return False

        sender_email = " ".join(mail.from_[0])

        title = "{} from {}".format(subject, sender_email)

        logger.info("Sending mail: %s", title)

        if mail.text_html:

            text_html = "\n".join(mail.text_html)

            f = io.BytesIO(text_html.encode())
            f.name = title + ".html"

            self.bot.send_document(
                self.chat,
                f,
                caption=title,
            )

        elif mail.text_plain:

            message = "\n".join(mail.text_plain)

            self.bot.send_message(
                self.chat, split(message)[0]
            )

            if len(message) >= 2:
                f = io.BytesIO("{}\n\n{}".format(title, message).encode())
                f.name = title + ".txt"
                self.bot.send_document(self.chat, f, caption=title)

        if mail.attachments:

            with tempfile.TemporaryDirectory() as tmp_dir:

                mail.write_attachments(tmp_dir)

                for file in os.listdir(tmp_dir):
                    self.bot.send_document(
                        self.chat, open(os.path.join(tmp_dir, file), "rb")
                    )

        return True

    def run(self):

        self.bot = TeleBot(self.bot_token)

        logger.info("Initialized.")

        last_uid = None

        for email, mail_id in self.get_emails():

            logger.info("Processing mail: %s", mail_id)

            sent = self.send_mail(email)

            last_uid = str(mail_id)

            if sent:
                time.sleep(5)

        if not (last_uid is None) and self.read_only:

            bot_state = {"last_uid": last_uid}

            with open(".mnbs", "w") as state_file:
                json.dump(bot_state, state_file)

        logger.info("All emails processed.")
