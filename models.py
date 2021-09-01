import re


class Course:
    def __init__(self, title: str, url: str):
        self.title = title
        self.url = url

    @property
    def course_id(self):
        m = re.search(r"id=(\d+)", self.url)
        return m.group(1)

    def __str__(self) -> str:
        return self.title


class Video(Course):
    def __init__(self, *args, **kwargs):
        super(Video, self).__init__(*args, **kwargs)
        self.media_id = ""
        self.num_files = -1

    @property
    def player_url(self):
        return self.url.replace("view", "viewer")

    def __eq__(self, other):
        if isinstance(other, Video):
            return self.url == other.url
        else:
            return False

    def __hash__(self):
        return hash(self.url)
