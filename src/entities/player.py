from __future__ import annotations
import pygame as pg
import math
from typing import override

from .entity import Entity
from src.core.services import input_manager
from src.utils import Position, PositionCamera, GameSettings, Logger, Direction
from src.core import GameManager

class Player(Entity):
    speed: float = 4.0 * GameSettings.TILE_SIZE
    game_manager: GameManager

    def __init__(self, x: float, y: float, game_manager: GameManager) -> None:
        super().__init__(x, y, game_manager)
        self.path = [] # [mine] 儲存導航路徑

    @override
    def update(self, dt: float) -> None:
        dis = Position(0, 0)
        
        # 1. 接收鍵盤輸入
        if input_manager.key_down(pg.K_LEFT) or input_manager.key_down(pg.K_a):
            dis.x -= 1
        if input_manager.key_down(pg.K_RIGHT) or input_manager.key_down(pg.K_d):
            dis.x += 1
        if input_manager.key_down(pg.K_UP) or input_manager.key_down(pg.K_w):
            dis.y -= 1
        if input_manager.key_down(pg.K_DOWN) or input_manager.key_down(pg.K_s):
            dis.y += 1
            
        # [Modified] GPS 導航邏輯
        # 邏輯修正：不再因為按鍵而取消路徑，只在「到達」時移除點
        if self.path:
            # 1. 檢查是否到達「最終終點」 (優先判定)
            dest = self.path[-1]
            # 取玩家中心點來計算距離，比較精準
            cx = self.position.x + GameSettings.TILE_SIZE // 2
            cy = self.position.y + GameSettings.TILE_SIZE // 2
            dist_to_dest = math.sqrt((dest.x - cx)**2 + (dest.y - cy)**2)
            
            # 如果距離終點小於半格 (32px)，視為到達，清空路徑
            if dist_to_dest < GameSettings.TILE_SIZE / 2:
                self.path = []
                Logger.info("Navigation Arrived!")
            
            # 2. 檢查是否通過「中間節點」
            # 如果還沒到終點，但已經經過了路徑上的下一個點，就把它移除
            elif self.path:
                target = self.path[0]
                dist_to_target = math.sqrt((target.x - cx)**2 + (target.y - cy)**2)
                
                if dist_to_target < GameSettings.TILE_SIZE:
                    self.path.pop(0)

        # (原本的 input_manager.key_down 邏輯接在下面，保持不變...)
            
        move_x = 0
        move_y = 0
        
        # 2. 移動邏輯if self
        if dis.x != 0 or dis.y != 0:
            # 更新面向與動畫
            if dis.x > 0:
                self.direction = Direction.RIGHT
                self.animation.switch("right")
            elif dis.x < 0:
                self.direction = Direction.LEFT
                self.animation.switch("left")
            elif dis.y > 0:
                self.direction = Direction.DOWN
                self.animation.switch("down")
            elif dis.y < 0:
                self.direction = Direction.UP
                self.animation.switch("up")

            # 正規化向量
            length = math.sqrt(dis.x ** 2 + dis.y ** 2)
            if length > 0:
                dis.x /= length
                dis.y /= length
            
            move_x += dis.x * self.speed * dt
            move_y += dis.y * self.speed * dt

            # X 碰撞
            self.position.x += move_x
            player_rect = pg.Rect(self.position.x, self.position.y, GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)
            if self.game_manager.check_collision(player_rect):
                self.position.x = self._snap_to_grid(self.position.x)

            # Y 碰撞
            self.position.y += move_y
            player_rect = pg.Rect(self.position.x, self.position.y, GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)
            if self.game_manager.check_collision(player_rect):
                self.position.y = self._snap_to_grid(self.position.y)
        
        # 3. 傳送點
        tp = self.game_manager.current_map.check_teleport(self.position)
        if tp:
            dest = tp.destination
            self.game_manager.switch_map(dest)
            self.path = [] # 換圖後清空導航
                
        super().update(dt)

    @override
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)
        
    @override
    def to_dict(self) -> dict[str, object]:
        return super().to_dict()
    
    @classmethod
    @override
    def from_dict(cls, data: dict[str, object], game_manager: GameManager) -> Player:
        return cls(data["x"] * GameSettings.TILE_SIZE, data["y"] * GameSettings.TILE_SIZE, game_manager)