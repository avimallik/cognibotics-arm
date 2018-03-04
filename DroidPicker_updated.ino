#include <SoftwareSerial.h>
#include <Servo.h>
SoftwareSerial BT(10, 11); //TX, RX respetively
String readdata;
int servopos;
//int servopos2;

Servo myservo;
Servo myservo2;

void setup() {
 BT.begin(9600);
 Serial.begin(9600);
  pinMode(3, OUTPUT);
  pinMode(4, OUTPUT);
  pinMode(5, OUTPUT);
  pinMode(6, OUTPUT);
  myservo.attach(9);
  //myservo2.attach(8);
}
//-----------------------------------------------------------------------// 
void loop() {
  while (BT.available()){  //Check if there is an available byte to read
  delay(10); //Delay added to make thing stable
  char c = BT.read(); //Conduct a serial read
  if(c == '#'){break;}
  readdata += c; //build the string- "forward", "reverse", "left" and "right"
  } 
  
  if (readdata.length() > 0) {
    Serial.println(readdata);

  if(readdata == "up")
  {
    digitalWrite(3, HIGH);
    digitalWrite (4, HIGH);
    digitalWrite(5,LOW);
    digitalWrite(6,LOW);
    delay(100);
  }

  else if(readdata == "down")
  {
    digitalWrite(3, LOW);
    digitalWrite(4, LOW);
    digitalWrite(5, HIGH);
    digitalWrite(6,HIGH);
    delay(100);
  }

  else if (readdata == "right")
  {
    digitalWrite (3,HIGH);
    digitalWrite (4,LOW);
    digitalWrite (5,LOW);
    digitalWrite (6,LOW);
    delay (100);
   
  }

 else if ( readdata == "left")
 {
   digitalWrite (3, LOW);
   digitalWrite (4, HIGH);
   digitalWrite (5, LOW);
   digitalWrite (6, LOW);
   delay (100);
 }

 else if (readdata == "stop")
 {
   digitalWrite (3, LOW);
   digitalWrite (4, LOW);
   digitalWrite (5, LOW);
   digitalWrite (6, LOW);
   delay (100);
 }

  
 readdata="";
  }

 
if(BT.available()>0)
  {
    servopos = BT.read(); // save the received number to servopos
    Serial.println(servopos); // serial print servopos current number received from bluetooth
    myservo.write(servopos); // roate the servo the angle received from the android app
    delay(10);
  }


/*
  else if(BT.available()>0)
  {
    servopos2 = BT.read(); // save the received number to servopos
    Serial.println(servopos2); // serial print servopos current number received from bluetooth
    myservo2.write(servopos2); // roate the servo the angle received from the android app
    delay(10);
  }
  */
  
 }



 //Reset the variable
