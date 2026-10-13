"""Procedural ambience for title cards, chapter breaths and the end card:
warm dust drifting through candlelight, over a dimmed archive image when one is given."""
import cv2
import numpy as np


class DustField:
    def __init__(self, W, H, seed=1, n=520, speed=1.0):
        rng = np.random.default_rng(seed)
        self.W, self.H = W, H
        self.w, self.h = W // 2, H // 2
        self.n = n
        self.x0 = rng.uniform(0, 1, n)
        self.y0 = rng.uniform(0, 1, n)
        self.depth = rng.power(2.2, n)                       # 0 far .. 1 near
        self.vx = rng.normal(0, 0.004, n) * speed
        self.vy = -(0.004 + 0.012 * self.depth) * speed      # rising slowly, near ones faster
        self.phase = rng.uniform(0, 6.28, n)
        self.flicker = rng.uniform(0.15, 0.6, n)
        warm = np.array([[255, 214, 160], [255, 196, 128], [250, 232, 200]], np.float32)
        self.color = warm[rng.integers(0, 3, n)] / 255.0
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        cx, cy = self.w * rng.uniform(0.35, 0.65), self.h * 0.62
        r = np.sqrt(((xx - cx) / self.w) ** 2 + ((yy - cy) / self.h) ** 2)
        glow = np.clip(1 - r * 1.25, 0, 1) ** 2.2
        self.base = (glow[..., None] * np.array([46, 30, 16], np.float32)
                     + np.array([10, 9, 8], np.float32))

    def render(self, t, base=None):
        img = self.base.copy() if base is None else base * 0.5 + self.base * 0.6
        layer_far = np.zeros((self.h, self.w, 3), np.float32)
        layer_near = np.zeros((self.h, self.w, 3), np.float32)
        x = ((self.x0 + self.vx * t + 0.01 * np.sin(t * 0.3 + self.phase)) % 1.0) * self.w
        y = ((self.y0 + self.vy * t) % 1.0) * self.h
        b = (0.55 + self.flicker * np.sin(t * 1.3 + self.phase)) * (0.35 + 0.65 * self.depth)
        xi = np.clip(x.astype(int), 0, self.w - 1)
        yi = np.clip(y.astype(int), 0, self.h - 1)
        val = self.color * (255 * b)[:, None]
        near = self.depth > 0.7
        np.add.at(layer_far, (yi[~near], xi[~near]), val[~near] * 3.0)
        np.add.at(layer_near, (yi[near], xi[near]), val[near] * 40.0)
        img += cv2.GaussianBlur(layer_far, (0, 0), 1.1) * 0.9
        img += cv2.GaussianBlur(layer_near, (0, 0), 4.5) * 0.8
        img = np.clip(img, 0, 255).astype(np.uint8)
        return cv2.resize(img, (self.W, self.H), interpolation=cv2.INTER_LINEAR)
