from typing import Tuple


class SecretsManager:
    SECRET_PATH = "./.secrets"

    def __init__(self):
        self.username = ""
        self.password = ""

    def get_secret(self) -> Tuple[str, str]:
        if self.username != "" and self.password != "":
            return self.username, self.password
        try:
            with open(self.SECRET_PATH, "r") as f:
                lines = f.readlines()
                if len(lines) != 2:
                    raise FileNotFoundError
                self.username, self.password = [
                    line.replace("\n", "") for line in lines
                ]
        except FileNotFoundError:
            return self.set_secret()
        return self.username, self.password

    def set_secret(self) -> Tuple[str, str]:
        self.username = input("\neTL 아이디를 입력하세요: ")
        self.password = input("비밀번호를 입력하세요: ")
        with open(self.SECRET_PATH, "w") as f:
            f.writelines([self.username + "\n", self.password])
        return self.username, self.password
