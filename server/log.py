import logging
import os
import sys
import time

from config import LOG_DIR, config

os.makedirs(LOG_DIR, exist_ok=True)


class _ConsoleStream:
    def __init__(self, stream):
        self.stream = stream
    def write(self, msg):
        try:
            self.stream.write(msg)
        except UnicodeEncodeError:
            self.stream.write(msg.encode('utf-8', errors='replace').decode('utf-8'))
    def flush(self):
        self.stream.flush()


session_timestamp: str = time.strftime("%Y%m%d-%H%M%S")
log_file: str = os.path.join(LOG_DIR, f"server_{session_timestamp}.log")

log_level: int = getattr(logging, config["logLevel"].upper(), logging.INFO)
logger: logging.Logger = logging.getLogger("SCRemote")
logger.setLevel(log_level)

formatter: logging.Formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

file_handler: logging.FileHandler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler: logging.StreamHandler = logging.StreamHandler(stream=_ConsoleStream(sys.stderr))
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


def cleanup_old_logs() -> None:
    try:
        files: list[str] = [os.path.join(LOG_DIR, f) for f in os.listdir(LOG_DIR) if f.startswith("server_") and f.endswith(".log")]
        files.sort(key=os.path.getmtime, reverse=True)

        if len(files) > config["backupCount"]:
            for old_file in files[config["backupCount"]:]:
                os.remove(old_file)
                print(f"LogCleanup: Removed old log file: {os.path.basename(old_file)}")
    except Exception as e:
        print(f"LogCleanup: Error cleaning up logs: {e}")


cleanup_old_logs()
logger.info(f"Logging initialized. Session log: {os.path.basename(log_file)}")
