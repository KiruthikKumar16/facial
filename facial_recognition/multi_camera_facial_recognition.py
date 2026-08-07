import os
import cv2
import numpy as np
import face_recognition

# Camera configuration
LAPTOP_CAMERA_INDEX = 0
IP_CAMERA_URL = 'rtsp://192.168.1.100:554'
CCTV_CAMERA_INDEX = 1  # Adjust based on your CCTV device

KNOWN_FACES_DIR = 'known_faces'
TOLERANCE = 0.6
MODEL = 'hog'  # Use 'cnn' if you have GPU support and dlib compiled with CUDA
FRAME_RESIZE_FACTOR = 0.5


def load_known_faces():
    known_encodings = []
    known_names = []

    if not os.path.isdir(KNOWN_FACES_DIR):
        print(f'No known faces directory found at "{KNOWN_FACES_DIR}". Skipping recognition.')
        return known_encodings, known_names

    for name in os.listdir(KNOWN_FACES_DIR):
        person_dir = os.path.join(KNOWN_FACES_DIR, name)
        if not os.path.isdir(person_dir):
            continue

        for filename in os.listdir(person_dir):
            filepath = os.path.join(person_dir, filename)
            image = face_recognition.load_image_file(filepath)
            locations = face_recognition.face_locations(image, model=MODEL)
            if not locations:
                print(f'No face found in {filepath}, skipping')
                continue

            encoding = face_recognition.face_encodings(image, locations)[0]
            known_encodings.append(encoding)
            known_names.append(name)
            print(f'Loaded known face for {name} from {filename}')

    return known_encodings, known_names


def capture_camera(source, source_name, known_face_encodings, known_face_names):
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f'Error: Failed to open camera source {source_name} ({source})')
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f'Error: Failed to capture from {source_name}')
            break

        small_frame = cv2.resize(frame, (0, 0), fx=FRAME_RESIZE_FACTOR, fy=FRAME_RESIZE_FACTOR)
        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_small, model=MODEL)
        face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

        face_names = []
        for face_encoding in face_encodings:
            name = 'Unknown'
            if known_face_encodings:
                distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                best_match_index = np.argmin(distances)
                if distances[best_match_index] <= TOLERANCE:
                    name = known_face_names[best_match_index]
            face_names.append(name)

        for (top, right, bottom, left), name in zip(face_locations, face_names):
            top = int(top / FRAME_RESIZE_FACTOR)
            right = int(right / FRAME_RESIZE_FACTOR)
            bottom = int(bottom / FRAME_RESIZE_FACTOR)
            left = int(left / FRAME_RESIZE_FACTOR)

            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.rectangle(frame, (left, bottom - 24), (right, bottom), (0, 255, 0), cv2.FILLED)
            cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        cv2.imshow(source_name, frame)
        if cv2.waitKey(1) == 27:  # ESC key
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    known_face_encodings, known_face_names = load_known_faces()

    print('Select camera source:')
    print('1. Laptop Camera')
    print('2. IP Camera')
    print('3. CCTV Camera')
    choice = input('Enter choice (1-3): ')

    if choice == '1':
        capture_camera(LAPTOP_CAMERA_INDEX, 'Laptop Camera', known_face_encodings, known_face_names)
    elif choice == '2':
        capture_camera(IP_CAMERA_URL, 'IP Camera', known_face_encodings, known_face_names)
    elif choice == '3':
        capture_camera(CCTV_CAMERA_INDEX, 'CCTV Camera', known_face_encodings, known_face_names)
    else:
        print('Invalid choice')
