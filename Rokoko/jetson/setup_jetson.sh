#!/usr/bin/env bash
# Run ON the Jetson Nano (JetPack 4.6, Python 3.6). Minimal, no torch needed for the servo receiver.
set -e
sudo apt-get update
sudo apt-get install -y python3-pip python3-numpy i2c-tools git
pip3 install --user adafruit-circuitpython-servokit
sudo usermod -aG i2c "$USER"   # re-login afterwards
echo "Done. Check I2C: sudo i2cdetect -y -r 1   (PCA9685 shows at 0x40)"
echo "Optional ML: torch 1.9 wheel from NVIDIA 'PyTorch for Jetson' forum thread (JetPack 4.6, Python 3.6)."
