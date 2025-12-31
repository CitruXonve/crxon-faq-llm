import sys


class Spinner:
    def __init__(self, total: int):
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.total = total
        self.index = 0

    def spin(self) -> None:
        frame = self.frames[self.index % len(self.frames)]
        sys.stdout.write(
            f"\r{frame} Processing posts... ({self.index + 1}/{self.total})")
        sys.stdout.flush()
        self.index += 1

    def finish(self, message: str) -> None:
        sys.stdout.write("\r" + " " * 50 + "\r")
        sys.stdout.flush()
        print(f"✔ {message}")
