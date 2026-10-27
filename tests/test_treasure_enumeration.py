"""Independent small-board enumeration checks layout multiplicity and constraints."""
from collections import Counter
from itertools import combinations, product
import random
import unittest

from treasure.solver import solve


def reference_layouts(n, shapes, cells):
    groups = Counter()
    for width, height, count in shapes:
        groups[tuple(sorted((width, height)))] += count
    candidates = []
    for (width, height), count in groups.items():
        rectangles = []
        for w, h in sorted({(width, height), (height, width)}):
            for y in range(n - h + 1):
                for x in range(n - w + 1):
                    rectangles.append(frozenset((x + dx, y + dy)
                                                for dx in range(w) for dy in range(h)))
        candidates.append(list(combinations(rectangles, count)))
    empty = {(i % n, i // n) for i, value in enumerate(cells) if value == 1}
    hits = {(i % n, i // n) for i, value in enumerate(cells) if value == 2}
    layouts = []
    for chosen in product(*candidates):
        rectangles = [rectangle for group in chosen for rectangle in group]
        occupied = frozenset().union(*rectangles)
        if len(occupied) != sum(map(len, rectangles)) or occupied & empty or not hits <= occupied:
            continue
        layouts.append(sum(1 << (y * n + x) for x, y in occupied))
    return layouts


class EnumerationTests(unittest.TestCase):
    def test_solver_matches_independent_placement_enumeration(self):
        rng = random.Random(20261014)
        cases = [(2, [(1, 1, 2)]), (2, [(1, 2, 2)]),
                 (2, [(1, 2, 1), (1, 1, 1)]),
                 (3, [(1, 2, 2)]), (3, [(2, 2, 1), (1, 1, 2)]),
                 (3, [(1, 2, 1), (2, 1, 1)])]
        for n, shapes in cases:
            boards = list(product(range(3), repeat=4)) if n == 2 else [
                [0] * 9, *[[rng.randrange(3) for _ in range(9)] for _ in range(40)]]
            for cells in boards:
                with self.subTest(n=n, shapes=shapes, cells=cells):
                    expected = reference_layouts(n, shapes, cells)
                    actual = solve(n, shapes, cells)
                    self.assertTrue(actual['exact'])
                    self.assertEqual(Counter(actual['masks']), Counter(expected))
                    probabilities = [sum(bool(m & (1 << i)) for m in expected) / len(expected)
                                     if expected else None for i in range(n * n)]
                    self.assertEqual(actual['probabilities'], probabilities)
