#!/usr/bin/env python3
import os
import sys
import subprocess
import getpass
import json
import random
import string
import time
import base64

DEFAULT_SETTINGS = {
    "enable_idle_check": True,
    "enable_internet_check": True,
    "enable_usb_watchdog": False,
    "enable_keyboard_panics": False,
    "enable_time_rollback": False,
    "enable_location_check": False,
    "enable_bruteforce_check": False,
    "enable_forensics_check": False,

    "idle_timeout": 600,
    "internet_timeout": 300,
    "g_press_max_time": 10,
    "usb_timeout": 30,

    "trusted_bssids": [],

    "suspicion_threshold": 3,
    "master_password": "",

    "log_file": "/var/log/guardian_watcher.log",
    "meltdown_action": "poweroff",

    "secret_system_key": "",
    "secret_usb_key": ""
}

CONFIG_PATH = "/etc/.hidden_service_conf.json"
UNIT_NAME = "NetworkManager-plugins.service"
UNIT_FILE = f"/etc/systemd/system/{UNIT_NAME}"

HIDDEN_SCRIPT_DIR = "/dev/shm"
def random_name(k=8):
    return "".join(random.choices(string.ascii_letters + string.digits, k=k))

HIDDEN_SERVICE_FILE = f".{random_name()}.py"
HIDDEN_SERVICE_PATH = os.path.join(HIDDEN_SCRIPT_DIR, HIDDEN_SERVICE_FILE)

def remove_from_memory(vars_list):
    for v in vars_list:
        if v in globals():
            globals()[v] = None
        if v in locals():
            locals()[v] = None

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f)
        return True
    except Exception as e:
        print(f"save_config error: {e}")
        return False

def show_help():
    print("""
Usage: setup.py [options]
  --help
  ... (all your watchers flags) ...
  --install-service
  --debug
""")

def install_systemd():
    content = f"""[Unit]
Description=Network Manager Compatibility Plugins
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {HIDDEN_SERVICE_PATH} --run-hidden
Restart=always

[Install]
WantedBy=multi-user.target
"""
    try:
        with open(UNIT_FILE, "w") as f:
            f.write(content)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", UNIT_NAME], check=True)
        print(f"Service installed & enabled as {UNIT_NAME}.  (systemctl start {UNIT_NAME})")
    except Exception as e:
        print("Error installing service:", e)

def generate_hidden_service(cfg, meltdown_core_py):
    """
    meltdown_core_py: full text of meltdown_watchers.py
    We base64-encode meltdown_core_py, produce a tiny loader script in /dev/shm
    that writes meltdown_core.py to a file & runs it with --run-hidden.
    """
    b64_payload = base64.b64encode(meltdown_core_py.encode("utf-8")).decode("utf-8")

    loader_code = f'''#!/usr/bin/env python3
import base64, sys, os
if "--run-hidden" not in sys.argv:
    print("This ephemeral file must be run with --run-hidden.")
    sys.exit(0)

payload_b64 = "{b64_payload}"
decoded = base64.b64decode(payload_b64)

mw_path = "/dev/shm/.mw_code.py"
with open(mw_path, "wb") as fp:
    fp.write(decoded)

# Now run meltdown_watchers with --run-hidden
os.chmod(mw_path, 0o700)
os.execv("/usr/bin/python3", ["python3", mw_path, "--run-hidden"])
'''

    with open(HIDDEN_SERVICE_PATH, "w") as f:
        f.write(loader_code)
    subprocess.run(["chmod", "+x", HIDDEN_SERVICE_PATH])

    return HIDDEN_SERVICE_PATH

def main():
    # 1) Make sure meltdown_watchers.py exists
    if not os.path.exists("meltdown_watchers.py"):
        print("❌ meltdown_watchers.py not found in current directory.")
        sys.exit(1)
    with open("meltdown_watchers.py", "r") as f:
        meltdown_core_py = f.read()

    cfg = DEFAULT_SETTINGS.copy()
    install_flag = False
    debug_flag = False

    args = sys.argv[1:]
    if not args:
        pass

    for a in args:
        if a.startswith("--help"):
            show_help()
            return
        elif a.startswith("--debug"):
            debug_flag = True
        elif a.startswith("--enable-idle-check="):
            cfg["enable_idle_check"] = ("true" in a.split("=")[1].lower())
        # ... parse other watchers the same ...
        elif a.startswith("--meltdown-action="):
            val = a.split("=")[1].lower()
            if val in ("poweroff","reboot","logout","lock","test"):
                cfg["meltdown_action"] = val
        elif a.startswith("--install-service"):
            install_flag = True

    # figure out which passphrases we need
    need_override = cfg["enable_internet_check"]
    need_usb = cfg["enable_usb_watchdog"]
    suspicious_features = (
        cfg["enable_forensics_check"] or
        cfg["enable_bruteforce_check"] or
        cfg["enable_location_check"]
    )
    need_master = suspicious_features

    if need_override:
        print("Enter override phrase (secret_system_key) [net-down meltdown override]:")
        s1 = getpass.getpass("First: ")
        s2 = getpass.getpass("Confirm: ")
        if s1 != s2:
            print("Mismatch, aborting.")
            return
        cfg["secret_system_key"] = s1

    if need_usb:
        print("Enter USB passphrase (secret_usb_key):")
        s1 = getpass.getpass("First: ")
        s2 = getpass.getpass("Confirm: ")
        if s1 != s2:
            print("Mismatch, aborting.")
            return
        cfg["secret_usb_key"] = s1

    if need_master:
        print("Enter the master password (for suspicion threshold override):")
        s1 = getpass.getpass("First: ")
        s2 = getpass.getpass("Confirm: ")
        if s1 != s2:
            print("Mismatch, aborting.")
            return
        cfg["master_password"] = s1

    # save config
    ok = save_config(cfg)
    if not ok:
        print("Failed saving config. Exiting.")
        return

    remove_from_memory(["s1","s2"])

    # 2) generate ephemeral loader with meltdown_watchers code embedded as base64
    path = generate_hidden_service(cfg, meltdown_core_py)
    print(f"Hidden loader generated at: {path}")

    # 3) Optionally install systemd service
    if install_flag:
        install_systemd()

    # 4) If debug, start service & tail logs
    if debug_flag:
        print("\n== DEBUG MODE ==\nStarting service & tailing logs. Press Ctrl+C to stop.\n")
        subprocess.run(["systemctl", "start", UNIT_NAME])
        subprocess.run(["journalctl", "-u", UNIT_NAME, "-f", "--no-pager"])
    else:
        print("Setup complete. If installed, run:")
        print(f"  systemctl start {UNIT_NAME}")

if __name__ == "__main__":
    main()
