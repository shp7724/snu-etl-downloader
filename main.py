import os
import re
import shutil
import sys
import time
from pathlib import Path
from threading import Thread
from typing import List, Tuple

import requests
import subprocess
from bs4 import BeautifulSoup

from models import *
from utils import SecretsManager


class ETLDownloader:
    DOWNLOAD_PATH = "downloads"

    def __init__(self):
        self.s = requests.Session()
        self.username, self.password = SecretsManager().get_secret()
        self.courses: List[Course] = []
        self.selected_course: Course = Course("", "")

    @staticmethod
    def _get_soup(html):
        return BeautifulSoup(html, "html.parser")

    def _get_tmp_dir(self):
        return os.path.join(self.DOWNLOAD_PATH, self.selected_course.title, "tmp")

    def _get_video_dir(self, video: Video, safe_filename=False, ext: str = "ts"):
        filename = f"{video.title}.{ext}"
        if safe_filename:
            filename = filename.replace("/", "-")
        return os.path.join(self.DOWNLOAD_PATH, self.selected_course.title, filename)

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
        if len(sys.argv) > 1:
            number = int(sys.argv[1])
        else:
            number = input("\n다운로드할 강좌의 번호를 입력하세요: ")
        self.selected_course = self.courses[int(number) - 1]

    def get_course_vods(self) -> List[Video]:
        soup = self._get_soup(self.s.get(url=self.selected_course.url).text)
        vods: List[Video] = []
        for instance in soup.find_all(class_="activityinstance"):
            try:
                href = instance.find("a").get("href")
            except AttributeError:
                continue
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

    def get_last_index(self, endpoint: str, media_id: str) -> int:
        index = 0
        while True:
            chunk_url = f"{endpoint}/media_{media_id}_{index}.ts"
            res = self.s.head(chunk_url)
            if res.status_code != 200:
                return index
            index += 1

    def download_proc(self, endpoint: str, media_id: str, index: str, directory: str):
        chunk_url = f"{endpoint}/media_{media_id}_{index}.ts"
        res = self.s.get(chunk_url)
        with open(
            os.path.join(directory, f"{index}_{media_id}.ts"),
            "wb",
        ) as f:
            f.write(res.content)
        print(".", end="", flush=True)
        self.done_num += 1

    def download_vod(self, video: Video):
        endpoint, media_id = self._parse_stream_endpoint(video.player_url)
        last_index = self.get_last_index(endpoint, media_id)

        video.media_id, video.num_files = media_id, last_index + 1

        directory = self._get_tmp_dir()
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"\t[*] {video.title} 다운로드 중.", end="", flush=True)

        self.done_num = 0
        for index in range(video.num_files):
            thread = Thread(
                target=self.download_proc, args=(endpoint, media_id, index, directory)
            )
            thread.start()
            time.sleep(0.05)

        while self.done_num < video.num_files:
            time.sleep(1)

        print(flush=True)

    def concat_files(self, video: Video):
        directory = self._get_tmp_dir()
        files = [f"{index}_{video.media_id}.ts" for index in range(video.num_files)]
        with open(
            self._get_video_dir(video, safe_filename=True),
            "wb",
        ) as outfile:
            for fname in files:
                with open(os.path.join(directory, fname), "rb") as infile:
                    shutil.copyfileobj(infile, outfile)

    def _delete_tmp_folder(self):
        try:
            shutil.rmtree(self._get_tmp_dir())
        except FileNotFoundError:
            return

    def convert_to_mp4(self, video):
        print(f"\t[*] {video.title} 변환 시작")
        infile = self._get_video_dir(video, safe_filename=True)
        outfile = self._get_video_dir(video, safe_filename=True, ext="mp4")
        subprocess.run(["ffmpeg", "-i", infile, outfile])
        os.remove(infile)
        print(f"\t[*] {video.title} 변환 완료")

    def download_all_videos(self):
        self._delete_tmp_folder()
        videos = self.get_course_vods()

        def download_video(video: Video):
            if Path(self._get_video_dir(video, safe_filename=True, ext="mp4")).exists():
                print(f"\t[*] {video.title}.mp4 파일이 이미 존재하므로 건너뜁니다.")
                return
            if Path(self._get_video_dir(video, safe_filename=True, ext="ts")).exists():
                print(f"\t[*] {video.title}.ts 파일이 이미 존재하므로 mp4로 변환 후 건너뜁니다.")
                self.convert_to_mp4(video)
                return
            self.download_vod(video)
            self.concat_files(video)
            self.convert_to_mp4(video)

        for video in videos:
            if "Lecture 11" in video.title or "digital" in video.title:
                download_video(video)
            # Thread(target=download_video, args=(video,)).start()
            # time.sleep(2)

        return
        for video in videos:
            if Path(self._get_video_dir(video, safe_filename=True)).exists():
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
        print("\n 다운로드 완료!")


if __name__ == "__main__":
    downloader = ETLDownloader()
    downloader.main()
