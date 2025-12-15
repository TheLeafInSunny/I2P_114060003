# src/scenes/catch_scene.py
#tode:要放進bag 隨機出現
import pygame as pg
from typing import override

from src.scenes.scene import Scene
from src.utils import GameSettings
from src.interface.components.button import Button
from src.core.services import scene_manager
from src.core import GameManager   # 用來 load / save


class CatchScene(Scene):
    """
    很簡單的「抓寶」場景：
      - 顯示一隻野生寶可夢
      - 有 Catch / Run 兩個按鈕
      - 抓到就加到 bag.monsters，然後存檔，再按 SPACE 回到 game
    """

    def __init__(self) -> None:
        super().__init__()

        # 這隻是「這場戰鬥要抓的野生寶可夢」
        # 之後你可以改成隨機或依地圖決定
        self.wild_mon: dict[str, object] = {
            "name": "Wild Eevee",
            "hp": 40,
            "max_hp": 40,
            "level": 5,
            "sprite_path": "menu_sprites/menusprite1.png",  # 只是為了跟資料型別一致
        }

        self.game_manager: GameManager | None = None
        self.caught: bool = False   # 有沒有抓到
        self.state: str = "CHOICE"  # CHOICE / CAUGHT / RUN

        self.font = pg.font.SysFont(None, 30)

        # Catch 按鈕
        self.btn_catch = Button(
            img_path="UI/button_play.png",
            img_hovered_path="UI/button_play_hover.png",
            x=100,
            y=GameSettings.SCREEN_HEIGHT - 120,
            width=160,
            height=60,
            on_click=self.on_catch,
        )

        # Run 按鈕
        self.btn_run = Button(
            img_path="UI/button_x.png",
            img_hovered_path="UI/button_x_hover.png",
            x=300,
            y=GameSettings.SCREEN_HEIGHT - 120,
            width=160,
            height=60,
            on_click=self.on_run,
        )

    @override
    def enter(self) -> None:
        """
        每次進入抓寶場景時：
          1. 重新 load 存檔（拿到最新的 bag）
          2. 重設狀態
        """
        self.game_manager = GameManager.load("saves/game0.json")
        self.caught = False
        self.state = "CHOICE"

    # ========== 按鈕事件 ==========

    def on_catch(self) -> None:
        if self.state != "CHOICE":
            return

        self.caught = True
        self.state = "CAUGHT"

        # 把這隻 wild_mon 加進背包
        if self.game_manager is not None:
            bag = self.game_manager.bag

            # 注意：bag._monsters_data 裡預期是 TypedDict[Monster] 型態
            bag._monsters_data.append(self.wild_mon.copy())

            # 存檔
            self.game_manager.save("saves/game0.json")

    def on_run(self) -> None:
        if self.state != "CHOICE":
            return
        self.caught = False
        self.state = "RUN"

    # ========== Update / Draw ==========

    @override
    def update(self, dt: float) -> None:
        if self.state == "CHOICE":
            self.btn_catch.update(dt)
            self.btn_run.update(dt)
        else:
            # CAUGHT / RUN 狀態：按 SPACE 回到遊戲
            keys = pg.key.get_pressed()
            if keys[pg.K_SPACE]:
                scene_manager.change_scene("game")

    @override
    def draw(self, screen: pg.Surface) -> None:
        screen.fill((200, 240, 255))

        # 顯示野生寶可夢資訊
        self.draw_mon_info(screen, 80, 80, self.wild_mon)

        # 狀態訊息
        if self.state == "CHOICE":
            msg = "A wild Pokemon appeared! Choose: Catch or Run."
        elif self.state == "CAUGHT":
            msg = "You caught it! Press SPACE to go back."
        else:  # RUN
            msg = "You ran away... Press SPACE to go back."

        text = self.font.render(msg, True, (0, 0, 0))
        screen.blit(text, (80, 40))

        # 只有在選擇階段顯示按鈕
        if self.state == "CHOICE":
            self.btn_catch.draw(screen)
            self.btn_run.draw(screen)

    def draw_mon_info(self, screen: pg.Surface, x: int, y: int, mon: dict[str, object]) -> None:
        name = str(mon.get("name", "Unknown"))
        hp = int(mon.get("hp", 0))
        maxhp = int(mon.get("max_hp", 0))
        level = int(mon.get("level", 1))

        screen.blit(self.font.render(f"{name} Lv.{level}", True, (0, 0, 0)), (x, y))
        screen.blit(self.font.render(f"HP: {hp}/{maxhp}", True, (0, 0, 0)), (x, y + 30))
