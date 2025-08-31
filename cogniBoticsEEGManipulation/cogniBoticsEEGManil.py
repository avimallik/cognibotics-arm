# Author: Arunav Mallik Avi
# IDE: VS Code or PyCharm
# pip install pyserial
import serial
import time

MINDWAVE_PORT = "COM7"    # Neurosky MindWave BT serial port
MINDWAVE_BAUD = 57600
ARDUINO_PORT  = "COM5"    # Arduino USB serial -- I used Arduino Mega 2560 V3
ARDUINO_BAUD  = 115200


# Very light ThinkGear parser for attention, meditation, blink, poorSignal
def read_thinkgear_values(ser):
    ser.timeout = 0.2
    data = ser.read(512)
    att = med = blink = None
    poor = 200  # default bad

    # Extremely simple scan by keywords (works with text-like proxies or Connector).
    # If you get raw binary packets, consider using an existing ThinkGear parser.
    text = data.decode(errors='ignore')
    
    # Examples of lines you might see from ThinkGear Connector:
    # "attention: 65", "meditation: 40", "blinkStrength: 60", "poorSignalLevel: 0"
    for line in text.splitlines():
        ls = line.strip().lower()
        if "attention" in ls:
            try: att = int(''.join(ch for ch in ls if ch.isdigit()))
            except: pass
        if "meditation" in ls:
            try: med = int(''.join(ch for ch in ls if ch.isdigit()))
            except: pass
        if "blink" in ls:
            try: blink = int(''.join(ch for ch in ls if ch.isdigit()))
            except: pass
        if "poorsignal" in ls or "poor signal" in ls or "poorsignallevel" in ls:
            try: poor = int(''.join(ch for ch in ls if ch.isdigit()))
            except: pass

    return {
        "attention": att,
        "meditation": med,
        "blink": blink,
        "poorSignal": poor
    }

def send_arduino(ser_arduino, cmd):
    ser_arduino.write((cmd + "\n").encode())
    # read optional feedback
    # print(ser_arduino.readline().decode(errors='ignore').strip())

def main():
    print("Connecting...")
    ser_mw = serial.Serial(MINDWAVE_PORT, MINDWAVE_BAUD)
    ser_ard = serial.Serial(ARDUINO_PORT,  ARDUINO_BAUD)
    time.sleep(2.0)  # let Arduino reset
    send_arduino(ser_ard, "HOME")

    grip_open = True   # track gripper state
    last_move = time.time()

    while True:
        v = read_thinkgear_values(ser_mw)
        if v["poorSignal"] is not None and v["poorSignal"] > 50:
            # signal bad → do nothing
            continue

        # Blink to toggle gripper
        if v["blink"] is not None and v["blink"] > 60:
            if grip_open:
                # CLOSE gripper (joint5 = index 5, step +10)
                send_arduino(ser_ard, "S 5 10")
            else:
                # OPEN gripper
                send_arduino(ser_ard, "S 5 -10")
            grip_open = not grip_open
            time.sleep(0.4)  # debounce

        # Periodic movement when attention/meditation high
        now = time.time()
        if now - last_move > 0.25:
            if v["attention"] is not None and v["attention"] > 70:
                # Rotate base left/right alternately (joint0)
                send_arduino(ser_ard, "S 0 5")
            if v["meditation"] is not None and v["meditation"] > 70:
                # Lift shoulder a bit (joint1)
                send_arduino(ser_ard, "S 1 3")
            last_move = now

        # Slow down loop a bit
        time.sleep(0.05)

if __name__ == "__main__":
    main()
