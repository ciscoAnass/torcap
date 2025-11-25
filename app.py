import sys
import time
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import getpass
from typing import List, Optional, Set

import mss
import requests


CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "interval_seconds": 10,
    "screenshot_folder": "",
    "server_url": "",
    "upload_password": "",
    "upload_batch_size": 10,
    "max_folder_size_mb": 500,
    "tor_socks_proxy": "socks5h://127.0.0.1:9050",
    "log_file": "screen_guard.log"
}


def setup_logging(log_file: str) -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    for h in list(logger.handlers):
        logger.removeHandler(h)

    log_path = Path(log_file)
    try:
        if log_path.exists():
            log_path.unlink()
    except Exception as e:
        print(f"[WARN] Could not delete old log file {log_path}: {e}", file=sys.stderr)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)


def load_or_create_config() -> dict:
    config_path = Path(CONFIG_FILE)

    if not config_path.exists():
        default_folder = Path.home() / "Pictures" / "Security"
        DEFAULT_CONFIG["screenshot_folder"] = str(default_folder)

        with config_path.open("w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)

        print(
            f"[INFO] {CONFIG_FILE} has been created with default settings.\n"
            f"Please open it, edit it, then run the program again."
        )
        sys.exit(0)

    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, value)

    return config


def ensure_folder(path_obj) -> Path:
    folder = Path(path_obj)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_folder_size_mb(folder: Path) -> float:
    total_bytes = 0
    for item in folder.rglob("*"):
        if item.is_file():
            total_bytes += item.stat().st_size
    return total_bytes / (1024 * 1024)


def rotate_screenshots(folder: Path, max_size_mb: float, protected: Optional[Set[Path]] = None) -> None:
    if max_size_mb <= 0:
        return

    current_size = get_folder_size_mb(folder)
    if current_size <= max_size_mb:
        return

    if protected is None:
        protected = set()

    logging.info(
        "Folder size %.2f MB exceeds limit %.2f MB. Starting rotation...",
        current_size, max_size_mb
    )

    files = [f for f in folder.rglob("*") if f.is_file()]
    files.sort(key=lambda f: f.stat().st_mtime)

    for file_path in files:
        if file_path in protected:
            continue

        try:
            logging.info("Deleting old screenshot (rotation): %s", file_path)
            file_path.unlink()
        except Exception as e:
            logging.error("Error deleting file %s: %s", file_path, e)

        current_size = get_folder_size_mb(folder)
        if current_size <= max_size_mb:
            logging.info("Rotation complete. Current folder size: %.2f MB", current_size)
            break


def take_screenshot(output_path: Path) -> None:
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct.grab(monitor)
            sct.shot(mon=1, output=str(output_path))
        logging.info("Screenshot saved: %s", output_path)
    except Exception as e:
        logging.error("Error taking screenshot: %s", e)


def get_day_folder_name_for_path(path: Path) -> str:
    name = path.stem  # screenshot_YYYYMMDD_HHMMSS
    parts = name.split("_")
    if len(parts) >= 2:
        date_str = parts[1]
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            pass

    dt = datetime.fromtimestamp(path.stat().st_mtime)
    return dt.strftime("%d-%m-%Y")


def upload_batch_to_server(
    server_url: str,
    upload_password: str,
    tor_proxy: Optional[str],
    username: str,
    pending_paths: List[Path]
) -> List[Path]:
    """
    Upload a batch of screenshots to the onion server.
    Returns list of Paths successfully uploaded (and deleted locally).
    """
    if not pending_paths or not server_url or not upload_password:
        return []

    successfully_uploaded: List[Path] = []

    proxies = None
    if tor_proxy:
        proxies = {
            "http": tor_proxy,
            "https": tor_proxy,
        }

    upload_url = server_url.rstrip("/") + "/api/upload"

    for path in pending_paths:
        try:
            if not path.exists():
                logging.warning("File %s no longer exists locally, skipping.", path)
                successfully_uploaded.append(path)
                continue

            day_folder = get_day_folder_name_for_path(path)
            logging.info("Uploading %s (day=%s) for user %s...", path, day_folder, username)

            with path.open("rb") as f:
                files = {
                    "file": (path.name, f, "image/png"),
                }
                data = {
                    "username": username,
                    "day": day_folder,
                }
                headers = {
                    "X-Upload-Password": upload_password,
                }

                resp = requests.post(
                    upload_url,
                    data=data,
                    files=files,
                    headers=headers,
                    proxies=proxies,
                    timeout=60,
                )

            if resp.status_code == 200:
                logging.info("Uploaded %s successfully, deleting local copy.", path)
                path.unlink()
                successfully_uploaded.append(path)
            else:
                logging.error(
                    "Server returned status %s for %s: %s",
                    resp.status_code, path, resp.text
                )

        except Exception as e:
            logging.error("Error uploading %s: %s", path, e)

    return successfully_uploaded


def main():
    config = load_or_create_config()

    setup_logging(config.get("log_file", "screen_guard.log"))
    logging.info(
        "ScreenGuard (Tor) started. This program only logs YOUR OWN screen on YOUR machine."
    )

    interval_seconds = int(config.get("interval_seconds", 10))
    screenshot_folder = config.get("screenshot_folder")
    if not screenshot_folder:
        screenshot_folder = str(Path.home() / "Pictures" / "Security")

    folder_path = ensure_folder(screenshot_folder)
    max_size_mb = float(config.get("max_folder_size_mb", 500))
    upload_batch_size = int(config.get("upload_batch_size", 10))

    server_url = config.get("server_url", "").strip()
    upload_password = config.get("upload_password", "").strip()
    tor_proxy = config.get("tor_socks_proxy", "").strip()

    username = getpass.getuser()

    logging.info("Using screenshot folder: %s", folder_path)
    logging.info("Interval: %d seconds", interval_seconds)
    logging.info("Local folder size limit: %.2f MB", max_size_mb)
    logging.info("Server URL: %s", server_url)
    logging.info("Tor proxy: %s", tor_proxy)
    logging.info("Upload batch size: %d", upload_batch_size)
    logging.info("Windows username (sent as 'username' to server): %s", username)

    # On startup, treat all existing files as pending (for offline periods)
    pending_screenshots: List[Path] = sorted(
        [p for p in folder_path.rglob("*.png") if p.is_file()],
        key=lambda p: p.stat().st_mtime
    )

    try:
        while True:
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            day_folder_name = now.strftime("%d-%m-%Y")

            day_folder_path = ensure_folder(folder_path / day_folder_name)
            filename = f"screenshot_{timestamp}.png"
            screenshot_path = day_folder_path / filename

            take_screenshot(screenshot_path)

            pending_screenshots.append(screenshot_path)

            rotate_screenshots(
                folder_path,
                max_size_mb,
                protected=set(pending_screenshots)
            )

            if len(pending_screenshots) >= upload_batch_size and server_url and upload_password:
                uploaded = upload_batch_to_server(
                    server_url,
                    upload_password,
                    tor_proxy,
                    username,
                    pending_screenshots
                )
                pending_screenshots = [p for p in pending_screenshots if p not in uploaded]

            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        logging.info("Interrupted by user. Attempting final upload...")

        if server_url and upload_password and pending_screenshots:
            uploaded = upload_batch_to_server(
                server_url,
                upload_password,
                tor_proxy,
                username,
                pending_screenshots
            )
            pending_screenshots = [p for p in pending_screenshots if p not in uploaded]

        logging.info("Exiting cleanly.")
    except Exception as e:
        logging.exception("Unexpected error: %s", e)


if __name__ == "__main__":
    main()

