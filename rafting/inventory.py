"""Best-effort inventory for display only, outside the control loop."""
from concurrent.futures import ThreadPoolExecutor
import cv2
from .vision import Vision


class InventoryReader:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='rafting-stock')
        self.future = None
        self.reader = None
        self.request_at = -100.
        self.request_image = None
        self.result_image = None
        self.value = None

    def read(self, roi):
        if self.reader is None:
            self.reader = Vision()
        return self.reader.read_stock(roi)

    def sample(self, vision, frame, obs, now):
        if obs.state != 'ready' or obs.button is None:
            return None
        game = vision.normalize(frame)
        left, top, right, _ = vision.rect
        by = (obs.button[1]-top)*540/(right-left)
        roi = vision.stock_region(game, by)
        if roi.size == 0:
            return None
        image = cv2.resize(roi, (64,24), interpolation=cv2.INTER_AREA)
        if self.future is not None and self.future.done():
            try:
                self.value = self.future.result()
            except Exception:
                self.value = None
            self.result_image = self.request_image
            self.future = None
        matches = self.result_image is not None and cv2.absdiff(image,self.result_image).mean() < .35
        if self.future is None and now-self.request_at >= 5:
            self.request_at = now
            self.request_image = image
            self.future = self.pool.submit(self.read, roi.copy())
        return self.value if matches and now-self.request_at < 15 else None

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
