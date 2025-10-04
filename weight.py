import serial
import time
import csv
import os
import logging
import signal
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, db
import subprocess
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ========== CONFIGURATION ==========
SCALE_PORTS = [
    '/dev/ttyUSB0'
]
CSV_PATH = "/home/evogene2/Desktop/get_weight/weight.csv"
FIREBASE_CRED = "/home/evogene2/Desktop/get_weight/Weight.json"
FIREBASE_URL = "https://getweight-5edee-default-rtdb.firebaseio.com/"
LOG_PATH = "/home/evogene2/Desktop/get_weight/weight_logger.log"
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY = 5  # seconds
WEIGHT_VALIDATION_THRESHOLD = 0.5  # kg
MAX_VALIDATION_RETRIES = 10

# ========== LOGGING SETUP ==========
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ========== FIREBASE SETUP ==========
def setup_firebase_with_retry():
    """Setup Firebase with retry mechanism for network issues"""
    max_retries = 3
    retry_delay = 10
    
    for attempt in range(max_retries):
        try:
            # Configure requests session with retry strategy
            session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            cred = credentials.Certificate(FIREBASE_CRED)
            firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_URL})
            ref_304 = db.reference('weights/12644')
            ref_303 = db.reference('weights/12644')
            
            logging.info("Firebase initialized successfully")
            return ref_304, ref_303
            
        except Exception as e:
            logging.warning(f"Firebase setup attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                logging.info(f"Retrying Firebase setup in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logging.error("Failed to initialize Firebase after all retries")
                raise

try:
    ref_304, ref_303 = setup_firebase_with_retry()
except Exception as e:
    logging.error(f"Failed to initialize Firebase: {e}")
    raise
# ========== SERIAL SCALE HANDLER ==========
class Scale:
    def __init__(self, port):
        self.port = port
        self.serial = None
        self.failed = False
        self.last_valid_weight = None
        self.connect()

    def connect(self):
        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            if not os.path.exists(self.port):
                logging.warning(f"Device {self.port} does not exist. Skipping connection attempt.")
                time.sleep(RECONNECT_DELAY)
                continue
            try:
                self.serial = serial.Serial(self.port, 9600, timeout=1)
                logging.info(f"Connected to scale at {self.port}")
                self.failed = False
                return
            except Exception as e:
                logging.warning(f"Attempt {attempt}: Error connecting to {self.port}: {e}")
                time.sleep(RECONNECT_DELAY)
        logging.error(f"Failed to connect to scale at {self.port} after {MAX_RECONNECT_ATTEMPTS} attempts")
        self.serial = None
        self.failed = True

    def read_weight(self, max_attempts=5, delay=0.2):
        for attempt in range(max_attempts):
            try:
                if self.serial is None or not self.serial.is_open:
                    logging.warning(f"Serial port {self.port} not open. Reconnecting...")
                    self.connect()
                    if self.serial is None:
                        continue
                self.serial.reset_input_buffer()
                line = self.serial.readline().decode('utf-8', errors='ignore').strip()
                logging.debug(f"Raw from {self.port}: {line}")
                if "kg" in line:
                    weight_str = line.split(",")[-1].replace("kg", "").replace("+", "").strip()
                    return float(weight_str)
            except Exception as e:
                logging.warning(f"Error reading from {self.port} (attempt {attempt+1}): {e}")
                self.connect()
            time.sleep(delay)
        logging.error(f"Failed to get valid weight from {self.port} after retries")
        return None

    def get_validated_weight(self):
        """Get a validated weight reading with consistency checks"""
        if self.last_valid_weight is None:
            # First reading, just get any valid reading
            weight = self.read_weight()
            if weight is not None:
                self.last_valid_weight = weight
                logging.info(f"Initial weight reading for {self.port}: {weight}kg")
            return weight
        
        # Try to get a consistent reading
        for attempt in range(MAX_VALIDATION_RETRIES):
            weight = self.read_weight()
            if weight is None:
                logging.warning(f"Scale {self.port} returned no reading (attempt {attempt + 1})")
                continue
            
            # Check if weight is within acceptable range
            weight_diff = abs(weight - self.last_valid_weight)
            if weight_diff <= WEIGHT_VALIDATION_THRESHOLD:
                self.last_valid_weight = weight
                logging.info(f"Valid weight reading for {self.port}: {weight}kg (diff: {weight_diff:.3f}kg)")
                return weight
            else:
                logging.warning(f"Weight reading for {self.port} too different: {weight}kg (diff: {weight_diff:.3f}kg, threshold: {WEIGHT_VALIDATION_THRESHOLD}kg)")
        
        # If we couldn't get a valid reading, use the last valid weight
        logging.warning(f"Using last valid weight for {self.port}: {self.last_valid_weight}kg after {MAX_VALIDATION_RETRIES} failed attempts")
        return self.last_valid_weight

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            logging.info(f"Closed serial port {self.port}")
# ========== CSV HANDLER ==========
def save_to_csv(timestamp, weights):
    file_exists = os.path.isfile(CSV_PATH)
    try:
        with open(CSV_PATH, mode="a", newline="") as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(["timestamp"] + [f"weight{i+1}" for i in range(len(weights))])
            writer.writerow([timestamp.isoformat()] + weights)
        logging.info(f"CSV saved: {timestamp.isoformat()}, {weights}")
    except Exception as e:
        logging.error(f"Error writing to CSV: {e}")

# ========== FIREBASE UPLOAD ==========
def upload_to_firebase(timestamp, weights):
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            # Scales 1 and 2 to weights/304
            data_304 = {'timestamp': timestamp.isoformat()}
            for i, w in enumerate(weights[:3], 1):  # Only first two
                data_304[f'weight{i}'] = w
            ref_304.push(data_304)
            logging.info(f"Firebase uploaded to weights/304: {data_304}")

            # Scale 3 to weights/303
            if len(weights) > 3:
                data_303 = {
                    'timestamp': timestamp.isoformat(),
                    'weight1': weights[2]
                }
                ref_303.push(data_303)
                logging.info(f"Firebase uploaded to weights/303: {data_303}")
            
            return  # Success, exit retry loop
            
        except Exception as e:
            logging.warning(f"Firebase upload attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                logging.info(f"Retrying Firebase upload in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logging.error(f"Firebase upload failed after {max_retries} attempts: {e}")

# ========== TIME SLOT HANDLER ==========
def get_next_slot():
    now = datetime.now()
    next_slot = (now + timedelta(minutes=10)).replace(second=0, microsecond=0)
    return next_slot - timedelta(minutes=now.minute % 10)

# ========== GRACEFUL SHUTDOWN ==========
scales = []

def cleanup_and_exit(signum, frame):
    logging.info("Received shutdown signal. Closing serial ports and exiting.")
    for scale in scales:
        scale.close()
    logging.info("Shutdown complete.")
    exit(0)

signal.signal(signal.SIGTERM, cleanup_and_exit)
signal.signal(signal.SIGINT, cleanup_and_exit)

# ========== MAIN LOOP ==========
def main():
    global scales
    scales = [Scale(port) for port in SCALE_PORTS]
    last_weights = [None] * len(scales)  # Initialize with None

    logging.info("Starting synchronized reading loop (every 10 minutes)...")
    while True:
        now = datetime.now()
        next_time = get_next_slot()
        wait_seconds = (next_time - now).total_seconds()
        logging.info(f"Sleeping for {int(wait_seconds)} seconds until next reading...")
        time.sleep(max(0, wait_seconds))

        t = datetime.now().replace(second=0, microsecond=0)
        weights = []
        for i, scale in enumerate(scales):
            w = scale.get_validated_weight()  # Use validated weight reading
            if w is not None:
                last_weights[i] = w  # Update last successful value
                weights.append(w)
            else:
                logging.error(f"Scale {i+1} ({scale.port}) returned no reading. Using last value: {last_weights[i]}")
                weights.append(last_weights[i])  # Use last value
                scale.failed = True  # Mark as failed to trigger reboot

        save_to_csv(t, weights)
        upload_to_firebase(t, weights)

        # Reboot if any scale failed to connect
        if any(scale.failed for scale in scales):
            logging.error("At least one scale failed to connect after retries. Rebooting system.")
            subprocess.run(['sudo', 'reboot'])

if __name__ == "__main__":
    main()
