import sys
from typing import Optional


class Spinner:
    def __init__(self, total: Optional[int] = None):
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.total = total
        self.index = 0

    def spin(self, type_str: str = "chunks") -> None:
        frame = self.frames[self.index % len(self.frames)]
        dots = ("." * (self.index % 3 + 1)).ljust(3)
        sys.stdout.write(
            f"\r{frame} Processing {dots} ({self.index + 1}/{self.total}) {type_str}" if self.total is not None else f"\r{frame} Processing {dots} {self.index + 1} {type_str}")
        sys.stdout.flush()
        self.index += 1

    def finish(self, message: str) -> None:
        sys.stdout.write("\r" + " " * 50 + "\r")
        sys.stdout.flush()
        print(f"✔ {message}")
