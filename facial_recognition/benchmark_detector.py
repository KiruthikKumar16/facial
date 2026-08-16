"""Small benchmark to measure detector timings without camera input.
Run: myenv/Scripts/python.exe benchmark_detector.py
"""
import logging
import time
import numpy as np

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('benchmark')

from detector import InsightFaceDetector

def main():
    det = InsightFaceDetector(use_gpu=False, det_size=(320,320), fast_detector=True)
    logger.info('fast_detector=%s, rec_model=%s', det.use_fast_detector, det.rec_model is not None)
    # create a synthetic image (RGB)
    img = (np.random.rand(480,640,3) * 255).astype('uint8')

    # warmup
    for i in range(2):
        _ = det.detect(img)

    times: list[float] = []
    for i in range(10):
        t0 = time.perf_counter()
        res = det.detect(img)
        dt = (time.perf_counter() - t0) * 1000.0
        times.append(dt)
        logger.info('iter %d: detected %d faces, time=%.2f ms', i, len(res), dt)

    times_arr = np.asarray(times, dtype=np.float64)
    logger.info('median time %.2f ms, mean %.2f ms', float(np.median(times_arr)), float(np.mean(times_arr)))

if __name__ == '__main__':
    main()
