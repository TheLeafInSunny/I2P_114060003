'''
[TODO HACKATHON 5]
Try to mimic the menu_scene.py or game_scene.py to create this new scene
'''
import pygame as pg
from typing import override

from src.scenes.scene import Scene
from src.utils import GameSettings
from src.core.services import scene_manager, sound_manager, input_manager
from src.interface.components.button import Button

# ========= 簡易 Checkbox =========
class Checkbox:
    def __init__(self, x: int, y: int, text: str, checked: bool = False, on_change=None):
        self.x = x
        self.y = y
        self.size = 24
        self.rect = pg.Rect(x, y, self.size, self.size)
        self.checked = checked
        self.on_change = on_change

        self.font = pg.font.SysFont(None, 24)
        self.label_surface = self.font.render(text, True, (255, 255, 255))

    def update(self, dt: float) -> None:
        if input_manager.mouse_pressed(1) and self.rect.collidepoint(input_manager.mouse_pos):
            self.checked = not self.checked
            if self.on_change is not None:
                self.on_change(self.checked)

    def draw(self, screen: pg.Surface) -> None:
        # 外框
        pg.draw.rect(screen, (255, 255, 255), self.rect, 2)
        # 內部打勾（用白色填滿）
        if self.checked:
            inner = self.rect.inflate(-6, -6)
            pg.draw.rect(screen, (255, 255, 255), inner)

        # 文字
        screen.blit(self.label_surface, (self.x + self.size + 8, self.y))


# ========= 簡易 Slider =========
class Slider:
    def __init__(self, x: int, y: int, width: int,
                 min_value: float, max_value: float, value: float,
                 on_change=None):
        self.x = x
        self.y = y
        self.width = width
        self.min_value = min_value
        self.max_value = max_value
        self.value = value
        self.on_change = on_change

        self.rect = pg.Rect(x, y - 8, width, 16)

    def _value_to_x(self) -> int:
        # value 映射到 [x, x+width]
        t = (self.value - self.min_value) / (self.max_value - self.min_value)
        return int(self.x + t * self.width)

    def _x_to_value(self, px: int) -> float:
        # 滑鼠 x 轉成 value
        t = (px - self.x) / self.width
        t = max(0.0, min(1.0, t))
        return self.min_value + t * (self.max_value - self.min_value)

    def update(self, dt: float) -> None:
        if input_manager.mouse_pressed(1) and self.rect.collidepoint(input_manager.mouse_pos):
            new_value = self._x_to_value(input_manager.mouse_pos[0])
            self.value = new_value
            if self.on_change is not None:
                self.on_change(self.value)

    def draw(self, screen: pg.Surface) -> None:
        center_y = self.y
        # 底線
        pg.draw.line(screen, (200, 200, 200), (self.x, center_y), (self.x + self.width, center_y), 4)
        # 滑塊
        knob_x = self._value_to_x()
        knob_rect = pg.Rect(0, 0, 14, 24)
        knob_rect.center = (knob_x, center_y)
        pg.draw.rect(screen, (255, 255, 255), knob_rect)
        # 顯示百分比
        font = pg.font.SysFont(None, 20)
        txt = font.render(f"{int(self.value * 100)}%", True, (255, 255, 255))
        screen.blit(txt, (self.x + self.width + 10, center_y - 10))


class SettingScene(Scene):
    def __init__(self):
        super().__init__()

        # 🔊 從 SoundManager 讀目前音量（0~1）
        initial_volume = getattr(sound_manager, "bgm_volume", GameSettings.AUDIO_VOLUME)

        self.muted = (initial_volume == 0.0)
        self.volume = initial_volume if not self.muted else 0.5  # 靜音時 UI 用 0.5 當顯示

        # 回主選單按鈕
        self.button_back = Button(
            img_path="UI/button_back.png",
            img_hovered_path="UI/button_back_hover.png",
            x=GameSettings.SCREEN_WIDTH // 2 - 50,
            y=GameSettings.SCREEN_HEIGHT // 2 + 80,
            width=100,
            height=100,
            on_click=lambda: scene_manager.change_scene("menu")
        )

        # Mute Checkbox
        self.checkbox_mute = Checkbox(
            x=100,
            y=150,
            text="Mute BGM",
            checked=self.muted,
            on_change=self.on_mute_changed
        )

        # Volume Slider（0~1）
        self.slider_volume = Slider(
            x=100,
            y=220,
            width=300,
            min_value=0.0,
            max_value=1.0,
            value=self.volume,
            on_change=self.on_volume_changed
        )

    # 勾選 / 取消靜音
    def on_mute_changed(self, checked: bool) -> None:
        self.muted = checked
        if self.muted:
            # 靜音：設成 0
            sound_manager.set_bgm_volume(0.0)
        else:
            # 取消靜音：用目前 slider 的值
            sound_manager.set_bgm_volume(self.volume)

    # Slider 改變音量
    def on_volume_changed(self, value: float) -> None:
        self.volume = value
        # 如果沒靜音，就直接套用到 SoundManager
        if not self.muted:
            sound_manager.set_bgm_volume(self.volume)

    @override
    def update(self, dt: float) -> None:
        self.button_back.update(dt)
        self.checkbox_mute.update(dt)
        self.slider_volume.update(dt)

    @override
    def draw(self, screen: pg.Surface) -> None:
        # 你可以加背景顏色或圖片，這裡先空白
        screen.fill((30, 30, 60))

        self.checkbox_mute.draw(screen)
        self.slider_volume.draw(screen)
        self.button_back.draw(screen)
