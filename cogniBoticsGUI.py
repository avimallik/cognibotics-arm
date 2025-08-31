# Author: Arunav Mallik Avi, Mustakim Billah
import threading
import queue
import time
import re
import sys

import serial
from serial.tools import list_ports

import tkinter as tk
from tkinter import ttk, messagebox

# ====== USER SETTINGS (change if needed) ======
MINDWAVE_BAUD = 57600
ARDUINO_BAUD  = 115200

ATTN_THRESH = 70     # attention threshold to move base
MED_THRESH  = 70     # meditation threshold to lift shoulder
BLINK_THRESH = 60    # blink threshold to toggle gripper
STEP_BASE = 5        # degrees each nudge for base (joint 0)
STEP_SHOULDER = 3    # degrees each nudge for shoulder (joint 1)
STEP_GRIPPER = 10    # degrees each toggle for gripper (joint 5)
MOVE_PERIOD = 0.25   # seconds between periodic moves

# =================================================

DIGITS_RE = re.compile(r'(\d+)')

def extract_int(line):
    m = DIGITS_RE.search(line)
    return int(m.group(1)) if m else None

class EEGReader(threading.Thread):
    """
    Reads MindWave (text-like ThinkGear output) from a serial port in a thread.
    Emits dicts: {"attention": int|None, "meditation": int|None,
                  "blink": int|None, "poorSignal": int|None}
    """
    def __init__(self, port, baud, out_q, stop_evt):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.out_q = out_q
        self.stop_evt = stop_evt
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.2)
            # Push a status message
            self.out_q.put({"_status": f"Connected MindWave on {self.port}"})
        except Exception as e:
            self.out_q.put({"_error": f"MindWave open failed: {e}"})
            return

        residual = ""
        while not self.stop_evt.is_set():
            try:
                data = self.ser.read(512)
            except Exception as e:
                self.out_q.put({"_error": f"MindWave read error: {e}"})
                break

            if not data:
                continue

            try:
                text = residual + data.decode(errors='ignore')
            except Exception:
                continue

            lines = text.splitlines(True)  # keepends
            residual = ""
            if lines and not lines[-1].endswith(('\r', '\n')):
                residual = lines.pop()

            att = med = blink = poor = None
            emitted = False

            for raw in lines:
                ls = raw.strip().lower()
                if "attention" in ls:
                    att = extract_int(ls)
                    self.out_q.put({"attention": att}); emitted = True
                elif "meditation" in ls:
                    med = extract_int(ls)
                    self.out_q.put({"meditation": med}); emitted = True
                elif "blink" in ls:
                    blink = extract_int(ls)
                    self.out_q.put({"blink": blink}); emitted = True
                elif "poorsignal" in ls or "poor signal" in ls or "poorsignallevel" in ls:
                    poor = extract_int(ls)
                    self.out_q.put({"poorSignal": poor}); emitted = True

            # emit heartbeat if nothing parsed (keeps UI alive)
            if not emitted:
                self.out_q.put({"_tick": True})

        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.out_q.put({"_status": "MindWave disconnected"})


