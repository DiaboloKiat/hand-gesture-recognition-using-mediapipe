#!/usr/bin/env python
# -*- coding: utf-8 -*-
import csv
import copy
import argparse
import itertools
from collections import Counter
from collections import deque

import cv2 as cv
import numpy as np
import mediapipe as mp

from utils import CvFpsCalc
from model import KeyPointClassifier


class GestureRecognition:
    def __init__(self, use_static_image_mode=False, min_detection_confidence=0.5, min_tracking_confidence=0.5, history_length=16):
        self.use_static_image_mode = use_static_image_mode
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.history_length = history_length

        # Load models
        self.hands, self.keypoint_classifier, self.keypoint_classifier_labels = self.load_model()

        # Finger gesture history
        self.point_history = deque(maxlen=history_length)

    def load_model(self):
        # Model load #############################################################
        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(
            static_image_mode=self.use_static_image_mode,
            max_num_hands=1,
            min_detection_confidence=self.min_detection_confidence,
            min_tracking_confidence=self.min_tracking_confidence,
        )

        keypoint_classifier = KeyPointClassifier()

        # Read labels ###########################################################
        with open('/home/diabolokiat/project_hand/catkin_ws/src/hand-gesture-recognition-using-mediapipe/hand_gesture/src/model/keypoint_classifier/keypoint_classifier_label.csv', encoding='utf-8-sig') as f:
            keypoint_classifier_labels = csv.reader(f)
            keypoint_classifier_labels = [row[0] for row in keypoint_classifier_labels]

        # with open('/home/seadrone/project_seadrone/catkin_ws/src/hand-gesture-recognition-using-mediapipe/hand_gesture/src/model/keypoint_classifier/keypoint_classifier_label.csv', encoding='utf-8-sig') as f:
        #     keypoint_classifier_labels = csv.reader(f)
        #     keypoint_classifier_labels = [row[0] for row in keypoint_classifier_labels]

        return hands, keypoint_classifier, keypoint_classifier_labels

    def recognize(self, image, number=-1, mode=0):

        # Move constants to other place
        USE_BRECT = True

        debug_image = copy.deepcopy(image)

        # Saving gesture id for drone controlling
        gesture_id = -1

        # Detection implementation 
        ####################################################################
        image = cv.cvtColor(debug_image, cv.COLOR_BGR2RGB)

        image.flags.writeable = False
        results = self.hands.process(image)
        image.flags.writeable = True

        #####################################################################
        if results.multi_hand_landmarks is not None:
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                # Bounding box calculation
                brect = self._calc_bounding_rect(debug_image, hand_landmarks)
                
                # Landmark calculation
                landmark_list = self._calc_landmark_list(debug_image, hand_landmarks)

                # Conversion to relative coordinates / normalized coordinates
                pre_processed_landmark_list = self._pre_process_landmark(landmark_list)

                # Write to the dataset file
                self._logging_csv(number, mode, pre_processed_landmark_list)

                # Hand sign classification
                hand_sign_id = self.keypoint_classifier(pre_processed_landmark_list)
                if hand_sign_id == 2:  # Point gesture
                    self.point_history.append(landmark_list[8])
                else:
                    self.point_history.append([0, 0])

                # Drawing part
                debug_image = self._draw_bounding_rect(USE_BRECT, debug_image, brect)
                debug_image = self._draw_landmarks(debug_image, landmark_list)
                debug_image = self._draw_info_text(debug_image, brect, handedness, self.keypoint_classifier_labels[hand_sign_id])

                # Saving gesture
                gesture_id = hand_sign_id
        else:
            self.point_history.append([0, 0])

        debug_image = self.draw_point_history(debug_image, self.point_history)

        return debug_image, gesture_id

    def draw_point_history(self, image, point_history):
        for index, point in enumerate(point_history):
            if point[0] != 0 and point[1] != 0:
                cv.circle(image, (point[0], point[1]), 1 + int(index / 2),
                          (152, 251, 152), 2)

        return image

    def draw_info(self, image, fps, mode, number):
        cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX,
                   1.0, (0, 0, 0), 4, cv.LINE_AA)
        cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX,
                   1.0, (255, 255, 255), 2, cv.LINE_AA)

        mode_string = ['Logging Key Point']
        if 1 <= mode <= 2:
            cv.putText(image, "MODE:" + mode_string[mode - 1], (10, 90), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv.LINE_AA)
            if 0 <= number <= 35:
                cv.putText(image, "NUM:" + str(number), (10, 110), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv.LINE_AA)
        return image

    def _logging_csv(self, number, mode, landmark_list):
        if mode == 0:
            pass
        if mode == 1 and (0 <= number <= 9):
            print("WRITE")
            # csv_path = '/home/seadrone/project_seadrone/catkin_ws/src/hand-gesture-recognition-using-mediapipe/hand_gesture/src/model/keypoint_classifier/keypoint_new.csv'
            csv_path = '/home/diabolokiat/project_hand/catkin_ws/src/hand-gesture-recognition-using-mediapipe/hand_gesture/src/model/keypoint_classifier/keypoint_new.csv'
            with open(csv_path, 'a', newline="") as f:
                writer = csv.writer(f)
                writer.writerow([number, *landmark_list])
        return

    def _calc_bounding_rect(self, image, landmarks):
        image_width, image_height = image.shape[1], image.shape[0]

        landmark_array = np.empty((0, 2), int)

        for _, landmark in enumerate(landmarks.landmark):
            landmark_x = min(int(landmark.x * image_width), image_width - 1)
            landmark_y = min(int(landmark.y * image_height), image_height - 1)

            landmark_point = [np.array((landmark_x, landmark_y))]

            landmark_array = np.append(landmark_array, landmark_point, axis=0)

        x, y, w, h = cv.boundingRect(landmark_array)

        return [x, y, x + w, y + h]

    def _calc_landmark_list(self, image, landmarks):
        image_width, image_height = image.shape[1], image.shape[0]

        landmark_point = []

        # Keypoint
        for _, landmark in enumerate(landmarks.landmark):
            landmark_x = min(int(landmark.x * image_width), image_width - 1)
            landmark_y = min(int(landmark.y * image_height), image_height - 1)
            # landmark_z = landmark.z

            landmark_point.append([landmark_x, landmark_y])

        return landmark_point

    def _pre_process_landmark(self, landmark_list):
        temp_landmark_list = copy.deepcopy(landmark_list)

        # Convert to relative coordinates
        base_x, base_y = 0, 0
        for index, landmark_point in enumerate(temp_landmark_list):
            if index == 0:
                base_x, base_y = landmark_point[0], landmark_point[1]

            temp_landmark_list[index][0] = temp_landmark_list[index][0] - base_x
            temp_landmark_list[index][1] = temp_landmark_list[index][1] - base_y

        # Convert to a one-dimensional list
        temp_landmark_list = list(
            itertools.chain.from_iterable(temp_landmark_list))

        # Normalization
        max_value = max(list(map(abs, temp_landmark_list)))

        def normalize_(n):
            return n / max_value

        temp_landmark_list = list(map(normalize_, temp_landmark_list))

        return temp_landmark_list

    def _draw_landmarks(self, image, landmark_point):
        if len(landmark_point) > 0:
            # Thumb
            cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]), (0, 255, 0), 2)

            # Index finger
            cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]), (0, 255, 0), 2)

            # Middle finger
            cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]), (0, 255, 0), 2)

            # Ring finger
            cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]), (0, 255, 0), 2)

            # Little finger
            cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]), (0, 255, 0), 2)

            # Palm
            cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[1]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[1]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[5]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[5]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]), (0, 255, 0), 2)
            cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[0]), (0, 0, 0), 8)
            cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[0]), (0, 255, 0), 2)

        # Key Points
        for index, landmark in enumerate(landmark_point):
            if index == 0:  # Wrist 1
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 1:  # Wrist 2
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 2:  # Thumb: Root
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 3:  # Thumb: 1st joint
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 4:  # Thumb: fingertip
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 2)
            if index == 5:  # Index finger: Root
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 6:  # Index finger: 2nd joint
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 7:  # Index finger: 1st joint
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 8:  # Index finger: fingertip
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 2)
            if index == 9:  # Middle finger: Root
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 10:  # Middle finger: 2nd joint
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 11:  # Middle finger: 1st joint
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 12:  # Middle finger: point first
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 2)
            if index == 13:  # Ring finger: Root
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 14:  # Ring finger: 2nd joint
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 15:  # Ring finger: 1st joint
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 16:  # Ring finger: fingertip
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 2)
            if index == 17:  # Little finger: base
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 18:  # Little finger: 2nd joint
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 19:  # Little finger: 1st joint
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 2)
            if index == 20:  # Little finger: point first
                cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 255), -1)
                cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 2)

        return image

    def _draw_info_text(self, image, brect, handedness, hand_sign_text):
        cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[1] - 22), (0, 0, 0), -1)

        info_text = handedness.classification[0].label[0:]
        if hand_sign_text != "":
            info_text = info_text + ':' + hand_sign_text
        cv.putText(image, info_text, (brect[0] + 5, brect[1] - 4), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv.LINE_AA)

        return image

    def _draw_bounding_rect(self, use_brect, image, brect):
        if use_brect:
            # Outer rectangle
            cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[3]), (0, 0, 0), 1)

        return image

class GestureBuffer:
    def __init__(self, buffer_len=10):
        self.buffer_len = buffer_len
        self._buffer = deque(maxlen=buffer_len)

    def add_gesture(self, gesture_id):
        self._buffer.append(gesture_id)

    def get_gesture(self):
        counter = Counter(self._buffer).most_common()
        if counter[0][1] >= (self.buffer_len - 1):
            self._buffer.clear()
            return counter[0][0]
        else:
            return
