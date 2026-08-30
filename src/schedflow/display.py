


class EasyDisplay:
    def __init__(self, content: str | None = None):
        self.content = content


    def __str__(self):
        return self.content if self.content else ''


