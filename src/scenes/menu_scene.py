import pygame as pg
import math
import random
from src.utils import GameSettings
from src.sprites import BackgroundSprite
from src.scenes.scene import Scene
from src.interface.components import Button
from src.core.services import scene_manager, sound_manager, input_manager
from typing import override

class MenuScene(Scene):
    background: BackgroundSprite
    play_button: Button
    settings_button: Button
    
    def __init__(self):
        super().__init__()
        # 1. 背景圖
        self.background = BackgroundSprite("backgrounds/background1.png")

        # 2. 按鈕 (整體往下移 50px)
        # 原本是 height * 3 // 4，現在多加 50
        px = GameSettings.SCREEN_WIDTH // 2
        py = (GameSettings.SCREEN_HEIGHT * 3 // 4) + 50 
        
        self.play_button = Button(
            "UI/button_play.png", "UI/button_play_hover.png",
            px + 50, py-100, 100, 100,
            lambda: scene_manager.change_scene("game")
        )
        
        self.settings_button = Button(
            img_path="UI/button_setting.png",
            img_hovered_path="UI/button_setting_hover.png",
            x=GameSettings.SCREEN_WIDTH // 2 - 100,
            y=py-100, # 跟上面一樣的高度
            width=100,
            height=100,
            on_click=lambda: scene_manager.change_scene("setting")
        )

        # 3. 樹葉特效
        self.timer = 0
        self.leaves = []
        for _ in range(25):
            self.leaves.append(self._create_leaf())

    def _create_leaf(self):
        colors = [(34, 139, 34), (50, 205, 50), (107, 142, 35), (144, 238, 144)]
        return {
            "x": random.randint(0, GameSettings.SCREEN_WIDTH + 100),
            "y": random.randint(-100, GameSettings.SCREEN_HEIGHT),
            "speed_x": random.uniform(-2.0, -0.5),
            "speed_y": random.uniform(0.5, 1.5),
            "size": random.randint(4, 8),
            "color": random.choice(colors),
            "angle": random.uniform(0, 360),
            "spin_speed": random.uniform(1, 3)
        }
        
    @override
    def enter(self) -> None:
        sound_manager.play_bgm("RBY 101 Opening (Part 1).ogg")

    @override
    def exit(self) -> None:
        pass

    @override
    def update(self, dt: float) -> None:
        self.timer += dt

        if input_manager.key_pressed(pg.K_SPACE):
            scene_manager.change_scene("game")
            return
            
        self.play_button.update(dt)
        self.settings_button.update(dt)

        for leaf in self.leaves:
            leaf["x"] += leaf["speed_x"]
            leaf["y"] += leaf["speed_y"]
            leaf["angle"] += leaf["spin_speed"]
            leaf["x"] += math.sin(self.timer * 2 + leaf["y"] * 0.05) * 0.2
            if leaf["x"] < -20 or leaf["y"] > GameSettings.SCREEN_HEIGHT + 20:
                leaf["x"] = random.randint(GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_WIDTH + 200)
                leaf["y"] = random.randint(-100, 0)

    @override
    def draw(self, screen: pg.Surface) -> None:
        # 1. 畫背景
        self.background.draw(screen)

        # 2. 畫樹葉
        for leaf in self.leaves:
            surf = pg.Surface((leaf["size"]*2, leaf["size"]*2), pg.SRCALPHA)
            center = leaf["size"]
            points = [(center, 0), (center + leaf["size"]//2, center), (center, leaf["size"]*2), (center - leaf["size"]//2, center)]
            pg.draw.polygon(surf, leaf["color"], points)
            rotated_surf = pg.transform.rotate(surf, leaf["angle"])
            rect = rotated_surf.get_rect(center=(leaf["x"], leaf["y"]))
            screen.blit(rotated_surf, rect)

        # 3. 繪製木板標題 (Wood Panel Title)
        
        # (A) 準備文字 [顏色修改點]
        title_font = pg.font.SysFont("Arial", 80, bold=True)
        text_surf = title_font.render("POKEGAME", True, (255, 140, 0)) # [改] 橘黃色
        text_shadow = title_font.render("POKEGAME", True, (60, 30, 0))  # 深色陰影
        
        # (B) 計算位置 [位置修改點]
        panel_w = text_surf.get_width() + 100
        panel_h = text_surf.get_height() + 60
        center_x = GameSettings.SCREEN_WIDTH // 2
        center_y = 350 # [改] 從 300 下移到 350
        
        panel_rect = pg.Rect(0, 0, panel_w, panel_h)
        panel_rect.center = (center_x, center_y)

        # (C) 畫木板
        pg.draw.rect(screen, (139, 69, 19), panel_rect, border_radius=15) # 底
        pg.draw.rect(screen, (160, 82, 45), panel_rect.inflate(-10, -10), 3, border_radius=15) # 內框
        pg.draw.rect(screen, (60, 30, 0), panel_rect, 6, border_radius=15) # 外框

        # (D) 畫釘子
        nail_color = (192, 192, 192)
        nail_offset = 15
        nails = [
            (panel_rect.left + nail_offset, panel_rect.top + nail_offset),
            (panel_rect.right - nail_offset, panel_rect.top + nail_offset),
            (panel_rect.left + nail_offset, panel_rect.bottom - nail_offset),
            (panel_rect.right - nail_offset, panel_rect.bottom - nail_offset)
        ]
        for nail in nails:
            pg.draw.circle(screen, (50, 50, 50), (nail[0]+2, nail[1]+2), 6)
            pg.draw.circle(screen, nail_color, nail, 6)

        # (E) 畫文字
        shadow_rect = text_shadow.get_rect(center=(center_x + 4, center_y + 4))
        screen.blit(text_shadow, shadow_rect)
        
        text_rect = text_surf.get_rect(center=(center_x, center_y))
        screen.blit(text_surf, text_rect)

        # 4. 畫按鈕
        self.play_button.draw(screen)
        self.settings_button.draw(screen)