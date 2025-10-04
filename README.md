Plant Weight Monitoring System

A Python system to monitor plant weight using serial-connected digital scales. Data is validated, logged locally to CSV, and uploaded to Firebase Realtime Database for real-time tracking and analysis.

Features

Automated weight readings every 10 minutes.

Consistency checks for reliable measurements.

Local CSV logging and detailed activity logs.

Firebase integration with retry mechanism.

Auto-reconnect for disconnected scales and graceful shutdown.

Automatic system reboot if a scale fails consistently.

Hardware Requirements

Digital scale(s) with serial (USB/TTL) output.

Raspberry Pi or compatible Linux device.

Supports multiple scales simultaneously.

Installation & Usage

Clone the repository and install dependencies:
git clone https://github.com/yourusername/plant-weight-monitor.git

cd plant-weight-monitor
pip install pyserial firebase-admin requests

Edit the script to configure your setup:

SCALE_PORTS – List of serial ports for scales (e.g., /dev/ttyUSB0)

CSV_PATH – Path for CSV logging

FIREBASE_CRED – Path to Firebase service account JSON

FIREBASE_URL – Firebase Realtime Database URL

Run the script:
python3 weight_monitor.py

The system will automatically read weights, save data locally, upload to Firebase, and handle connection issues.

License

MIT License
