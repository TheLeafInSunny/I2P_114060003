from __future__ import annotations
import pygame as pg
from typing import override
from src.sprites import Animation
from src.utils import Position, PositionCamera, Direction, GameSettings
from src.core import GameManager


class Entity:
    animation: Animation
    direction: Direction
    position: Position
    game_manager: GameManager
    
    def __init__(self, x: float, y: float, game_manager: GameManager) -> None:
        # Sprite is only for debug, need to change into animations
        self.animation = Animation(
            "character/ow1.png", ["down", "left", "right", "up"], 4,
            (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)
        )
        
        self.position = Position(x, y)
        self.direction = Direction.DOWN
        self.animation.update_pos(self.position)
        self.game_manager = game_manager

    def update(self, dt: float) -> None:
        self.animation.update_pos(self.position)
        self.animation.update(dt)
        
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        self.animation.draw(screen, camera)
        if GameSettings.DRAW_HITBOXES:
            self.animation.draw_hitbox(screen, camera)
        
    @staticmethod
    def _snap_to_grid(value: float) -> int:
        return round(value / GameSettings.TILE_SIZE) * GameSettings.TILE_SIZE
    #把一個座標「吸附」到最近的格線上（tile grid）
    
    @property
    def camera(self) -> PositionCamera:
        ##
        #玩家的 sprite 是一格（TILE_SIZE），中心在 position + TILE_SIZE / 2；螢幕中心:(SCREEN_WIDTH/2, SCREEN_HEIGHT/2)
       
        screen_w = GameSettings.SCREEN_WIDTH // 2
        screen_h = GameSettings.SCREEN_HEIGHT // 2
#GameSettings.TILE_SIZE:角色高
        player_x = self.position.x + GameSettings.TILE_SIZE // 2
        player_y = self.position.y + GameSettings.TILE_SIZE // 2
  
        cam_x = int(player_x - screen_w)
        cam_y = int(player_y - screen_h)

        return PositionCamera(cam_x, cam_y)
       #鏡頭目前在世界地圖的哪個位置（左上角座標）
        ##
        '''
        [TODO HACKATHON 3]
        Implement the correct algorithm of player camera
        '''
       
        
    def to_dict(self) -> dict[str, object]:
        return {
            "x": self.position.x / GameSettings.TILE_SIZE,
            "y": self.position.y / GameSettings.TILE_SIZE,
        }
        
    @classmethod
    def from_dict(cls, data: dict[str, float | int], game_manager: GameManager) -> Entity:
        x = float(data["x"])
        y = float(data["y"])
        return cls(x * GameSettings.TILE_SIZE, y * GameSettings.TILE_SIZE, game_manager)
        