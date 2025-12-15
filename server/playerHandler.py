import threading
import time
import copy
from dataclasses import dataclass, field
from typing import Dict, Optional

TIMEOUT_TIME = 60.0
CHECK_INTERVAL_TIME = 10.0

@dataclass
class Player:
    id: int
    x: float
    y: float
    map: str
    last_update: float
    # [mine] 新增欄位：方向與怪獸
    direction: str = "DOWN"
    pokemon: dict = None

    # [mine] 更新方法加入 direction 和 pokemon
    def update(self, x: float, y: float, map: str, direction: str, pokemon: dict) -> None:
        # 只要有任何狀態改變，就更新活躍時間
        if (x != self.x or y != self.y or map != self.map or direction != self.direction):
            self.last_update = time.monotonic()
        self.x = x
        self.y = y
        self.map = map
        self.direction = direction
        self.pokemon = pokemon

    def is_inactive(self) -> bool:
        now = time.monotonic()
        return (now - self.last_update) >= TIMEOUT_TIME


class PlayerHandler:
    _lock: threading.Lock
    _stop_event: threading.Event
    _thread: threading.Thread | None
    
    players: Dict[int, Player]
    _next_id: int

    def __init__(self, *, timeout_seconds: float = 120.0, check_interval_seconds: float = 5.0):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        
        self.players = {}
        self._next_id = 0
    # [Fix] 補上這個漏掉的方法
    def unregister(self, player_id: int) -> None:
        # 這裡假設你的儲存變數叫做 self.players (如果是 self._players 請自行調整)
        if hasattr(self, "players") and player_id in self.players:
            del self.players[player_id]
            print(f"[PlayerHandler] Player {player_id} unregistered.")  
    # Threading
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._cleaner, name="PlayerCleaner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _cleaner(self) -> None:
        while not self._stop_event.wait(CHECK_INTERVAL_TIME):
            now = time.monotonic()
            to_remove: list[int] = []
            with self._lock:
                for pid, p in list(self.players.items()):
                    if now - p.last_update >= TIMEOUT_TIME:
                        to_remove.append(pid)
                for pid in to_remove:
                    _ = self.players.pop(pid, None)
                    
    # API
    def register(self) -> int:
        with self._lock:
            pid = self._next_id
            self._next_id += 1
            # 初始化玩家
            self.players[pid] = Player(pid, 0.0, 0.0, "", time.monotonic())
            return pid

    # [Modified] update 接收更多參數
    def update(self, pid: int, x: float, y: float, map_name: str, direction: str, pokemon: dict) -> bool:
        with self._lock:
            p = self.players.get(pid)
            if not p:
                return False
            else:
                p.update(float(x), float(y), str(map_name), str(direction), pokemon)
                return True

    def list_players(self) -> dict:
        with self._lock:
            player_list = {}
            for p in self.players.values():
                player_list[p.id] = {
                    "id": p.id,
                    "x": p.x,
                    "y": p.y,
                    "map": p.map,
                    "direction": p.direction, # [New] 回傳方向
                    "pokemon": p.pokemon      # [New] 回傳怪獸
                }
            return player_list