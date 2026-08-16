# probe_cameras.py
import cv2
for i in range(6):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)  # Windows: try DirectShow backend
    ok, frame = cap.read()
    print(f"index={i} opened={cap.isOpened()} read_ok={ok}")
    if ok:
        h,w = frame.shape[:2]
        print(f"  frame size: {w}x{h}")
    cap.release()