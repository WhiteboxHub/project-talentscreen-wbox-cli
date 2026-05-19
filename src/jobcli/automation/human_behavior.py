"""Human-like behavioral overrides for Playwright interactions.

This module provides realistic mouse movements using bezier curves and
realistic typing delays to evade advanced behavioral bot detection.
"""

import math
import random
import time
from typing import List, Tuple

from playwright.sync_api import Page, Locator


class HumanBehavior:
    """Helper class to inject human-like behavior into Playwright."""

    @staticmethod
    def _generate_bezier_curve(
        start: Tuple[float, float],
        end: Tuple[float, float],
        control1: Tuple[float, float],
        control2: Tuple[float, float],
        steps: int
    ) -> List[Tuple[float, float]]:
        """Generate points along a cubic Bezier curve."""
        points = []
        for i in range(steps + 1):
            t = i / steps
            x = (
                (1 - t)**3 * start[0] +
                3 * (1 - t)**2 * t * control1[0] +
                3 * (1 - t) * t**2 * control2[0] +
                t**3 * end[0]
            )
            y = (
                (1 - t)**3 * start[1] +
                3 * (1 - t)**2 * t * control1[1] +
                3 * (1 - t) * t**2 * control2[1] +
                t**3 * end[1]
            )
            points.append((x, y))
        return points

    @staticmethod
    def move_mouse_humanly(page: Page, target_x: float, target_y: float) -> None:
        """Move the mouse to coordinates using a realistic bezier curve."""
        try:
            # Playwright doesn't expose current mouse position directly, so we assume
            # starting from middle of viewport or previous position
            start_x = random.randint(100, 500)
            start_y = random.randint(100, 500)

            # Randomize control points to create an arc
            dist_x = target_x - start_x
            dist_y = target_y - start_y
            
            ctrl1_x = start_x + (dist_x * random.uniform(0.1, 0.4)) + random.uniform(-50, 50)
            ctrl1_y = start_y + (dist_y * random.uniform(0.1, 0.4)) + random.uniform(-50, 50)
            
            ctrl2_x = start_x + (dist_x * random.uniform(0.6, 0.9)) + random.uniform(-50, 50)
            ctrl2_y = start_y + (dist_y * random.uniform(0.6, 0.9)) + random.uniform(-50, 50)

            steps = random.randint(15, 30)
            points = HumanBehavior._generate_bezier_curve(
                (start_x, start_y),
                (target_x, target_y),
                (ctrl1_x, ctrl1_y),
                (ctrl2_x, ctrl2_y),
                steps
            )

            # Follow the curve with slightly variable speed
            for px, py in points:
                page.mouse.move(px, py)
                time.sleep(random.uniform(0.005, 0.015))
                
        except Exception:
            # Fallback to direct move if calculation fails
            page.mouse.move(target_x, target_y)

    @staticmethod
    def click(page: Page, locator: Locator) -> None:
        """Click a locator with human-like mouse movement and slight delays."""
        try:
            # Get element bounding box
            box = locator.bounding_box(timeout=2000)
            if box:
                # Target a random point slightly off-center
                target_x = box["x"] + (box["width"] / 2) + random.uniform(-box["width"]/4, box["width"]/4)
                target_y = box["y"] + (box["height"] / 2) + random.uniform(-box["height"]/4, box["height"]/4)
                
                HumanBehavior.move_mouse_humanly(page, target_x, target_y)
                time.sleep(random.uniform(0.05, 0.2)) # Pause before clicking
            
            # Click
            locator.click(delay=random.randint(30, 100))
        except Exception:
            # Fallback to standard click
            locator.click()

    @staticmethod
    def type(locator: Locator, text: str) -> None:
        """Type text with realistic, randomized delays between keystrokes."""
        try:
            # Clear field first
            locator.fill("")
            time.sleep(random.uniform(0.05, 0.15))
            
            # Type with delay
            # Normal human typing is ~60 WPM, which is ~300 CPM.
            # That's roughly 200ms per character on average, with variation.
            locator.type(text, delay=random.randint(50, 150))
            
            # Occasional "typo and backspace" behavior could be added here for ultra-stealth
        except Exception:
            # Fallback
            locator.fill(text)
