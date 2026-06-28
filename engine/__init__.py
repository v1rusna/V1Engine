__version__ = 0.1
__version__ = "v1 consol engine"

from engine.core.fps_controller import FPSController
from engine.core.console_input import ConsoleInput
from engine.core.console_renderer import ConsoleRenderer, Color

def create_renderer(width: int = 120, height: int = 30) -> ConsoleRenderer:
    return ConsoleRenderer(width=width, height=height)

def create_keyboard(esc_timeout: float = 0.02) -> ConsoleInput:
    return ConsoleInput(esc_timeout)

def create_clock(target_fps: int = 30, precise: bool = True) -> FPSController:
    return FPSController(target_fps, precise=precise)

