# Jetson Nano (extra)
Realistic role: low-latency **servo/robot-hand driver** and small on-device inference, fed by the laptop over UDP (Wi-Fi/Ethernet). Training stays on the laptop (RTX 5070 Ti).
- JetPack 4.6 => Python 3.6, CUDA 10.2; PyTorch max ~1.9-1.10 (NVIDIA "PyTorch for Jetson" wheel). Keep code stdlib/numpy.
- Setup: copy this folder to the Jetson, `bash setup_jetson.sh`, `python3 receiver.py`.
- Laptop: `python src/forward_to_jetson.py --jetson <ip> --mock` to test with fake fingers.
- Wire: PCA9685 on I2C bus 1 (pins 3/5), servos on channels 0-4, external 5-6V supply for servos (common GND).
