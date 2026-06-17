class Entry:
    def __init__(self, entry_dict: dict) -> None:
        self.id: int = entry_dict["id"]
        self.title: str = entry_dict["title"]
        self.url: str = entry_dict["url"]
        self.feed_title: str = entry_dict["feed"]["title"]
        self.attempt: int = 0

    def __lt__(self, other: Entry, /) -> bool:
        return self.id < other.id

    def __eq__(self, other: object, /) -> bool:
        if not isinstance(other, Entry):
            return False
        return self.id == other.id

    def __repr__(self) -> str:
        return f"Entry(id={self.id}, title={self.title}, url={self.url}, feed_title={self.feed_title})"

    def __hash__(self) -> int:
        return hash(self.id)
