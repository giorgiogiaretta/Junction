"""Windows stand-in for PyTurboJPEG (no libturbojpeg here): decode/encode BGR via OpenCV. Client side only."""
import cv2
import numpy as np

TJPF_BGR = 0


class TurboJPEG:
    def __init__(self, *a, **k):
        pass

    def decode(self, jpeg_buf, pixel_format=TJPF_BGR, *a, **k):
        return cv2.imdecode(np.frombuffer(jpeg_buf, np.uint8), cv2.IMREAD_COLOR)

    def encode(self, img, quality=85, *a, **k):
        return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])[1].tobytes()
