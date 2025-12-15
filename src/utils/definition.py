from pygame import Rect
from .settings import GameSettings
from dataclasses import dataclass
from enum import Enum
from typing import overload, TypedDict, Protocol

MouseBtn = int
Key = int

Direction = Enum('Direction', ['UP', 'DOWN', 'LEFT', 'RIGHT', 'NONE'])

# [mine] 定義屬性
class Element(Enum):
    NORMAL = "Normal"
    WATER = "Water"
    FIRE = "Fire"
    GRASS = "Grass"

# [New] 定義屬性相剋邏輯
# Key: 攻擊方屬性, Value: {防禦方屬性: 倍率}
ELEMENT_CHART = {
    Element.WATER: {Element.FIRE: 2.0, Element.GRASS: 0.5, Element.WATER: 0.5},
    Element.FIRE: {Element.GRASS: 2.0, Element.WATER: 0.5, Element.FIRE: 0.5},
    Element.GRASS: {Element.WATER: 2.0, Element.FIRE: 0.5, Element.GRASS: 0.5},
    Element.NORMAL: {} # Normal 打誰都 1.0
}

@dataclass
class Position:
    x: float
    y: float
    
    def copy(self):
        return Position(self.x, self.y)
        
    def distance_to(self, other: "Position") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5
        
@dataclass
class PositionCamera:
    x: int
    y: int
    
    def copy(self):
        return PositionCamera(self.x, self.y)
        
    def to_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)
        
    def transform_position(self, position: Position) -> tuple[int, int]:
        return (int(position.x) - self.x, int(position.y) - self.y)
        
    def transform_position_as_position(self, position: Position) -> Position:
        return Position(int(position.x) - self.x, int(position.y) - self.y)
        
    def transform_rect(self, rect: Rect) -> Rect:
        return Rect(rect.x - self.x, rect.y - self.y, rect.width, rect.height)

@dataclass
class Teleport:
    pos: Position
    destination: str
    
    @overload
    def __init__(self, x: int, y: int, destination: str) -> None: ...
    @overload
    def __init__(self, pos: Position, destination: str) -> None: ...

    def __init__(self, *args, **kwargs):
        if isinstance(args[0], Position):
            self.pos = args[0]
            self.destination = args[1]
        else:
            x, y, dest = args
            self.pos = Position(x, y)
            self.destination = dest
    
    def to_dict(self):
        return {
            "x": self.pos.x // GameSettings.TILE_SIZE,
            "y": self.pos.y // GameSettings.TILE_SIZE,
            "destination": self.destination
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(data["x"] * GameSettings.TILE_SIZE, data["y"] * GameSettings.TILE_SIZE, data["destination"])
    
class Monster(TypedDict):
    name: str
    hp: int
    max_hp: int
    level: int
    sprite_path: str
    # [mine] 新增戰鬥數值
    element: str    # 存字串 "Water", "Fire"...
    attack: int
    defense: int
    # [New] 進化相關
    exp: int        # 當前經驗值
    next_evo_level: int # 幾等進化 (0代表不進化)
    next_evo_sprite: str # 進化後變什麼樣子

class Item(TypedDict):
    name: str
    count: int
    sprite_path: str
    # [mine] 道具類型與效果值
    effect_type: str # "HEAL", "ATK_UP", "DEF_UP"
    value: int       # 加多少