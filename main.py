import requests
import os
from typing import List, Tuple
from utils import SecretsManager
from bs4 import BeautifulSoup
from models import *
import re
import shutil
from pathlib import Path


class ETLDownloader:
    DOWNLOAD_PATH = "./download"

    def __init__(self):
        self.s = requests.Session()
        self.username, self.password = SecretsManager().get_secret()
        self.courses: List[Course] = []
        self.selected_course: Course = Course("", "")

    @staticmethod
    def _get_soup(html):
        return BeautifulSoup(html, "html.parser")

    def _get_tmp_dir(self):
        return os.path.join("downloads", self.selected_course.title, "tmp")

    def _get_video_dir(self, video: Video):
        return os.path.join(
            "downloads", self.selected_course.title, video.title + ".ts"
        )

    def login(self):
        res = self.s.post(
            url="https://sso.snu.ac.kr/safeidentity/modules/auth_idpwd",
            data=dict(si_id=self.username, si_pwd=self.password),
        )
        soup = self._get_soup(res.text)
        cert_data = {
            input_.get("name"): input_.get("value") for input_ in soup.find_all("input")
        }
        self.s.post(url="https://sso.snu.ac.kr/nls3/fcs", data=cert_data)

    def parse_course_list(self):
        soup = self._get_soup(self.s.get(url="http://etl.snu.ac.kr/").text)
        courses = soup.find(class_="course_lists").find_all(class_="course_box")
        self.courses = [
            Course(
                title=course.find("a").get("title"),
                url=course.find("a").get("href"),
            )
            for course in courses
        ]

    def select_course_to_download(self):
        print()
        for i, c in enumerate(self.courses, 1):
            print(f"[{i}] {c}")
        number = input("\n다운로드할 강좌의 번호를 입력하세요: ")
        self.selected_course = self.courses[int(number) - 1]

    def get_course_vods(self) -> List[Video]:
        soup = self._get_soup(self.s.get(url=self.selected_course.url).text)
        vods: List[Video] = []
        for instance in soup.find_all(class_="activityinstance"):
            href = instance.find("a").get("href")
            if "vod" not in href:
                continue
            vods.append(
                Video(
                    title=instance.find(class_="instancename").find(
                        text=True, recursive=False
                    ),
                    url=href,
                )
            )
        return list(set(vods))

    def _parse_stream_endpoint(self, url: str) -> Tuple[str, str]:
        html = self.s.get(url).text
        m = re.search(r"(http://etlstream.snu.ac.kr:1935.*\.mp4)", html)
        endpoint = m.group(1)
        m2 = re.search(
            r"chunklist_(.*)\.m3u8", self.s.get(endpoint + "/playlist.m3u8").text
        )
        media_id = m2.group(1)
        return endpoint, media_id

    def download_vod(self, video: Video):
        index = 0
        endpoint, media_id = self._parse_stream_endpoint(video.player_url)
        video.media_id = media_id
        directory = self._get_tmp_dir()
        print(f"\t[*] {video.title} 다운로드 중.", end="")
        while True:
            chunk_url = f"{endpoint}/media_{media_id}_{index}.ts"
            res = self.s.get(chunk_url)
            if res.status_code != 200:
                print("")
                break
            Path(directory).mkdir(parents=True, exist_ok=True)
            with open(
                os.path.join(directory, f"{index}_{media_id}.ts"),
                "wb",
            ) as f:
                f.write(res.content)
            index += 1
            print(".", end="")
        video.num_files = index

    def concat_files(self, video: Video):
        directory = self._get_tmp_dir()
        files = [f"{index}_{video.media_id}.ts" for index in range(video.num_files)]
        with open(
            self._get_video_dir(video),
            "wb",
        ) as outfile:
            for fname in files:
                with open(os.path.join(directory, fname), "rb") as infile:
                    shutil.copyfileobj(infile, outfile)

    def _delete_tmp_folder(self):
        shutil.rmtree(self._get_tmp_dir())

    def download_all_videos(self):
        videos = self.get_course_vods()
        for video in videos:
            if Path(self._get_video_dir(video)).exists():
                print(f"\t[*] {video.title}.ts 파일이 이미 존재하므로 건너뜁니다.")
                continue
            self.download_vod(video)
            self.concat_files(video)
            self._delete_tmp_folder()

    def main(self):
        self.login()
        self.parse_course_list()
        self.select_course_to_download()
        self.download_all_videos()


if __name__ == "__main__":
    downloader = ETLDownloader()
    downloader.main()
