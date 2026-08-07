
import html


class EasyDisplay:
    def __init__(self, content: str = None):
        self.content = content
        
        
    def __str__(self):
        return self.content if self.content else ''


