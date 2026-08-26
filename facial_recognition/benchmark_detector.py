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

    # calibration logic matching main_cpu.py
    calib_times = []
    for _ in range(30):
        img = (np.random.rand(480,640,3) * 255).astype('uint8')
        import cv2
        small = cv2.resize(img, (256, 256), interpolation=cv2.INTER_LINEAR)
        t0 = time.perf_counter()
        det.detect(small)
        calib_times.append((time.perf_counter() - t0) * 1000.0)

    median_latency = float(np.median(calib_times))
    if median_latency < 15.0:
        tier = 'fast (320x320, skip 3)'
    elif median_latency < 30.0:
        tier = 'mid (256x256, skip 5)'
    else:
        tier = 'slow (192x192, skip 8)'

    logger.info('--- Calibration Phase ---')
    logger.info('Median latency: %.2f ms', median_latency)
    logger.info('Theoretical tier selection: %s', tier)
    logger.info('-------------------------')

    times: list[float] = []
    for i in range(10):
        img = (np.random.rand(480,640,3) * 255).astype('uint8')
        t0 = time.perf_counter()
        res = det.detect(img)
        dt = (time.perf_counter() - t0) * 1000.0
        times.append(dt)
        logger.info('iter %d: detected %d faces, time=%.2f ms', i, len(res), dt)

    times_arr = np.asarray(times, dtype=np.float64)
    logger.info('Raw detector (320x320) median time %.2f ms, mean %.2f ms', float(np.median(times_arr)), float(np.mean(times_arr)))

if __name__ == '__main__':
    main()
