from __future__ import annotations

import logging
import subprocess
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MCPServer:
    """Represents a running MCP server process."""

    def __init__(self, name: str, config: dict) -> None:
        self.name = name
        self.config = config
        self._process: Optional[subprocess.Popen] = None

    def start(self) -> None:
        cmd = [self.config["command"]] + self.config.get("args", [])
        env = self.config.get("env", None)
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            logger.info("Started MCP server '%s' (pid %s)", self.name, self._process.pid)
        except FileNotFoundError as e:
            logger.warning("MCP server '%s' could not start: %s", self.name, e)

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            logger.info("Stopped MCP server '%s'", self.name)


class MCPLoader:
    """Loads and manages MCP server processes from .theorycraft.json config."""

    def __init__(self) -> None:
        from theorycraft.config import get_mcp_config
        self._config = get_mcp_config()
        self._servers: dict[str, MCPServer] = {}

    def start_all(self) -> None:
        for name, cfg in self._config.mcp_servers.items():
            server = MCPServer(name, cfg)
            server.start()
            self._servers[name] = server

    def stop_all(self) -> None:
        for server in self._servers.values():
            server.stop()
        self._servers.clear()

    @property
    def running_servers(self) -> list[str]:
        return list(self._servers.keys())

    def __enter__(self) -> "MCPLoader":
        self.start_all()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop_all()
