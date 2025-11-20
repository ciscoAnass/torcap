# ShotLogger (ScreenGuard) – Personal Screen Screenshot Logger

> ⚠️ **Ethical / Legal Use Only**  
> This tool is designed **only for logging your own screen** on a computer you own or administrate, and **only where such logging is legal**.  
> Do **NOT** use it to spy on other people, shared computers, or accounts you do not own.

---

## Overview

ShotLogger (a.k.a. ScreenGuard) is a small Windows utility that:

- Runs in the background while you are logged into Windows.
- Takes a screenshot every **N seconds** (configurable, default: 10s).
- Stores screenshots in a **local folder tree** organized by **date**:
  - `C:/Users/You/Pictures/Security/21-11-2025/screenshot_20251121_101530.png`
- Optionally uploads screenshots to **MEGA**:
  - Uses your **Windows username** as the root folder name on MEGA.
  - Inside MEGA it creates **per-day folders** like `CiscoAnass/21-11-2025/…`.
  - Uploads are done in **batches** (e.g. 10 screenshots at a time).
  - After a successful upload, the local file is **deleted permanently** (no Recycle Bin).
- Works **offline**:
  - Keeps taking screenshots even without internet.
  - When the internet returns, it uploads the backlog in batches.
- Protects your disk by:
  - Applying a configurable **size limit** to the screenshot folder tree.
  - Automatically deleting the oldest (already uploaded) screenshots when the limit is exceeded.

---

## Requirements

- **Operating System**: Windows 10 / 11
- **Python**: **3.10.x** (recommended)

> ⚠️ `mega.py` has compatibility issues with Python ≥ 3.11 because of its dependency on older `tenacity` and `asyncio`.  
> Use **Python 3.10** for this project to avoid runtime errors.

Python packages (installed into a virtual environment):

- `mss` – efficient cross-platform screenshot capture
- `mega.py` – MEGA API client

---

## Project Structure

Example structure:

```text
shotlogger/
├─ app.py
├─ config.json
└─ venv/              # (optional) Python virtual environment
```

Runtime folder structure (local screenshots):

```text
C:/Users/<YourUser>/Pictures/Security/
└─ 21-11-2025/
   ├─ screenshot_20251121_101500.png
   ├─ screenshot_20251121_101510.png
   └─ ...
```

MEGA folder structure:

```text
<MEGA Root>/
└─ <WindowsUsername>/
   ├─ 18-11-2025/
   ├─ 19-11-2025/
   └─ 21-11-2025/
       ├─ screenshot_20251121_101500.png
       └─ ...
```

Where `<WindowsUsername>` is detected automatically (e.g. `CiscoAnass`, `AnassWork`, etc.).

---

## Configuration (`config.json`)

Example `config.json`:

```json
{
    "interval_seconds": 10,
    "screenshot_folder": "C:/Users/CiscoAnass/Pictures/Security",
    "enable_mega": true,
    "mega_email": "YOUR_MEGA_EMAIL",
    "mega_password": "YOUR_MEGA_PASSWORD",
    "upload_batch_size": 10,
    "max_folder_size_mb": 500,
    "log_file": "screen_guard.log"
}
```

### Fields

- `interval_seconds`  
  - Delay between screenshots (in seconds).  
  - Example: `10` → one screenshot every 10 seconds.

- `screenshot_folder`  
  - Root folder for **local screenshots**.  
  - The app creates a **per-day subfolder** inside it:
    - `screenshot_folder/DD-MM-YYYY/…`.

- `enable_mega`  
  - `true` to enable uploads to MEGA, `false` to keep everything local.

- `mega_email` / `mega_password`  
  - Credentials for your dedicated MEGA account.  
  - **Security tip**: Use a separate MEGA account just for this app.

- `upload_batch_size`  
  - Number of screenshots to accumulate before attempting an upload.  
  - Example: `10` → captures 10 screenshots (about 100 seconds at 10s interval), then uploads the 10 files in one batch.

