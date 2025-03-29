
#!/usr/bin/env python3
import os, sys, time, subprocess, threading, json, random, signal

CONFIG_PATH = "/etc/.hidden_service_conf.json"
CONFIG = {}
SUSPICION_LEVEL = 0
PROMPT_ACTIVE = False
WATCHDOG_RUNNING = True

try:
    import setproctitle
    setproctitle.setproctitle("dbus-daemon")
except:
    pass

def load_config():
    global CONFIG
    try:
        with open(CONFIG_PATH, "r") as f:
            CONFIG = json.load(f)
    except:
        sys.exit(0)

def log(msg):
    lf = CONFIG.get("log_file","/var/log/guardian_watcher.log")
    try:
        with open(lf,"a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except:
        pass

def meltdown(reason="unknown"):
    log(f"Meltdown triggered: {reason}")
    action = CONFIG.get("meltdown_action","poweroff")

    if action == "poweroff":
        try: subprocess.run(["sync"])
        except: pass
        try: subprocess.run(["systemctl","poweroff"])
        except: pass

    elif action == "reboot":
        try: subprocess.run(["sync"])
        except: pass
        try: subprocess.run(["systemctl","reboot"])
        except: pass

    elif action == "logout":
        try:
            uid = os.getuid()
            subprocess.run(["pkill","-KILL","-u",str(uid)])
        except:
            pass

    elif action == "lock":
        try:
            subprocess.run(["loginctl","lock-session"])
        except:
            pass

    elif action == "test":
        try:
            subprocess.run([
                "yad", "--title=Test Meltdown",
                "--text=✅ Test meltdown logic triggered successfully!",
                "--button=OK", "--center", "--width=400", "--height=200"
            ])
        except:
            pass

def suspicion_event(source):
    global SUSPICION_LEVEL
    SUSPICION_LEVEL += 1
    log(f"Suspicion +1 from {source}, total={SUSPICION_LEVEL}")
    check_suspicion()

def check_suspicion():
    global SUSPICION_LEVEL, PROMPT_ACTIVE
    threshold = CONFIG.get("suspicion_threshold",3)
    if SUSPICION_LEVEL >= threshold and not PROMPT_ACTIVE:
        PROMPT_ACTIVE = True
        prompt_for_master()

def prompt_for_master():
    global SUSPICION_LEVEL, PROMPT_ACTIVE
    mpw = CONFIG.get("master_password","")
    if not mpw:
        meltdown("No master password set, meltdown now.")
        return

    entered = ""
    try:
        result = subprocess.run(["yad","--entry","--timeout","30",
                                 "--title=Suspicion Alert","--text=Enter Master Password:"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        entered = result.stdout.decode().strip()
    except:
        import sys, select
        print("Suspicion threshold exceeded. Enter master password within 30s:")
        i,_,_ = select.select([sys.stdin],[],[],30)
        if i:
            entered = sys.stdin.readline().strip()

    if entered == mpw:
        log("Master password correct, suspicion reset.")
        SUSPICION_LEVEL = 0
        PROMPT_ACTIVE = False
    else:
        meltdown("Suspicion prompt failure")

def is_internet_up():
    try:
        subprocess.check_output(["ping","-c","1","1.1.1.1"], stderr=subprocess.DEVNULL)
        return True
    except:
        return False

def get_idle_seconds():
    try:
        out = subprocess.check_output(["xprintidle"]).decode().strip()
        return int(out)/1000.0
    except:
        return 0

class KeyWatcher:
    def __init__(self):
        self.g_times = []
        self.buffer = ""
        self.override_typed = False
        self.last_tty = None
        self.time_rollback_reference = time.time()

    def on_press(self, key):
        ch = ""
        try:
            ch = key.char
        except:
            pass
        now = time.time()

        sys_key = CONFIG.get("secret_system_key","")
        if ch:
            self.buffer += ch
            if sys_key and sys_key in self.buffer:
                self.override_typed = True
                log("Override typed. Net meltdown canceled once.")
                self.buffer = ""

        if CONFIG.get("enable_keyboard_panics"):
            if ch and ch.lower() == 'g':
                # check the time delta
                if not self.g_times or (now - self.g_times[-1]) <= CONFIG.get("g_press_max_time",10):
                    self.g_times.append(now)
                else:
                    self.g_times = [now]
                # meltdown if 5 g's in time window
                if len(self.g_times) == 5 and (self.g_times[-1] - self.g_times[0]) <= CONFIG.get("g_press_max_time",10):
                    meltdown("5x g pressed")
            else:
                self.g_times = []

    def check_tty(self):
        if CONFIG.get("enable_keyboard_panics"):
            try:
                curr = subprocess.check_output(["fgconsole"]).decode().strip()
                if self.last_tty and curr != self.last_tty:
                    meltdown("TTY switched")
                self.last_tty = curr
            except:
                pass

    def check_time_rollback(self):
        if CONFIG.get("enable_time_rollback"):
            now = time.time()
            if now < self.time_rollback_reference - 300:
                meltdown("Time rolled back")
            self.time_rollback_reference = now

class IdleWatcher:
    def run(self):
        if CONFIG.get("enable_idle_check"):
            if get_idle_seconds() >= CONFIG.get("idle_timeout",600):
                meltdown("Idle limit")

class InternetWatcher:
    def __init__(self, kwatcher):
        self.kwatcher = kwatcher
        self.internet_down_start = None

    def run(self):
        if CONFIG.get("enable_internet_check"):
            if is_internet_up():
                self.internet_down_start = None
                self.kwatcher.override_typed = False
            else:
                if self.internet_down_start is None:
                    self.internet_down_start = time.time()
                    log("Internet disconnected")
                else:
                    if (time.time() - self.internet_down_start) >= CONFIG.get("internet_timeout",300) and not self.kwatcher.override_typed:
                        meltdown("Net down too long")

class USBWatcher:
    def start(self):
        if not CONFIG.get("enable_usb_watchdog"):
            return
        try:
            import pyudev
        except:
            log("pyudev not installed; skipping USB watch.")
            return
        def loop():
            log("USBWatcher started. Monitoring new block devices..")
            ctx = pyudev.Context()
            mon = pyudev.Monitor.from_netlink(ctx)
            mon.filter_by("block")
            for dev in iter(mon.poll, None):
                if dev.action == "add":
                    self.handle(dev)
        threading.Thread(target=loop, daemon=True).start()

    def handle(self, device):
        log(f"USB DEBUG => device={device}, type={device.device_type}, path={device.device_path}")
        if device.device_type != "disk":
            log("Skipping non-disk device.")
            return
        if "usb" not in device.device_path:
            log("Skipping device with no usb in path.")
            return

        suspicion_event("USB Insert")
        node = device.device_node
        log(f"USB {node} inserted -> powering off.")
        try:
            subprocess.run(["udisksctl","power-off","-b", node], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass

        secret_usb = CONFIG.get("secret_usb_key","")
        pw = ""
        if secret_usb:
            try:
                result = subprocess.run(["yad","--entry","--timeout", str(CONFIG.get("usb_timeout",30)),
                                         "--title=USB Auth","--text=Enter USB pass:"],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                pw = result.stdout.decode().strip()
            except:
                import sys, select
                print("USB inserted. Enter pass:")
                i,_,_ = select.select([sys.stdin],[],[], CONFIG.get("usb_timeout",30))
                if i:
                    pw = sys.stdin.readline().strip()

        if pw != secret_usb:
            meltdown("Bad USB pass")
        else:
            log(f"Correct pass for {node}, re-power + mount.")
            try:
                subprocess.run(["udisksctl","power-on","-b", node])
                subprocess.run(["udisksctl","mount","-b", node])
            except:
                meltdown("USB mount error")

class ForensicsWatcher:
    def run(self):
        if not CONFIG.get("enable_forensics_check"):
            return
        try:
            ps = subprocess.check_output(["ps","aux"]).decode()
            keywords = ["dd ","strings ","autopsy","foremost","bulk_extractor","guymager","wireshark","tcpdump","volatility","tsk_recover"]
            for kw in keywords:
                if kw in ps:
                    suspicion_event("ForensicsTool")
                    break
        except:
            pass

class BruteforceWatcher:
    def run(self):
        if not CONFIG.get("enable_bruteforce_check"):
            return
        try:
            fails = 0
            with open("/var/log/auth.log","r") as f:
                for line in f:
                    if "Failed password" in line:
                        fails += 1
            if fails > 10:
                suspicion_event("BruteForce")
        except:
            pass

class LocationWatcher:
    def run(self):
        if not CONFIG.get("enable_location_check"):
            return
        bssids = CONFIG.get("trusted_bssids",[])
        if not bssids:
            return
        cur = get_current_bssid()
        if cur and cur not in bssids:
            suspicion_event("UnknownBSSID")

def get_current_bssid():
    try:
        out = subprocess.check_output(["iw","dev"]).decode()
        for l in out.split("\n"):
            if "Connected to" in l:
                return l.split("Connected to")[-1].strip()
    except:
        pass
    return None

def anti_kill_watchdog():
    while WATCHDOG_RUNNING:
        time.sleep(5)

def main():
    if "--run-hidden" not in sys.argv:
        print("This file is meant to be run with --run-hidden.")
        sys.exit(0)

    load_config()
    log("Hidden meltdown watchers started (base64).")

    threading.Thread(target=anti_kill_watchdog, daemon=True).start()

    kw = KeyWatcher()
    usb = USBWatcher()
    usb.start()

    watchers = [
        IdleWatcher(),
        InternetWatcher(kw),
        ForensicsWatcher(),
        BruteforceWatcher(),
        LocationWatcher()
    ]

    try:
        from pynput import keyboard
        def on_press(key):
            kw.on_press(key)
        threading.Thread(target=lambda: keyboard.Listener(on_press=on_press).run(), daemon=True).start()
    except:
        log("pynput not installed, skipping keyboard meltdown watchers.")

    while True:
        for w in watchers:
            w.run()
        kw.check_tty()
        kw.check_time_rollback()
        time.sleep(5)
