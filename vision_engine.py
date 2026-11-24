import cv2
import time
import os
import ssl
import urllib.request
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# MediaPipe Pose Landmark Indices
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16

POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24), (23, 25), (24, 26),
    (25, 27), (26, 28)
]


class VisionEngine:
    def __init__(self, connect_drone=False):
        self.cap = None
        self.detector = None
        self._init_pose_detector()

        # Target elbow angles for "Remember the Time" moves (plus fallback moves)
        self.target_moves = {
            "CROWN_REACH": {"l_elbow": 145, "r_elbow": 145},
            "EGYPTIAN_FRAME": {"l_elbow": 90, "r_elbow": 165},
            "SHOULDER_POP_L": {"l_elbow": 55, "r_elbow": 170},
            "SHOULDER_POP_R": {"l_elbow": 170, "r_elbow": 55},
            "GROOVE_LOCK": {"l_elbow": 90, "r_elbow": 90},
            "UP": {"l_elbow": 160, "r_elbow": 160},
            "RIGHT_ARM_UP": {"l_elbow": 45, "r_elbow": 160},
            "DOWN": {"l_elbow": 45, "r_elbow": 45},
            "LEFT": {"l_elbow": 90, "r_elbow": 180},
            "RIGHT": {"l_elbow": 180, "r_elbow": 90},
        }

    def _init_pose_detector(self):
        """Initializes MediaPipe PoseLandmarker."""
        model_path = "pose_landmarker_lite.task"
        if not os.path.exists(model_path):
            print("[VisionEngine] Downloading MediaPipe PoseLandmarker model...")
            url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
            context = ssl._create_unverified_context()
            try:
                with urllib.request.urlopen(url, context=context) as response, open(model_path, 'wb') as out_file:
                    out_file.write(response.read())
            except Exception as e:
                print(f"[VisionEngine Error] Failed to download model: {e}")
                raise

        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.detector = vision.PoseLandmarker.create_from_options(options)

    def open_camera(self, index=0):
        self.release_camera()
        backend = cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(index, backend)

        if not self.cap.isOpened():
            self.cap.release()
            self.cap = cv2.VideoCapture(index)

        if not self.cap.isOpened():
            print(f"[VisionEngine Error] Could not open camera at index {index}")
            self.cap = None
            return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return True

    def read_frame(self):
        if self.cap is None or not self.cap.isOpened():
            return False, None
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return False, None
        return True, frame

    def _calculate_angle(self, a, b, c):
        """Calculates joint angle given 3 points (shoulder, elbow, wrist)."""
        a = np.array(a)
        b = np.array(b)
        c = np.array(c)
        radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
        angle = np.abs(radians * 180.0 / np.pi)
        if angle > 180.0:
            angle = 360.0 - angle
        return angle

    def process_frame(self, draw=True, target_move=None):
        """
        Processes camera frame, draws skeleton, and scores user's pose
        against the active target_move.
        """
        success, frame = self.read_frame()
        if not success:
            return None, None

        # Mirror frame for a natural game experience
        frame = cv2.flip(frame, 1)
        frame = cv2.resize(frame, (960, 720))
        h, w, _ = frame.shape

        rgb_frame = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        detection_result = self.detector.detect(mp_image)

        dance_status = "WAITING"
        feedback_text = "Get Ready!"
        person_detected = False

        if detection_result.pose_landmarks and len(detection_result.pose_landmarks) > 0:
            landmarks = detection_result.pose_landmarks[0]
            person_detected = True

            # Draw skeleton overlay
            if draw:
                for start_idx, end_idx in POSE_CONNECTIONS:
                    if start_idx < len(landmarks) and end_idx < len(landmarks):
                        pt1 = (int(landmarks[start_idx].x * w), int(landmarks[start_idx].y * h))
                        pt2 = (int(landmarks[end_idx].x * w), int(landmarks[end_idx].y * h))
                        cv2.line(frame, pt1, pt2, (0, 255, 0), 2)

                for lm in landmarks:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)

            try:
                # Extract coordinates for arm joints
                l_sh = [landmarks[LEFT_SHOULDER].x, landmarks[LEFT_SHOULDER].y]
                l_el = [landmarks[LEFT_ELBOW].x, landmarks[LEFT_ELBOW].y]
                l_wr = [landmarks[LEFT_WRIST].x, landmarks[LEFT_WRIST].y]

                r_sh = [landmarks[RIGHT_SHOULDER].x, landmarks[RIGHT_SHOULDER].y]
                r_el = [landmarks[RIGHT_ELBOW].x, landmarks[RIGHT_ELBOW].y]
                r_wr = [landmarks[RIGHT_WRIST].x, landmarks[RIGHT_WRIST].y]

                l_angle = self._calculate_angle(l_sh, l_el, l_wr)
                r_angle = self._calculate_angle(r_sh, r_el, r_wr)

                # Judge pose if a target move is active on the timeline
                if target_move in self.target_moves:
                    target = self.target_moves[target_move]
                    l_diff = abs(l_angle - target["l_elbow"])
                    r_diff = abs(r_angle - target["r_elbow"])

                    if l_diff < 25 and r_diff < 25:
                        dance_status = "PERFECT"
                        feedback_text = "PERFECT!"
                    elif l_diff < 45 and r_diff < 45:
                        dance_status = "GOOD"
                        feedback_text = "GOOD!"
                    else:
                        dance_status = "MISS"
                        feedback_text = "MISS / ADJUST POSE"
                else:
                    dance_status = "ACTIVE"
                    feedback_text = "Freestyle / Stand By"

            except Exception as e:
                print(f"[Joint Calculation Error]: {e}")

        # HUD Banner on camera feed
        cv2.rectangle(frame, (0, 0), (w, 55), (0, 0, 0), -1)
        status_color = (0, 255, 0) if person_detected else (0, 165, 255)
        status_text = f"TARGET MOVE: {target_move or 'NONE'} | STATUS: {feedback_text}"
        cv2.putText(frame, status_text, (15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

        result = {
            "status": dance_status,
            "feedback_text": feedback_text,
            "timestamp": time.time()
        }

        return result, frame

    def release_camera(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        print("[VisionEngine] Camera released.")

    def close(self):
        self.release_camera()
        if self.detector:
            self.detector.close()
            self.detector = None