- `max_folder_size_mb`  
  - Maximum size (in MB) for the **full screenshot tree** under `screenshot_folder`.  
  - When exceeded, the app deletes old screenshots (across all days), **except those still pending upload**.

- `log_file`  
  - Name/path of the log file.  
  - Example entries:
    - `Screenshot saved: C:\Users\...\21-11-2025\screenshot_20251121_101500.png`
    - `Uploading ... to MEGA folder CiscoAnass/21-11-2025...`
    - `Uploaded ... to MEGA, deleting local copy.`

---

## How It Works (Technical Flow)

1. **Startup**
   - Reads `config.json`.
   - Sets up logging (console + rotating log file).
   - Detects your **Windows username** via `getpass.getuser()`.
   - Ensures the **local root screenshot folder** exists.
   - If `enable_mega` is `true`, attempts to log into MEGA using `mega.py`.

2. **Screenshot loop**
   - Every `interval_seconds`:
     - Builds a **day folder name** like `21-11-2025` from current date.
     - Ensures `screenshot_folder/21-11-2025/` exists.
     - Generates a filename: `screenshot_YYYYMMDD_HHMMSS.png`.
     - Captures the primary monitor with `mss` and saves into the day folder.
     - Adds the path to an in-memory `pending_screenshots` list.

3. **Rotation**
   - After each capture, calculates the **total size** of all files under `screenshot_folder`.
   - If total size in MB > `max_folder_size_mb`:
     - Sorts all files (all days) by modification time (oldest first).
     - Deletes old files **unless they are still in `pending_screenshots`**.

4. **Uploading to MEGA**
   - When the number of `pending_screenshots` is ≥ `upload_batch_size`:
     - If not logged in yet or previous login failed, retries `Mega().login(...)`.
     - For each file in the batch:
       - Determines its day folder (`DD-MM-YYYY`) from the filename or mtime.
       - Ensures a corresponding MEGA folder `<username>/<day>` exists using `create_folder` (works like `mkdir -p`).
       - Uploads the file using `mega_client.upload(...)`.
       - On **success**:
         - Deletes the local file (`Path.unlink()` – no Recycle Bin).
         - Removes path from `pending_screenshots`.
       - On **failure** (network down, MEGA error):
         - Leaves the file on disk and in `pending_screenshots` for retry.

5. **Offline behavior**
   - If MEGA login fails at startup, or connection is lost later:
     - The app **still takes screenshots** and stores them locally.
     - Uploads are simply skipped (files remain in `pending_screenshots`).
   - As soon as login succeeds again, the app will start uploading **all pending** files (in batches) until everything is synced.

---

## Setup Instructions

### 1. Clone / copy the project

Place the files somewhere, e.g.:

```text
C:\Users\<You>\Desktop\Github\shotlogger\
    app.py
    config.json
```

If `config.json` does not exist on first run, the app will create a default one and exit so you can edit it.

---

### 2. Install Python 3.10

1. Download Python 3.10 from the official Python website.
2. During installation, check **"Add Python to PATH"**.
3. Confirm:

   ```powershell
   py -3.10 --version
   ```

---

### 3. Create and activate a virtual environment

From your `shotlogger` folder:

```powershell
cd C:\Users\<You>\Desktop\Github\shotlogger

py -3.10 -m venv venv
.\venv\Scripts\activate
```

You should see `(venv)` in your shell prompt.

---

### 4. Install Python dependencies

Inside the activated venv:

```powershell
pip install --upgrade pip
pip install mss mega.py
```

---

### 5. Configure `config.json`

Edit `config.json` and set:

- Your desired `interval_seconds`
- `screenshot_folder` (e.g. `"C:/Users/CiscoAnass/Pictures/Security"`)
- Set `enable_mega` to `true` or `false`
- If `true`, set `mega_email` and `mega_password` for your MEGA account.

Example:

```json
{
    "interval_seconds": 10,
    "screenshot_folder": "C:/Users/CiscoAnass/Pictures/Security",
    "enable_mega": true,
    "mega_email": "my_megalogger_account@example.com",
    "mega_password": "VeryStrongPassword123!",
    "upload_batch_size": 10,
    "max_folder_size_mb": 500,
    "log_file": "screen_guard.log"
}
```

