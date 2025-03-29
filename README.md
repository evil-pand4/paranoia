# Guardian Watcher – Advanced Security & Anti-Forensics -- WIP -- STILL IN DEVELOPMENT FOR NOW

Guardian Watcher is a Python-based security toolkit that passively monitors your Linux system for suspicious or unauthorized activity. If triggered, it performs a **configurable meltdown** response (e.g., power off, reboot, logout, or lock the screen).

---

## Key Features

1. **Idle-Time Shutdown**  
   - Automatically power off or lock your system if it remains idle for too long.

2. **Internet-Down Watch**  
   - If the system’s internet connection remains offline for a set time (and no override phrase is typed), meltdown occurs.

3. **USB Watchdog**  
   - Any newly inserted USB storage device requires a passphrase to power on and mount. Otherwise, meltdown.

4. **Keyboard Panic**  
   - Pressing `g` five times within a certain window triggers meltdown.  
   - Or if the user typed the override phrase, meltdown can be canceled once for internet-down events.

5. **Time Rollback & TTY Switch Checks**  
   - If the system clock is rolled back significantly, meltdown.  
   - Switching TTY (e.g. from GUI to console) can also trigger meltdown.

6. **Suspicion Threshold**  
   - Detects forensics tools (`dd`, `strings`, `autopsy`, etc.), repeated auth failures, or unknown Wi-Fi networks.  
   - Each event raises suspicion by +1. Once over a threshold, the user must type a “master password” within 30 seconds or meltdown occurs.

7. **Multiple Meltdown Options**  
   - `poweroff`, `reboot`, `logout`, or `lock`.

8. **Watchdog-of-the-Watchdog**  
   - A secondary thread tries to detect if the process is forcibly stopped. (Limited protection—SIGKILL is unstoppable, but at least there’s some minimal coverage.)

9. **Configuration Through `setup.py`**  
   - Choose features via flags (`--enable-usb-watchdog=true`, etc.).  
   - Provide passphrases and meltdown actions.  
   - Optionally install a disguised systemd service that auto-starts each reboot.

---

## Installation & Dependencies

- Python 3.  
- Required modules: `pynput`, `pyudev`, `setproctitle` (optional but recommended), plus typical system tools like `xprintidle`, `yad`, `udisksctl`, etc.
- Run `setup.py` with desired flags, e.g.:
  ```bash
  sudo python3 setup.py --enable-usb-watchdog=true \
                        --enable-forensics-check=true \
                        --enable-location-check=true \
                        --meltdown-action=logout \
                        --install-service
