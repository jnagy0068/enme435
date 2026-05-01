import numpy as np
import cv2
import time
import os
import threading
import smtplib
from smtplib import SMTP
from smtplib import SMTPException
import email
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from picamera2 import Picamera2

# smartdoorbellenme435@gmail.com
# smartdoorbell12
# mfhs hrfy zsxj rbqi

# --- Video recording setup ---
VIDEO_FPS = 20
VIDEO_SIZE = (1280, 720)
videostr = time.strftime("doorbell_recording-%Y%m%d-%H%M%S.avi")
fourcc = cv2.VideoWriter_fourcc(*'XVID')
video_writer = cv2.VideoWriter(videostr, fourcc, VIDEO_FPS, VIDEO_SIZE)

# Shared state between threads
latest_frame = None
frame_lock = threading.Lock()
stop_event = threading.Event()


def capture_frame(picam2):
    """Capture a frame directly into a BGR numpy array (no temp file)."""
    frame = picam2.capture_array()
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    frame = cv2.flip(frame, -1)  # vflip + hflip
    return frame


def select_points(img):  # for initial mask point selection
    points = []
    for i in range(0, 4):  # number of points needed to form shape
        bbox = cv2.selectROI(img, False)
        print(bbox)
        points.append([bbox[0], bbox[1]])
    print(points)
    return points


def mask_image(img):
    mask = np.zeros((img.shape[0], img.shape[1]), dtype="uint8")
    pts = np.array([[385, 16], [854, 20], [904, 655], [434, 673]], dtype=np.int32)  # mask points
    cv2.fillConvexPoly(mask, pts, 255)
    masked = cv2.bitwise_and(img, img, mask=mask)
    gray = cv2.resize(masked, (200, int(masked.shape[0] * 200 / masked.shape[1])))
    gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (11, 11), 0)  # kernel size
    return masked, gray


def video_thread(picam2):
    """Background thread: continuously captures frames, shows live feed, and records to file."""
    global latest_frame
    print("Video recording started —  press Q in the preview window to stop and save.")
    while not stop_event.is_set():
        frame = capture_frame(picam2)

        # Update shared latest frame for motion detection
        with frame_lock:
            latest_frame = frame.copy()

        # Write to video file
        video_writer.write(frame)

        # Show live preview
        cv2.imshow("Smart Doorbell - Press Q to stop & save", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            stop_event.set()
            break

    video_writer.release()
    cv2.destroyAllWindows()
    print(f"Video saved as: {videostr}")


# --- Initialize picamera2 (video mode for continuous capture) ---
picam2 = Picamera2()
config = picam2.create_video_configuration(main={"size": VIDEO_SIZE})
picam2.configure(config)
picam2.start()
time.sleep(2)  # warm up

# Start video/preview thread
t = threading.Thread(target=video_thread, args=(picam2,), daemon=True)
t.start()

# Wait until first frame is available
while latest_frame is None:
    time.sleep(0.1)

# --- Main motion detection loop ---
counter = -1

try:
    while not stop_event.is_set():

        counter += 1
        print(" ")
        print("Times through loop since starting:", counter)
        print(" ")

        # Grab 1st frame from shared latest
        with frame_lock:
            test1 = latest_frame.copy()
        time.sleep(2)

        # Grab 2nd frame after delay
        with frame_lock:
            test2 = latest_frame.copy()

        print("Captured 1st & 2nd image for analysis...")

        # mask images
        masked1, gray1 = mask_image(test1)
        masked2, gray2 = mask_image(test2)

        # compare the two images
        pixel_threshold = 50
        detector = np.zeros((gray2.shape[0], gray2.shape[1]), dtype="uint8")

        # pixel by pixel comparison
        for i in range(0, gray2.shape[0]):
            for j in range(0, gray2.shape[1]):
                if abs(int(gray2[i, j]) - int(gray1[i, j])) > pixel_threshold:
                    detector[i, j] = 255

        detector_total = np.uint64(np.sum(detector))
        print("detector_total = ", detector_total)
        print(" ")

        if detector_total > 30000:

            print("Smart Doorbell has detected someone/something at the door!")

            timestr = time.strftime("doorbell-%Y%m%d-%H%M%S")

            # grab two fresh confirmation frames
            with frame_lock:
                test1 = latest_frame.copy()
            time.sleep(2)
            with frame_lock:
                test2 = latest_frame.copy()

            # write all images to file for email attachment
            cv2.imwrite("test1.jpg",   test1)
            cv2.imwrite("test2.jpg",   test2)
            cv2.imwrite("gray1.jpg",   gray1)
            cv2.imwrite("gray2.jpg",   gray2)
            cv2.imwrite("masked1.jpg", masked1)
            cv2.imwrite("masked2.jpg", masked2)

            # upload snapshot to Dropbox
            fullDirectory = '/home/pi/Documents/ENME435/HW/HW7/' + timestr + '.jpg'
            cv2.imwrite(fullDirectory, test1)
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

            body = MIMEText('Smart Doorbell alert: ' + f_time)
            msg.attach(body)

            for fname in ['test1.jpg', 'test2.jpg', 'gray1.jpg', 'gray2.jpg', 'masked1.jpg', 'masked2.jpg']:
                with open(fname, 'rb') as fp:
                    img = MIMEImage(fp.read())
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
    print("Stopped via Ctrl+C")
    stop_event.set()
finally:
    stop_event.set()
    t.join(timeout=3)
    picam2.stop()
    print("Done.")import numpy as np
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

# enme435burner@gmail.com:apasswordofalltime123

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

    # final selected points for porch
    # pts = np.array([[553, 707], [700, 650], [843, 550], [833, 124], [1100, 109], [1100, 619], [906, 700]], dtype=np.int32) # mitchell's array
    pts = np.array([[385, 16], [854, 20], [904, 655], [434, 673]], dtype=np.int32) # my array
    cv2.fillConvexPoly(mask, pts, 255)

    # pts = np.array([[553, 707], [300, 600], [400, 590], [550, 650]], dtype=np.int32) # walkway coordinates
    # cv2.fillConvexPoly(mask, pts, 255)

    masked = cv2.bitwise_and(img, img, mask=mask)

    gray = cv2.resize(masked, (200, int(masked.shape[0] * 200 / masked.shape[1])))

    gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

    gray = cv2.GaussianBlur(gray, (11, 11), 0) # play with kernel size

    return masked, gray

# Counter variable for analysis
counter = 0

# Mask calibration
# img = cv2.imread("calibration.jpg")
# select_points(img)

try:
    while True:
        if cv2.waitKey(1) == ord('q'):
            break

        counter += 1
        print(" ")
        print("----Times through loop since starting:", counter, "----")
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
            smtpUser = 'enme435burner@gmail.com'
            smtpPass = 'vizp isjl dhdr kybp'

            toAdd = 'shanayk@umd.edu'
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
    
