// === Arduino IDE sketch: arm_controller.ino ===
#include <Servo.h>

Servo servos[6];
int servoPins[6] = {2, 3, 4, 5, 6, 7};  // D2..D7
int angles[6]    = {90, 90, 90, 90, 90, 90}; // start in mid

// Per-joint limits (tune for your arm so it won’t crash)
int minA[6] = {10,  10,  10,  10,  10,  10};
int maxA[6] = {170, 170, 170, 170, 170, 170};

void applyAngle(int j, int a) {
  if (j < 0 || j >= 6) return;
  a = constrain(a, minA[j], maxA[j]);
  angles[j] = a;
  servos[j].write(a);
}

void homePose() {
  int home[6] = {90, 90, 90, 90, 90, 90};
  for (int j=0; j<6; j++) applyAngle(j, home[j]);
}

void setup() {
  Serial.begin(115200);
  for (int j=0; j<6; j++) {
    servos[j].attach(servoPins[j]);
    servos[j].write(angles[j]);
  }
  homePose();
  Serial.println("READY");
}

void processLine(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line.equalsIgnoreCase("HOME")) {
    homePose();
    Serial.println("OK HOME");
    return;
  }

  char cmd = line.charAt(0);
  if (cmd == 'J' || cmd == 'j') {
    // J <idx> <angle>
    int idx, a;
    if (sscanf(line.c_str(), "J %d %d", &idx, &a) == 2) {
      applyAngle(idx, a);
      Serial.println("OK J");
    }
  } else if (cmd == 'S' || cmd == 's') {
    // S <idx> <delta>
    int idx, d;
    if (sscanf(line.c_str(), "S %d %d", &idx, &d) == 2) {
      int newA = angles[idx] + d;
      applyAngle(idx, newA);
      Serial.println("OK S");
    }
  } else {
    Serial.println("ERR");
  }
}

String buf;
void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      processLine(buf);
      buf = "";
    } else if (c != '\r') {
      buf += c;
    }
  }
}
