import configparser
import io
import os
import tempfile
import time

import mailparser
from imapclient import IMAPClient
from telebot import TeleBot


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

        self.whitelist = [v for (k, v) in self.parser.items("whitelist")]

        if len(self.whitelist) > 0:
            print("[LOG]: Ignoring emails except from:", self.whitelist)

        self.bot_token = self.parser.get("tg", "token")
        self.chat = self.parser.get("tg", "chat_id")

        self.bot = None

    def get_emails(self):

        with IMAPClient(self.host) as server:

            server.login(self.login, self.password)
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
            print("[LOG]: Ignoring email from:", sender_email_raw)
            return False

        sender_email = " ".join(mail.from_[0])

        title = "{} from {}".format(subject, sender_email)

        print("[LOG]: Sending mail:", title)

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

        print("[LOG]: Initialized.")

        for email, mail_id in self.get_emails():

            print("[LOG]: Processing mail:", mail_id)

            sent = self.send_mail(email)

            self.parser.set("mail", "last_uid", str(mail_id))
            self.parser.write(open(self.config_file, "w"))

            if sent:
                time.sleep(5)

        print("[LOG]: All emails processed.")
