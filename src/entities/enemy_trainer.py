from __future__ import annotations
import pygame
import random
from enum import Enum
from dataclasses import dataclass, field
from typing import override

from .entity import Entity
from src.sprites import Sprite, Animation
from src.core import GameManager
from src.core.services import input_manager, scene_manager
from src.utils import GameSettings, Direction, Position, PositionCamera

class EnemyTrainerClassification(Enum):
    STATIONARY = "stationary"
    MERCHANT = "merchant"
    RANDOM_MOVEMENT = "random_movement" # [Fix] 補上這個列舉

# [New] 定義隨機移動的邏輯
@dataclass
class RandomMovement:
    move_timer: float = 0.0
    wait_timer: float = 0.0
    is_waiting: bool = False
    
    def update(self, enemy: "EnemyTrainer", dt: float) -> None:
        if self.is_waiting:
            self.wait_timer -= dt
            if self.wait_timer <= 0:
                self.is_waiting = False
                # 隨機選方向
                choices = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]
                direction = random.choice(choices)
                enemy._set_direction(direction)
                self.move_timer = 1.0
        else:
            self.move_timer -= dt
            if self.move_timer <= 0:
                self.is_waiting = True
                self.wait_timer = random.uniform(1.0, 3.0)
                return

            # 移動 (簡單實作，不含碰撞檢查，如需碰撞可參考 Player 邏輯)
            speed = 30
            if enemy.direction == Direction.UP: enemy.position.y -= speed * dt
            elif enemy.direction == Direction.DOWN: enemy.position.y += speed * dt
            elif enemy.direction == Direction.LEFT: enemy.position.x -= speed * dt
            elif enemy.direction == Direction.RIGHT: enemy.position.x += speed * dt
            
            # 限制範圍 (簡單限制：不要離出生點太遠)
            # 這裡需要 enemy 有 origin_pos，下方的 __init__ 會補上

@dataclass
class IdleMovement:
    def update(self, enemy: "EnemyTrainer", dt: float) -> None:
        return

class EnemyTrainer(Entity):
    classification: EnemyTrainerClassification
    max_tiles: int | None
    _movement: RandomMovement | IdleMovement # [Fix] 支援多種移動模式
    warning_sign: Sprite
    detected: bool
    los_direction: Direction
    sprite_path: str 
    origin_pos: Position # [New] 記住出生點

    @override
    def __init__(
        self,
        x: float,
        y: float,
        game_manager: GameManager,
        classification: EnemyTrainerClassification = EnemyTrainerClassification.STATIONARY,
        # [Fix] 參數順序調整正確
        facing: Direction | None = None,
        max_tiles: int | None = 2,
        sprite_path: str = "character/ow1.png",
    ) -> None:
        super().__init__(x * GameSettings.TILE_SIZE, y * GameSettings.TILE_SIZE, game_manager)
        
        self.sprite_path = sprite_path
        self.animation = Animation(sprite_path, ["down", "left", "right", "up"], 4, (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE))
        
        self.classification = classification
        self.facing = facing
        self.direction = facing or Direction.DOWN
        self.max_tiles = max_tiles
        self.origin_pos = Position(self.position.x, self.position.y)
        
        # [Fix] 根據分類決定移動邏輯，避免 ValueError 崩潰
        if classification == EnemyTrainerClassification.RANDOM_MOVEMENT:
            self._movement = RandomMovement()
        elif classification in (EnemyTrainerClassification.STATIONARY, EnemyTrainerClassification.MERCHANT):
            self._movement = IdleMovement()
        else:
            # 預設為靜止，避免崩潰
            self._movement = IdleMovement()

        if facing is None:
            self._set_direction(Direction.DOWN)
        else:
            self._set_direction(facing)
            
        self.warning_sign = Sprite("exclamation.png", (GameSettings.TILE_SIZE // 2, GameSettings.TILE_SIZE // 2))
        self.warning_sign.update_pos(Position(self.position.x + GameSettings.TILE_SIZE // 4, self.position.y - GameSettings.TILE_SIZE // 2))
        self.detected = False

    @override
    def update(self, dt: float) -> None:
        self._movement.update(self, dt)
        self._has_los_to_player()
        self.animation.update_pos(self.position)

    @override
    def draw(self, screen: pygame.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)
        if self.detected:
            self.warning_sign.draw(screen, camera)
        if GameSettings.DRAW_HITBOXES:
            los_rect = self._get_los_rect()
            if los_rect is not None:
                pygame.draw.rect(screen, (255, 255, 0), camera.transform_rect(los_rect), 1)

    def _set_direction(self, direction: Direction) -> None:
        self.direction = direction
        if direction == Direction.RIGHT: self.animation.switch("right")
        elif direction == Direction.LEFT: self.animation.switch("left")
        elif direction == Direction.DOWN: self.animation.switch("down")
        else: self.animation.switch("up")
        self.los_direction = self.direction

    def _get_los_rect(self) -> pygame.Rect | None:
        tile = GameSettings.TILE_SIZE
        x = int(self.position.x)
        y = int(self.position.y)
        if self.los_direction == Direction.UP: return pygame.Rect(x, y - tile, tile, tile)
        elif self.los_direction == Direction.DOWN: return pygame.Rect(x, y + tile, tile, tile)
        elif self.los_direction == Direction.LEFT: return pygame.Rect(x - tile, y, tile, tile)
        elif self.los_direction == Direction.RIGHT: return pygame.Rect(x + tile, y, tile, tile)
        return None

    def _has_los_to_player(self) -> None:
        player = self.game_manager.player
        if player is None:
            self.detected = False
            return
        los_rect = self._get_los_rect()
        if los_rect is None:
            self.detected = False
            return
        player_rect = pygame.Rect(int(player.position.x), int(player.position.y), GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)
        self.detected = los_rect.colliderect(player_rect)

    @classmethod
    @override
    def from_dict(cls, data: dict, game_manager: GameManager) -> "EnemyTrainer":
        class_str = data.get("classification", "stationary")
        try: classification = EnemyTrainerClassification(class_str)
        except ValueError: classification = EnemyTrainerClassification.STATIONARY
        
        max_tiles = data.get("max_tiles")
        facing_val = data.get("facing")
        facing: Direction | None = None
        
        if facing_val is not None:
            if isinstance(facing_val, str): facing = Direction[facing_val]
            elif isinstance(facing_val, Direction): facing = facing_val
        
        sprite_path = data.get("sprite", "character/ow1.png")

        # [Fix] 使用 Keyword Arguments 呼叫，確保安全
        return cls(
            x = data["x"], 
            y = data["y"], 
            game_manager = game_manager, 
            classification = classification, 
            facing = facing, 
            max_tiles = max_tiles,
            sprite_path = sprite_path
        )

    @override
    def to_dict(self) -> dict[str, object]:
        base: dict[str, object] = super().to_dict()
        base["classification"] = self.classification.value
        base["facing"] = self.direction.name
        base["max_tiles"] = self.max_tiles
        base["sprite"] = self.sprite_path
        return base