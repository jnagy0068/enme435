import numpy as np
import cv2
import time
import os
import smtplib
from smtplib import SMTP
from smtplib import SMTPException
import email
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# smartdoorbellenme435@gmail.com
# smartdoorbell12
# mfhs hrfy zsxj rbqi 

def select_points(img): # for initial mask point selection
    points = []
    for i in range(0, 4): # number of points needed to form shape
        bbox = cv2.selectROI(img, False)
        print(bbox)
        points.append([bbox[0], bbox[1]])
    print(points)

    return points

def mask_image(img):
    mask = np.zeros((img.shape[0], img.shape[1]), dtype="uint8")
    pts = np.array([[385, 16], [854, 20], [904, 655], [434, 673]], dtype=np.int32) # mask points
    cv2.fillConvexPoly(mask, pts, 255)
    # pts = np.array([[553, 707], [300, 600], [400, 590], [550, 650]], dtype=np.int32) # walkway coordinates
    # cv2.fillConvexPoly(mask, pts, 255)
    masked = cv2.bitwise_and(img, img, mask=mask)
    gray = cv2.resize(masked, (200, int(masked.shape[0] * 200 / masked.shape[1])))
    gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (11, 11), 0) # kernel size
    return masked, gray

# keep looping
counter = -1
# Mask calibration
# img = cv2.imread("calibration.jpg")
# select_points(img)

try:
    while True:
        if cv2.waitKey(1) == ord('q'):
            break

        counter = counter + 1
        print(" ")
        print("Times through loop since starting:", counter)
        print(" ")

        # take a 1st and 2nd image to compare
        os.system('libcamera-still --width 1280 --height 720 --vflip --hflip --timeout 1000 -o test1.jpg')
        time.sleep(2)
        os.system('libcamera-still --width 1280 --height 720 --vflip --hflip --timeout 1000 -o test2.jpg')
        
        print("Captured 1st & 2nd image for analysis...")

        # mask images
        test1 = cv2.imread("test1.jpg")
        time.sleep(3)
        test2 = cv2.imread("test2.jpg")
        masked1, gray1 = mask_image(test1)
        masked2, gray2 = mask_image(test2)

        # compare the two images
        pixel_threshold = 50

        detector_total = np.uint64(0)
        detector = np.zeros((gray2.shape[0], gray2.shape[1]), dtype="uint8")

        # pixel by pixel comparison
        for i in range(0, gray2.shape[0]):
            for j in range(0, gray2.shape[1]):
                if abs(int(gray2[i, j]) - int(gray1[i, j])) > pixel_threshold:
                    detector[i, j] = 255

        # sum the detector array
        detector_total = np.uint64(np.sum(detector))
        print("detector_total = ", detector_total)
        print(" ")

        if detector_total > 30000:

            print("Smart Doorbell has detected someone/something at the door!")

            # define a unique name for the new video file
            timestr = time.strftime("doorbell-%Y%m%d-%H%M%S")

            os.system('libcamera-still --width 1280 --height 720 --vflip --hflip --timeout 1000 -o test1.jpg')
            time.sleep(2)
            os.system('libcamera-still --width 1280 --height 720 --vflip --hflip --timeout 1000 -o test2.jpg')

            print("Finished recording...converting to mp4...")
            
            command3 = f'ffmpeg -framerate 30 -i {timestr}.h264 -c copy {timestr}.mp4'
            os.system(command3)

            print("Finished converting file...available for viewing")

            # write masked images to file
            cv2.imwrite("gray1.jpg", gray1)
            cv2.imwrite("gray1.jpg", gray2)
            cv2.imwrite("masked1.jpg", masked1)
            cv2.imwrite("masked2.jpg", masked2)

            # upload video file to the cloud
            fullDirectory = '/home/pi/Documents/ENME435/HW/HW7/' + timestr + '.mp4'

            command4 = '/home/pi/dropbox_uploader.sh upload ' + fullDirectory + ' /'
            os.system(command4)

            # send email to user
            smtpUser = 'smartdoorbellenme435@gmail.com'
            smtpPass = 'mfhs hrfy zsxj rbqi'

            toAdd = 'jnagy@umd.edu'
            fromAdd = smtpUser

            f_time = datetime.now().strftime('%a %d %b @ %H:%M')
            subject = 'Smart Doorbell recording from: ' + f_time

            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = fromAdd
            msg['To'] = toAdd
            
            msg.preamble = 'Image @ ' + f_time

            body = email.mime.Text.MIMEText('Smart Doorbell video: ' + f_time)
            msg.attach(body)

            fp = open('test1.jpg', 'rb')
            img = MIMEImage(fp.read())
            fp.close()
            msg.attach(img)
            fp = open('test2.jpg', 'rb')
            img = MIMEImage(fp.read())
            fp.close()
            msg.attach(img)
            fp = open('gray1.jpg', 'rb')
            img = MIMEImage(fp.read())
            fp.close()
            msg.attach(img)
            fp = open('gray2.jpg', 'rb')
            img = MIMEImage(fp.read())
            fp.close()
            msg.attach(img)
            fp = open('masked1.jpg', 'rb')
            img = MIMEImage(fp.read())
            fp.close()
            msg.attach(img)
            fp = open('masked2.jpg', 'rb')
            img = MIMEImage(fp.read())
            fp.close()
            msg.attach(img)

            s = smtplib.SMTP('smtp.gmail.com', 587)
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(smtpUser, smtpPass)
            s.sendmail(fromAdd, toAdd, msg.as_string())
            s.quit()

            print("Email delivered!")

        else:
            print("Nothing detected...yet!")
except KeyboardInterrupt:
    print("Stopped")