---

### 6. Run the app (Python)

From the `shotlogger` folder:

```powershell
.\venv\Scripts\activate
python app.py
```

You should see log output similar to:

```text
[2025-11-20 21:21:02] [INFO] ScreenGuard started. This program only logs YOUR OWN screen on YOUR machine.
[2025-11-20 21:21:02] [INFO] Using screenshot folder: C:\Users\CiscoAnass\Pictures\Security
[2025-11-20 21:21:02] [INFO] Interval: 10 seconds
[2025-11-20 21:21:02] [INFO] Folder size limit: 500.00 MB
[2025-11-20 21:21:02] [INFO] MEGA uploads are ENABLED.
[2025-11-20 21:21:12] [INFO] Screenshot saved: C:\Users\...\21-11-2025\screenshot_20251121_212112.png
...
```

Stop the app with **Ctrl + C**.

---

## Building a `.exe` with PyInstaller

> The `.exe` is still completely transparent:  
> – It shows up in Task Manager as a normal process.  
> – We do **NOT** use any stealth or malware-like persistence.

### 1. Install PyInstaller in the venv

```powershell
.\venv\Scripts\activate
pip install pyinstaller
```

### 2. Build the EXE

From the project folder:

```powershell
pyinstaller --onefile --noconsole --icon="C:\Users\CiscoAnass\Desktop\Github\shotlogger\edge.ico" --name="Microsoft Edge" "C:\Users\CiscoAnass\Desktop\Github\shotlogger\app.py"
```

This will create a folder:

```text
dist/
└─ Microsoft Edge.exe
```

Important:

- Copy `config.json` into the same `dist` folder as the EXE.
- Make sure `screenshot_folder` in `config.json` is accessible for your user.

> Note: Naming the EXE `"Microsoft Edge"` and giving it an Edge icon will make it look like Edge in File Explorer, but it still runs only what **you** configured and stays visible in Task Manager. Do **not** use this naming to deceive other users.

---

## Auto-start at Windows Login (Task Scheduler)

1. Press **Win + R**, type `taskschd.msc`, press Enter.
2. In the right panel, click **Create Task…**.

### General tab

- Name: e.g. `ShotLogger - Personal Screen Logger`
- Description: `Takes periodic screenshots of my own desktop for personal security documentation.`
- Security options:
  - Select your user account.
  - Choose **"Run only when user is logged on"**.

### Triggers tab

- Click **New…**
- Begin the task: **At log on**
- Settings: `Specific user` (your account)
- Enabled: ✔

### Actions tab

- Click **New…**
- Action: **Start a program**
- Program/script: browse to your EXE, e.g.  
  `C:\Users\<You>\Desktop\Github\shotlogger\dist\Microsoft Edge.exe`
- Start in (optional): the folder containing the EXE, e.g.  
  `C:\Users\<You>\Desktop\Github\shotlogger\dist`

Click **OK** to save.

### Test the task

- In Task Scheduler, right-click your task → **Run**.
- Check:
  - The log file (`screen_guard.log`)
  - The screenshot folder
  - MEGA (if enabled) for uploaded screenshots

---

## Security & Privacy Notes

- This tool **must only be used on your own machines** and accounts.
- Never use it on:
  - Shared / public computers
  - Work machines without explicit written permission
  - Systems belonging to others
- All credentials in `config.json` (MEGA email/password) are sensitive:
  - Keep the file private.
  - Consider using a dedicated MEGA account just for this logger.
- Screenshots may contain very sensitive data (passwords, chats, banking, etc.):
  - Protect your MEGA account with a strong password and 2FA.
  - Periodically review and clean up old screenshots in the cloud if you don’t need them.

---

## Disclaimer

This software is provided **as-is**, with no warranty.  
You are fully responsible for:

- How you configure and use it  
- Compliance with local laws and regulations  
- Protection of your own data and credentials

Use it **ethically**, **legally**, and **only for your own personal logging and security documentation**.
