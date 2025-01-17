"""
@author: Viet Nguyen <nhviet1009@gmail.com>
"""

import gym_super_mario_bros
from gym.spaces import Box
from gym import Wrapper
from nes_py.wrappers import JoypadSpace
from gym_super_mario_bros.actions import SIMPLE_MOVEMENT, COMPLEX_MOVEMENT, RIGHT_ONLY
import cv2
import numpy as np
import subprocess as sp
from gym_super_mario_bros import SuperMarioBrosRandomStagesEnv

class Monitor:
    def __init__(self, width, height, saved_path):

        self.command = ["ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-s", "{}X{}".format(width, height),
                        "-pix_fmt", "rgb24", "-r", "80", "-i", "-", "-an", "-vcodec", "mpeg4", saved_path]
        try:
            self.pipe = sp.Popen(self.command, stdin=sp.PIPE, stderr=sp.PIPE)
        except FileNotFoundError:
            pass

    def record(self, image_array):
        self.pipe.stdin.write(image_array.tostring())


def process_frame(frame):
    if frame is not None:
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        frame = cv2.resize(frame, (84, 84))[None, :, :] / 255.
        return frame
    else:
        return np.zeros((1, 84, 84))

class CustomReward(Wrapper):
    def __init__(self, env=None, monitor=None):
        super(CustomReward, self).__init__(env)
        self.observation_space = Box(low=0, high=255, shape=(1, 84, 84))
        self.curr_score = 0
        self.max_x_pos = 0
        self.max_x_pos_counter = 0
        self.rand_counter = 0
        if monitor:
            self.monitor = monitor
        else:
            self.monitor = None

    def step(self, action):
        done = False
        if self.rand_counter > 25: #mario is stuck
            for x in range(0, 2):
                state, reward, done, info = self.env.step(self.env.action_space.sample())
                if done:
                    break
            self.rand_counter = 0
        if done == False:
            state, reward, done, info = self.env.step(action)
        if self.monitor:
            self.monitor.record(state)
        state = process_frame(state)
        reward += (info["score"] - self.curr_score) / 40.
        self.curr_score = info["score"]
        if done:
            self.max_x_pos = 0
            self.max_x_pos_counter = 0
            self.rand_counter = 0
            if info["flag_get"]:
                reward += 50
            else:
                reward -= 50
        if info['x_pos'] > self.max_x_pos:
            self.max_x_pos = info['x_pos']
            self.max_x_pos_counter = 0
            self.rand_counter = 0
        else:
            self. max_x_pos_counter += 1
            if self.max_x_pos_counter > 50:
                reward -= 1
                self.rand_counter += 1
        return state, reward / 10., done, info

    def reset(self):
        self.curr_score = 0
        self.max_x_pos_counter = 0
        self.rand_counter = 0
        self.max_x_pos = 0
        return process_frame(super().reset())

class CustomSuperMarioBrosRandomStagesEnv(SuperMarioBrosRandomStagesEnv):
    def __init__(self, env, rom_mode='vanilla'):
        self.stage = 0
        self.world = 0
        super(CustomSuperMarioBrosRandomStagesEnv, self).__init__(rom_mode)

    def _select_random_level(self):
        """Select a random level to use."""
        self.world = 4 - 1
        self.stage = 4 - 1
        while( (self.world == (4 - 1) and self.stage == (4 - 1)) or (self.world == (7 - 1) and self.stage == (4 - 1)) ):
            self.world = self.np_random.randint(1, 9) - 1
            self.stage = self.np_random.randint(1, 5) - 1
        print('selecting level:',self.world + 1,self.stage + 1)
        self.env = self.envs[self.world][self.stage]

    def _select_next_level(self):
        """Select the next level to use."""
        self.stage += 1
        if self.stage > 3:
            self.stage = 0
            self.world += 1
        if self.world > 7:
            self.stage = 0
            self.world = 0
        print(self.world, self.stage)
        print('selecting level:',self.world + 1,self.stage + 1)
        self.env = self.envs[self.world][self.stage]

    def reset(self):
        """
        Reset the state of the environment and returns an initial observation.
        Returns:
            state (np.ndarray): next frame as a result of the given action
        """
        # select a new level
        #self._select_random_level()
        self._select_next_level()
        # reset the environment
        return self.env.reset()
        
class CustomSkipFrame(Wrapper):
    def __init__(self, env, skip=4):
        super(CustomSkipFrame, self).__init__(env)
        self.observation_space = Box(low=0, high=255, shape=(4, 84, 84))
        self.skip = skip

    def step(self, action):
        total_reward = 0
        states = []
        state, reward, done, info = self.env.step(action)
        #self.env.render()
        for i in range(self.skip):
            if not done:
                state, reward, done, info = self.env.step(action)
                total_reward += reward
                states.append(state)
            else:
                states.append(state)
        states = np.concatenate(states, 0)[None, :, :, :]
        return states.astype(np.float32), reward, done, info

    def reset(self):
        state = super().reset()
        states = np.concatenate([state for _ in range(self.skip)], 0)[None, :, :, :]
        return states.astype(np.float32)

       
def create_train_env(world, stage, action_type, output_path=None):
    #env = gym_super_mario_bros.make("SuperMarioBrosRandomStages-v0")
    env = gym_super_mario_bros.make("SuperMarioBros-{}-{}-v0".format(world, stage))
    env = CustomSuperMarioBrosRandomStagesEnv(env)
    if output_path:
        monitor = Monitor(256, 240, output_path)
    else:
        monitor = None
    if action_type == "right":
        actions = RIGHT_ONLY
    elif action_type == "simple":
        actions = SIMPLE_MOVEMENT
    else:
        actions = COMPLEX_MOVEMENT
    env = JoypadSpace(env, actions)
    env = CustomReward(env, monitor)
    env = CustomSkipFrame(env)
    return env, env.observation_space.shape[0], len(actions)