class ArduinoCtrl:
    """Simple wrapper to send lines to Arduino and optionally read replies."""
    def __init__(self):
        self.ser = None

    def open(self, port, baud):
        if self.ser and self.ser.is_open:
            self.close()
        self.ser = serial.Serial(port, baud, timeout=0.2)
        time.sleep(2.0)  # let Arduino reset

    def close(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.ser = None

    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def send(self, line):
        if not self.is_open(): return
        self.ser.write((line.strip() + "\n").encode())

    def readline(self):
        if not self.is_open(): return ""
        try:
            return self.ser.readline().decode(errors='ignore').strip()
        except Exception:
            return ""


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NeuroSky → 6-DOF Arm (Arduino) — Simple GUI")
        self.geometry("720x520")

        # Queues & threads
        self.eeg_q = queue.Queue()
        self.eeg_stop_evt = threading.Event()
        self.eeg_thread = None

        # Arduino
        self.arduino = ArduinoCtrl()

        # State
        self.attention = 0
        self.meditation = 0
        self.poor = 200
        self.last_move_t = 0
        self.grip_open = True
        self.streaming = False

        # UI
        self.create_widgets()
        self.refresh_ports()
        self.poll_queues()

    # ---------- UI ----------
    def create_widgets(self):
        pad = {'padx': 8, 'pady': 6}

        top = ttk.Frame(self)
        top.pack(fill='x', **pad)

        ttk.Label(top, text="MindWave Port:").grid(row=0, column=0, sticky='w')
        self.cb_mw = ttk.Combobox(top, width=28, state="readonly")
        self.cb_mw.grid(row=0, column=1, sticky='w', padx=(0,10))

        ttk.Label(top, text="Arduino Port:").grid(row=0, column=2, sticky='w')
        self.cb_ard = ttk.Combobox(top, width=28, state="readonly")
        self.cb_ard.grid(row=0, column=3, sticky='w')

        self.btn_refresh = ttk.Button(top, text="↻ Refresh", command=self.refresh_ports)
        self.btn_refresh.grid(row=0, column=4, padx=(10,0))

        mid = ttk.Labelframe(self, text="EEG Levels")
        mid.pack(fill='x', **pad)

        # Attention
        self.pb_att = ttk.Progressbar(mid, maximum=100)
        self.pb_att.grid(row=0, column=1, sticky='ew', **pad)
        ttk.Label(mid, text="Attention").grid(row=0, column=0, sticky='w', padx=(10,0))
        self.lbl_att = ttk.Label(mid, text="0")
        self.lbl_att.grid(row=0, column=2, sticky='e', padx=(0,10))

        # Meditation
        self.pb_med = ttk.Progressbar(mid, maximum=100)
        self.pb_med.grid(row=1, column=1, sticky='ew', **pad)
        ttk.Label(mid, text="Meditation").grid(row=1, column=0, sticky='w', padx=(10,0))
        self.lbl_med = ttk.Label(mid, text="0")
        self.lbl_med.grid(row=1, column=2, sticky='e', padx=(0,10))

        # Poor Signal (inverted bar: lower is better)
        self.pb_poor = ttk.Progressbar(mid, maximum=200)
        self.pb_poor.grid(row=2, column=1, sticky='ew', **pad)
        ttk.Label(mid, text="Poor Signal").grid(row=2, column=0, sticky='w', padx=(10,0))
        self.lbl_poor = ttk.Label(mid, text="200")
        self.lbl_poor.grid(row=2, column=2, sticky='e', padx=(0,10))

        mid.columnconfigure(1, weight=1)

        # Controls
        ctrl = ttk.Labelframe(self, text="Control")
        ctrl.pack(fill='x', **pad)

        self.btn_start = ttk.Button(ctrl, text="Start", command=self.on_start)
        self.btn_start.grid(row=0, column=0, padx=8, pady=6)

        self.btn_stop = ttk.Button(ctrl, text="Stop", command=self.on_stop, state='disabled')
        self.btn_stop.grid(row=0, column=1, padx=8, pady=6)

        self.btn_home = ttk.Button(ctrl, text="E-STOP (HOME)", command=self.on_home)
        self.btn_home.grid(row=0, column=2, padx=8, pady=6)

        self.lbl_status = ttk.Label(ctrl, text="Idle", anchor='w')
        self.lbl_status.grid(row=0, column=3, sticky='ew', padx=8)
        ctrl.columnconfigure(3, weight=1)

        # Command log
        logf = ttk.Labelframe(self, text="Command Log → Arduino")
        logf.pack(fill='both', expand=True, **pad)
        self.txt_log = tk.Text(logf, height=12, wrap='none')
        self.txt_log.pack(fill='both', expand=True, padx=6, pady=6)
        self.txt_log.config(state='disabled')

    def refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        self.cb_mw['values'] = ports
        self.cb_ard['values'] = ports
        # Keep selection if still present
        if not self.cb_mw.get() and ports:
            self.cb_mw.set(ports[0])
        if not self.cb_ard.get() and ports:
            self.cb_ard.set(ports[-1] if len(ports) > 1 else ports[0])

    # ---------- Streaming control ----------
    def on_start(self):
        if self.streaming:
            return
        mw = self.cb_mw.get().strip()
        ard = self.cb_ard.get().strip()
        if not mw or not ard:
            messagebox.showerror("Ports", "Please select both MindWave and Arduino ports.")
            return

        # Open Arduino
        try:
            self.arduino.open(ard, ARDUINO_BAUD)
        except Exception as e:
            messagebox.showerror("Arduino", f"Failed to open Arduino: {e}")
            return

        # Start EEG thread
        self.eeg_stop_evt.clear()
        self.eeg_thread = EEGReader(mw, MINDWAVE_BAUD, self.eeg_q, self.eeg_stop_evt)
        self.eeg_thread.start()

        # Send HOME
        self.send_cmd("HOME")

        self.streaming = True
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        self.status("Streaming…")

    def on_stop(self):
        if not self.streaming:
            return
        self.eeg_stop_evt.set()
        if self.eeg_thread:
            self.eeg_thread.join(timeout=1.5)
        self.arduino.close()
        self.streaming = False
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        self.status("Stopped")

    def on_home(self):
        self.send_cmd("HOME")

    # ---------- Helpers ----------
    def status(self, msg):
        self.lbl_status.config(text=msg)

    def log(self, line):
        self.txt_log.config(state='normal')
        self.txt_log.insert('end', line + "\n")
        self.txt_log.see('end')
        self.txt_log.config(state='disabled')

    def send_cmd(self, line):
        if self.arduino.is_open():
            self.arduino.send(line)
            self.log(f"> {line}")

    def apply_mapping(self, vdict):
        # vdict contains parsed values; we maintain local state for thresholds & timing
        if 'poorSignal' in vdict and vdict['poorSignal'] is not None:
            self.poor = vdict['poorSignal']

        if self.poor is not None and self.poor > 50:
            # Freeze if poor signal
            return

        # Blink toggles gripper
        if 'blink' in vdict:
            blink = vdict['blink']
            if blink is not None and blink >= BLINK_THRESH:
                if self.grip_open:
                    self.send_cmd(f"S 5 {STEP_GRIPPER}")   # close
                else:
                    self.send_cmd(f"S 5 {-STEP_GRIPPER}")  # open
                self.grip_open = not self.grip_open

        now = time.time()
        if now - self.last_move_t >= MOVE_PERIOD:
            if 'attention' in vdict and vdict['attention'] is not None:
                self.attention = vdict['attention']
                if self.attention >= ATTN_THRESH:
                    self.send_cmd(f"S 0 {STEP_BASE}")  # base yaw

            if 'meditation' in vdict and vdict['meditation'] is not None:
                self.meditation = vdict['meditation']
                if self.meditation >= MED_THRESH:
                    self.send_cmd(f"S 1 {STEP_SHOULDER}")  # shoulder

            self.last_move_t = now

    # ---------- Periodic UI/queue polling ----------
    def poll_queues(self):
        try:
            while True:
                item = self.eeg_q.get_nowait()
                if "_error" in item:
                    self.status(item["_error"])
                    self.log(f"! {item['_error']}")
                elif "_status" in item:
                    self.status(item["_status"])
                    self.log(f"* {item['_status']}")
                else:
                    # Update values & mapping
                    if "attention" in item and item["attention"] is not None:
                        self.attention = item["attention"]
                    if "meditation" in item and item["meditation"] is not None:
                        self.meditation = item["meditation"]
                    if "poorSignal" in item and item["poorSignal"] is not None:
                        self.poor = item["poorSignal"]
                    # Apply mapping to Arduino
                    self.apply_mapping(item)
        except queue.Empty:
            pass

        # Update UI bars
        self.pb_att['value'] = self.attention if self.attention is not None else 0
        self.lbl_att.config(text=str(self.attention if self.attention is not None else 0))

        self.pb_med['value'] = self.meditation if self.meditation is not None else 0
        self.lbl_med.config(text=str(self.meditation if self.meditation is not None else 0))

        self.pb_poor['value'] = self.poor if self.poor is not None else 200
        self.lbl_poor.config(text=str(self.poor if self.poor is not None else 200))

        # Poll again
        self.after(50, self.poll_queues)

    def destroy(self):
        # Clean shutdown
        try:
            self.on_stop()
        except Exception:
            pass
        super().destroy()


if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
