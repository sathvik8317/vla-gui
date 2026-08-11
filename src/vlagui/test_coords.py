import pytest

from vlagui.coords import image_to_model, image_to_screen, model_to_image, screen_to_image

WIDTH, HEIGHT = 1280, 800


@pytest.mark.parametrize("x,y", [(0, 0), (640, 400), (1279, 799), (100.5, 250.25)])
def test_image_screen_round_trip(x: float, y: float) -> None:
    sx, sy = image_to_screen(x, y)
    ix, iy = screen_to_image(sx, sy)
    assert (ix, iy) == pytest.approx((x, y))


@pytest.mark.parametrize("x,y", [(0, 0), (640, 400), (1279, 799), (100.5, 250.25)])
def test_image_model_round_trip(x: float, y: float) -> None:
    mx, my = image_to_model(x, y, WIDTH, HEIGHT)
    ix, iy = model_to_image(mx, my, WIDTH, HEIGHT)
    assert (ix, iy) == pytest.approx((x, y))
