from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
from typing import Dict, Set
import json
import asyncio
from dataclasses import dataclass, asdict
import uvicorn
import ssl

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
        "https://abdelrahmane7200.github.io",  # Add the GitHub Pages domain
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    allow_origin_regex=r"https://.*\.github\.io"  # Allow all GitHub Pages domains
)


@dataclass
class Player:
    name: str
    color: str
    score: int = 0


@dataclass
class Cell:
    owner: str
    color: str


class GameState:
    def __init__(self):
        self.grid: Dict[str, Cell] = {}
        self.players: Dict[str, Player] = {}
        self.connections: Set[WebSocket] = set()
        self.is_frozen: bool = False

    async def broadcast_state(self):
        if not self.connections:
            return

        state = {
            "grid": {k: asdict(v) for k, v in self.grid.items()},
            "players": {k: asdict(v) for k, v in self.players.items()},
            "frozen": self.is_frozen
        }

        dead_connections = set()
        for connection in self.connections:
            try:
                await connection.send_json(state)
            except:
                dead_connections.add(connection)

        self.connections -= dead_connections


game_state = GameState()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print(f"New connection attempt from {websocket.client}")
    try:
        await websocket.accept()
        print(f"Connection accepted for {websocket.client}")
        game_state.connections.add(websocket)

        await websocket.send_json({
            "grid": {k: asdict(v) for k, v in game_state.grid.items()},
            "players": {k: asdict(v) for k, v in game_state.players.items()},
            "frozen": game_state.is_frozen
        })

        while True:
            try:
                data = await websocket.receive_json()

                if data["type"] == "join":
                    game_state.players[data["name"]] = Player(
                        name=data["name"],
                        color=data["color"]
                    )

                elif data["type"] == "claim":
                    if not game_state.is_frozen:
                        cell_key = data["cell"]
                        player_name = data["player"]

                        if cell_key in game_state.grid:
                            old_owner = game_state.grid[cell_key].owner
                            if old_owner != player_name:
                                game_state.players[old_owner].score -= 1

                        game_state.grid[cell_key] = Cell(
                            owner=player_name,
                            color=game_state.players[player_name].color
                        )
                        game_state.players[player_name].score += 1

                elif data["type"] == "admin":
                    if data["action"] == "freeze":
                        game_state.is_frozen = True
                    elif data["action"] == "unfreeze":
                        game_state.is_frozen = False
                    elif data["action"] == "reset":
                        game_state.grid.clear()
                        for player in game_state.players.values():
                            player.score = 0

                await game_state.broadcast_state()

            except Exception as e:
                print(f"Error handling message: {e}")
                break

    except WebSocketDisconnect:
        print("Client disconnected normally")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if websocket in game_state.connections:
            game_state.connections.remove(websocket)
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close()

app.mount("/", StaticFiles(directory=".", html=True,
          check_dir=False), name="static")

if __name__ == "__main__":
    import uvicorn
    import ssl
    from uvicorn.config import LOGGING_CONFIG

    LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(asctime)s - %(levelname)s - %(message)s"
    LOGGING_CONFIG["formatters"]["access"][
        "fmt"] = '%(asctime)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="debug",
        ws_ping_interval=1.0,
        ws_ping_timeout=10.0,
        proxy_headers=True,
        forwarded_allow_ips="*",
        ws_max_size=10*1024*1024,
        loop="auto",
        ssl_keyfile=None,
        ssl_certfile=None,
        server_header=False,
        date_header=False,
        headers=[
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "*"),
            ("Access-Control-Allow-Headers", "*"),
            ("Access-Control-Expose-Headers", "*"),
        ]
    )

    print(f"Starting server on port {config.port}")
    server = uvicorn.Server(config)
    server.run()
