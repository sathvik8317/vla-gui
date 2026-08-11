"""Every image<->screen<->model-space coordinate transform. No inline pixel arithmetic elsewhere.

Viewport is pinned with device_scale_factor=1 (see config.py), so screenshot
image pixels equal screen (CSS) pixels — image<->screen is identity, but it
stays an explicit transform here rather than being assumed inline at call sites.
Model-space is the VLM's normalized [0, scale] coordinate space (scale=1000
matches Qwen-VL-style grounding output).
"""

Point = tuple[float, float]


def image_to_screen(x: float, y: float) -> Point:
    return x, y


def screen_to_image(x: float, y: float) -> Point:
    return x, y


def screen_to_model(x: float, y: float, width: int, height: int, scale: int = 1000) -> Point:
    return x / width * scale, y / height * scale


def model_to_screen(mx: float, my: float, width: int, height: int, scale: int = 1000) -> Point:
    return mx / scale * width, my / scale * height


def image_to_model(x: float, y: float, width: int, height: int, scale: int = 1000) -> Point:
    return screen_to_model(*image_to_screen(x, y), width, height, scale)


def model_to_image(mx: float, my: float, width: int, height: int, scale: int = 1000) -> Point:
    return screen_to_image(*model_to_screen(mx, my, width, height, scale))
