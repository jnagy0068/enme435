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

# --- Save directory (local) ---
SAVE_DIR = '/home/pi/doorbell_recordings'
os.makedirs(SAVE_DIR, exist_ok=True)

# --- Video settings ---
VIDEO_FPS = 20
VIDEO_SIZE = (1280, 720)
VIDEO_DURATION = 5  # seconds

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


def record_clip(picam2, filename):
    """Record a VIDEO_DURATION second clip when detection is triggered."""
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    writer = cv2.VideoWriter(filename, fourcc, VIDEO_FPS, VIDEO_SIZE)
    total_frames = VIDEO_FPS * VIDEO_DURATION
    print(f"Recording {VIDEO_DURATION}s clip to {filename}...")
    for _ in range(total_frames):
        frame = capture_frame(picam2)
        writer.write(frame)
    writer.release()
    print(f"Clip saved: {filename}")


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
    # pts = np.array([[553, 707], [700, 650], [843, 550], [833, 124], [1100, 109], [1100, 619], [906, 700]], dtype=np.int32) # mitchell's array
    pts = np.array([[385, 16], [854, 20], [904, 655], [434, 673]], dtype=np.int32)  # my array
    cv2.fillConvexPoly(mask, pts, 255)
    # pts = np.array([[553, 707], [300, 600], [400, 590], [550, 650]], dtype=np.int32) # walkway coordinates
    # cv2.fillConvexPoly(mask, pts, 255)
    masked = cv2.bitwise_and(img, img, mask=mask)
    gray = cv2.resize(masked, (200, int(masked.shape[0] * 200 / masked.shape[1])))
    gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (11, 11), 0)  # play with kernel size
    return masked, gray


def preview_thread(picam2):
    """Background thread: continuously captures frames and shows live preview."""
    global latest_frame
    print("Live preview started — press Q in the preview window to stop.")
    while not stop_event.is_set():
        frame = capture_frame(picam2)

        # Update shared latest frame for motion detection
        with frame_lock:
            latest_frame = frame.copy()

        # Show live preview
        cv2.imshow("Smart Doorbell - Press Q to stop", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            stop_event.set()
            break

    cv2.destroyAllWindows()


# --- Initialize picamera2 ---
picam2 = Picamera2()
config = picam2.create_video_configuration(main={"size": VIDEO_SIZE})
picam2.configure(config)
picam2.start()
time.sleep(2)  # warm up

# Start preview thread
t = threading.Thread(target=preview_thread, args=(picam2,), daemon=True)
t.start()

# Wait until first frame is available
while latest_frame is None:
    time.sleep(0.1)

# --- Main motion detection loop ---
counter = 0
# Mask calibration
# img = capture_frame(picam2)
# select_points(img)

try:
    while not stop_event.is_set():

        counter += 1
        print(" ")
        print("----Times through loop since starting:", counter, "----")
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

            # Record a 5-second clip
            clip_path = os.path.join(SAVE_DIR, timestr + '.avi')
            record_clip(picam2, clip_path)

            # grab two confirmation frames after recording
            with frame_lock:
                test1 = latest_frame.copy()
            time.sleep(2)
            with frame_lock:
                test2 = latest_frame.copy()

            # save images locally
            cv2.imwrite(os.path.join(SAVE_DIR, "test1.jpg"),   test1)
            cv2.imwrite(os.path.join(SAVE_DIR, "test2.jpg"),   test2)
            cv2.imwrite(os.path.join(SAVE_DIR, "gray1.jpg"),   gray1)
            cv2.imwrite(os.path.join(SAVE_DIR, "gray2.jpg"),   gray2)
            cv2.imwrite(os.path.join(SAVE_DIR, "masked1.jpg"), masked1)
            cv2.imwrite(os.path.join(SAVE_DIR, "masked2.jpg"), masked2)
            print(f"Images saved to {SAVE_DIR}")

            # send email to user
            smtpUser = 'smartdoorbellenme435@gmail.com'
            smtpPass = 'mfhs hrfy zsxj rbqi'

            toAdd = 'jnagy@terpmail.umd.edu'
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
                fpath = os.path.join(SAVE_DIR, fname)
                with open(fpath, 'rb') as fp:
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
    print("Done.")
