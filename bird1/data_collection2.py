# ENME489Y: Remote Sensing
# import the necessary packages
import numpy as np
import time
import cv2
import os
from picamera2 import Picamera2

# Initialize and configure the Pi Camera 2 once before the loop
picam2 = Picamera2()
config = picam2.create_still_configuration(main={"size": (1280, 720)})
picam2.configure(config)

# Allow camera to warm up once
picam2.start()
time.sleep(2)

# Set controls after start, then wait for them to take effect
picam2.set_controls({"AeEnable": False, "ExposureTime": 6000000, "AnalogueGain": 1.0, "Contrast": 1.0})
time.sleep(2)

# Check actual exposure time being used
metadata = picam2.capture_metadata()
print("Actual exposure time:", metadata["ExposureTime"])

while True:
    # Enter IMU angle from user
    d = input("Please enter IMU angle (or 'q' to quit): ")

    if d.lower() == 'q':
        print("Exiting. All done!")
        break

    print("Confirming the IMU angle you entered is: " + d)

    # Capture directly into a numpy array
    image = picam2.capture_array()

    # picamera2 returns RGB; convert to BGR for OpenCV
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    image = cv2.flip(image, -1)

    # plot crosshairs for alignment
    cv2.line(image, (640, 0),   (640, 720),  (0, 150, 150), 1)
    cv2.line(image, (600, 360), (1280, 360), (0, 150, 150), 1)

    # display IMU angle, for reference
    font = cv2.FONT_HERSHEY_COMPLEX_SMALL
    red = (0, 0, 255)
    cv2.putText(image, d, (800, 200), font, 10, red, 10)

    # write image to file
    d = int(d)
    filename = "%d.jpg" % d
    cv2.imwrite(filename, image)

    print(f"Image saved for angle {d}. Ready for next capture.")

# Stop the camera cleanly after the loop exits
picam2.stop()
