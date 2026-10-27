"""Shared activity supply-shop recognition; never produces a click target.

Recognize a repeated two-column offer grid, then read only its button labels.
Offer order, button coordinates, price and the number of bought bundles vary.
"""
from dataclasses import dataclass
import re
import time

import cv2
import numpy as np


@dataclass(frozen=True)
class ShopButton:
    color: str
    bounds: tuple


@dataclass(frozen=True)
class ShopLayout:
    buttons: tuple
    rows: int


def supply_layout(game, hsv=None):
    """Cheap visual gate. Colors alone are not a confirmed purchase page."""
    h, w = game.shape[:2]
    if hsv is None:
        hsv = cv2.cvtColor(game, cv2.COLOR_BGR2HSV)
    buttons = []
    for color, lo, hi in (('yellow', (15, 100, 100), (34, 255, 255)),
                          ('green', (35, 100, 80), (85, 255, 255))):
        mask = cv2.inRange(hsv, lo, hi)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        for x, y, bw, bh, area in stats[1:]:
            if (w*.25 <= bw <= w*.49 and h*.025 <= bh <= h*.10
                    and 2.2 <= bw/bh <= 6.5 and area > bw*bh*.45):
                buttons.append(ShopButton(color, tuple(map(int, (x, y, bw, bh)))))
    if not 4 <= len(buttons) <= 8:
        return None
    centers = [(b.bounds[0]+b.bounds[2]/2, b.bounds[1]+b.bounds[3]/2) for b in buttons]
    left, right = min(x for x, _ in centers), max(x for x, _ in centers)
    if right-left < w*.28:
        return None
    columns = [[], []]
    for button, (x, y) in zip(buttons, centers):
        column = 0 if abs(x-left) < abs(x-right) else 1
        if abs(x-(left if column == 0 else right)) > w*.075:
            return None
        columns[column].append((y, button))
    if min(map(len, columns)) < 2:
        return None
    height = float(np.median([b.bounds[3] for b in buttons]))
    rows = []
    for y, button in sorted((item for column in columns for item in column), key=lambda item: item[0]):
        if not rows or y-rows[-1][0][0] > height*.6:
            rows.append([])
        rows[-1].append((y, button))
    if (not 2 <= len(rows) <= 4 or any(len(row) > 2 for row in rows)
            or sum(len(row) == 2 for row in rows) < 2
            or rows[-1][0][0]-rows[0][0][0] < h*.16
            or any(b[0][0]-a[0][0] < height*1.5 for a, b in zip(rows, rows[1:]))):
        return None
    ordered = tuple(button for row in rows for _, button in sorted(row, key=lambda item: item[1].bounds[0]))
    return ShopLayout(ordered, len(rows))


def supply_shop(game, layout, read_text):
    """A price must include a currency mark; unrelated reward numbers do not count."""
    priced = free = 0
    for button in layout.buttons:
        x, y, bw, bh = button.bounds
        # Ignore lock ornaments at the right edge; labels remain inside the face.
        roi = game[y+round(bh*.12):y+round(bh*.93), x+round(bw*.12):x+round(bw*.85)]
        label = re.sub(r'\s+', '', read_text(roi))
        if button.color == 'yellow' and re.search(r'(?:[¥￥]|人民币|RMB)\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?元', label, re.I):
            priced += 1
        if button.color == 'green' and label == '免费':
            free += 1
    if priced and free:
        return True
    # After buying offers, every remaining button may be free (or all paid).
    # Require the bundle title as extra evidence in these uniform-color cases.
    colors = {b.color for b in layout.buttons}
    if ((colors == {'green'} and free >= 4) or (colors == {'yellow'} and priced >= 4)) and '礼包' in re.sub(r'\s+', '', read_text(game[:max(1, min(b.bounds[1] for b in layout.buttons))])):
        return True
    return False


def supply_signature(game, layout):
    signatures = []
    for button in layout.buttons:
        x, y, bw, bh = button.bounds
        roi = game[y+round(bh*.12):y+round(bh*.93), x+round(bw*.12):x+round(bw*.85)]
        signatures.append(cv2.resize(roi, (48, 20), interpolation=cv2.INTER_AREA))
    return np.concatenate(signatures)


class SupplyShopReader:
    """Reuse OCR only while the grid and current label pixels still match.

    A synchronous first read can outlive an input frame. The following fresh
    frame can then safely stop without repeatedly blocking on the same OCR.
    """
    def __init__(self):
        self.layout = self.signature = self.confirmed = None
        self.read_at = -100.

    def recognize(self, game, layout, read_text):
        if layout is None:
            self.layout = self.signature = self.confirmed = None
            return None
        signatures = [supply_signature(game, layout)]
        # Include the title: uniform-color recognition depends on its meaning.
        signatures.append(cv2.resize(game[:max(1, min(b.bounds[1] for b in layout.buttons))], (48, 20), interpolation=cv2.INTER_AREA))
        signature = np.concatenate(signatures)
        if (self.layout == layout and self.signature is not None
                and cv2.absdiff(signature, self.signature).mean() < 1.2
                and (self.confirmed or time.monotonic()-self.read_at < 2)):
            return self.confirmed
        confirmed = supply_shop(game, layout, read_text)
        self.layout, self.signature, self.confirmed = layout, signature, confirmed
        self.read_at = time.monotonic()
        return confirmed
