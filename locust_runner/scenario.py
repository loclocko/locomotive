from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils import ensure_dir, write_text


_NAME_RE = re.compile(r"[^a-zA-Z0-9_]+")


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = _NAME_RE.sub("_", value)
    value = value.strip("_")
    return value or "task"


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class ScenarioGenerator:
    """Generates Locust test files from scenario configuration.
    
    The scenario config format:
    {
        "think_time": {"min": 0.5, "max": 2.0},  # or just a number
        "headers": {"Authorization": "Bearer ${TOKEN}"},
        "auth": {
            "type": "bearer",
            "token": "${API_TOKEN}"
        },
        "on_start": [  # requests to run once per user at start
            {"method": "POST", "path": "/login", ...}
        ],
        "requests": [
            {
                "name": "Get Users",
                "method": "GET",
                "path": "/users",
                "weight": 5,
                "headers": {},
                "query": {},
                "json": {},
                "tags": ["api"]
            }
        ]
    }
    """
    
    def __init__(
        self,
        scenario: Dict[str, Any],
        target: Dict[str, Any],
    ) -> None:
        self.scenario = scenario
        self.target = target
        self.requests: List[Dict[str, Any]] = []
    
    def load_requests(self) -> None:
        """Load requests from config."""
        self.requests = self.scenario.get("requests", [])
        if not isinstance(self.requests, list):
            self.requests = []
        
        # Filter by tags if specified
        include_tags = self.target.get("tags") or []
        exclude_tags = self.target.get("exclude_tags") or []
        
        if include_tags or exclude_tags:
            include_set = set(include_tags) if include_tags else None
            exclude_set = set(exclude_tags) if exclude_tags else set()
            
            filtered = []
            for req in self.requests:
                req_tags = set(req.get("tags", []))
                if req_tags & exclude_set:
                    continue
                if include_set is not None and not (req_tags & include_set):
                    continue
                filtered.append(req)
            self.requests = filtered
    
    def generate(self, output_dir: Path) -> Path:
        """Generate the locustfile and return its path."""
        self.load_requests()
        
        if not self.requests:
            raise ValueError("scenario.requests must be a non-empty list")
        
        lines = self._generate_imports()
        lines.extend(self._generate_helpers())
        lines.extend(self._generate_user_class())
        
        output_path = output_dir / "generated_locustfile.py"
        ensure_dir(output_dir)
        write_text(output_path, "\n".join(lines) + "\n")
        return output_path
    
    def _generate_imports(self) -> List[str]:
        """Generate import statements."""
        return [
            "import os",
            "import time",
            "import random",
            "from locust import HttpUser, task, between, tag",
            "",
        ]
    
    def _generate_helpers(self) -> List[str]:
        """Generate helper functions for dynamic values."""
        return [
            "",
            "# Dynamic value generators",
            "_iteration_counter = 0",
            "",
            "",
            "def _env(name, default=''):",
            "    '''Get environment variable.'''",
            "    return os.environ.get(name, default)",
            "",
            "",
            "def _timestamp():",
            "    '''Current timestamp in milliseconds.'''",
            "    return str(int(time.time() * 1000))",
            "",
            "",
            "def _random_string(length=8):",
            "    '''Random alphanumeric string.'''",
            "    chars = 'abcdefghijklmnopqrstuvwxyz0123456789'",
            "    return ''.join(random.choice(chars) for _ in range(length))",
            "",
            "",
            "def _iteration():",
            "    '''Incrementing counter.'''",
            "    global _iteration_counter",
            "    _iteration_counter += 1",
            "    return _iteration_counter",
            "",
            "",
            "def _resolve(value):",
            "    '''Resolve dynamic placeholders in string values.",
            "    ",
            "    Supports:",
            "        ${ENV_VAR} - environment variable",
            "        ${timestamp} - current timestamp ms",
            "        ${random} - random string",
            "        ${iteration} - incrementing counter",
            "    '''",
            "    if not isinstance(value, str):",
            "        return value",
            "    ",
            "    import re",
            "    def replace(match):",
            "        key = match.group(1)",
            "        if key == 'timestamp':",
            "            return _timestamp()",
            "        if key == 'random':",
            "            return _random_string()",
            "        if key == 'iteration':",
            "            return str(_iteration())",
            "        # Treat as env var",
            "        return os.environ.get(key, '')",
            "    ",
            "    return re.sub(r'\\$\\{([^}]+)\\}', replace, value)",
            "",
            "",
            "def _resolve_dict(d):",
            "    '''Recursively resolve dynamic values in dict/list.'''",
            "    if isinstance(d, dict):",
            "        return {k: _resolve_dict(v) for k, v in d.items()}",
            "    if isinstance(d, list):",
            "        return [_resolve_dict(v) for v in d]",
            "    return _resolve(d)",
            "",
        ]
    
    def _generate_user_class(self) -> List[str]:
        """Generate the main User class."""
        lines = ["", "class GeneratedUser(HttpUser):"]
        
        # Wait time
        think_time = self.scenario.get("think_time")
        if isinstance(think_time, dict):
            min_wait = _safe_float(think_time.get("min"), 0.5)
            max_wait = _safe_float(think_time.get("max"), min_wait)
            lines.append(f"    wait_time = between({min_wait}, {max_wait})")
        elif think_time is not None:
            value = _safe_float(think_time, 1.0)
            lines.append(f"    wait_time = between({value}, {value})")
        else:
            lines.append("    wait_time = between(0.5, 2.0)")
        
        # Gather headers
        scenario_headers = self.scenario.get("headers") if isinstance(self.scenario.get("headers"), dict) else {}
        target_headers = self.target.get("headers") if isinstance(self.target.get("headers"), dict) else {}
        base_headers = {**target_headers, **scenario_headers}
        
        # Handle auth config
        auth = self.scenario.get("auth")
        if isinstance(auth, dict):
            auth_type = auth.get("type", "").lower()
            if auth_type == "bearer":
                token = auth.get("token", "${API_TOKEN}")
                base_headers["Authorization"] = f"Bearer {token}"
            elif auth_type == "basic":
                # Will be resolved at runtime
                user = auth.get("username", "${API_USER}")
                password = auth.get("password", "${API_PASSWORD}")
                base_headers["Authorization"] = f"Basic {user}:{password}"
            elif auth_type == "api_key":
                header_name = auth.get("header", "X-API-Key")
                key = auth.get("key", "${API_KEY}")
                base_headers[header_name] = key
        
        # Store base headers as class attribute
        if base_headers:
            lines.append(f"    _base_headers = {repr(base_headers)}")
        else:
            lines.append("    _base_headers = {}")
        
        # on_start for setup (login, etc.)
        on_start = self.scenario.get("on_start")
        if isinstance(on_start, list) and on_start:
            lines.extend(self._generate_on_start(on_start, base_headers))
        
        # Generate tasks
        for idx, req in enumerate(self.requests, start=1):
            task_lines = self._generate_task(idx, req, base_headers)
            lines.extend(task_lines)
        
        return lines
    
    def _generate_on_start(self, requests: List[Dict[str, Any]], base_headers: Dict[str, str]) -> List[str]:
        """Generate on_start method for user initialization."""
        lines = [
            "",
            "    def on_start(self):",
            "        '''Run once per user at start (login, setup, etc.).'''",
        ]
        
        for req in requests:
            if not isinstance(req, dict):
                continue
            
            method = str(req.get("method", "GET")).upper()
            path = req.get("path")
            if not path:
                continue
            
            name = req.get("name") or f"{method} {path}"
            
            headers = base_headers.copy()
            req_headers = req.get("headers") if isinstance(req.get("headers"), dict) else {}
            headers.update(req_headers)
            
            params = req.get("query")
            json_body = req.get("json")
            data_body = req.get("data")
            
            # Build call
            args = [repr(method), repr(path)]
            kwargs = [f"name={repr(name)}"]
            if headers:
                kwargs.append(f"headers=_resolve_dict({repr(headers)})")
            if params:
                kwargs.append(f"params=_resolve_dict({repr(params)})")
            if json_body is not None:
                kwargs.append(f"json=_resolve_dict({repr(json_body)})")
            if data_body is not None:
                kwargs.append(f"data=_resolve_dict({repr(data_body)})")
            
            # Handle response capture (for tokens, etc.)
            capture = req.get("capture")
            if capture:
                lines.append(f"        resp = self.client.request({', '.join(args + kwargs)})")
                if isinstance(capture, dict):
                    for var_name, json_path in capture.items():
                        # Simple json path like "token" or "data.access_token"
                        lines.append(f"        try:")
                        lines.append(f"            data = resp.json()")
                        path_parts = json_path.split(".")
                        accessor = "data"
                        for part in path_parts:
                            accessor += f"[{repr(part)}]"
                        lines.append(f"            self.{var_name} = {accessor}")
                        lines.append(f"        except Exception:")
                        lines.append(f"            self.{var_name} = None")
            else:
                lines.append(f"        self.client.request({', '.join(args + kwargs)})")
        
        return lines
    
    def _generate_task(
        self,
        idx: int,
        req: Dict[str, Any],
        base_headers: Dict[str, str],
    ) -> List[str]:
        """Generate a single task method."""
        method = str(req.get("method", "GET")).upper()
        path = req.get("path")
        if not path:
            return []
        
        name = req.get("name") or f"{method} {path}"
        weight = _safe_int(req.get("weight"), 1)
        if weight < 1:
            weight = 1
        
        tags = req.get("tags", [])
        
        headers = base_headers.copy()
        req_headers = req.get("headers") if isinstance(req.get("headers"), dict) else {}
        headers.update(req_headers)
        
        params = req.get("query") if isinstance(req.get("query"), dict) else None
        json_body = req.get("json")
        data_body = req.get("data")
        timeout = req.get("timeout")
        
        # Build function arguments
        args: List[str] = [repr(method), repr(path)]
        kwargs: List[str] = [f"name={repr(name)}"]
        
        if headers:
            kwargs.append(f"headers=_resolve_dict(self._base_headers | {repr(req_headers)})" if req_headers else "headers=_resolve_dict(self._base_headers)")
        if params:
            kwargs.append(f"params=_resolve_dict({repr(params)})")
        if json_body is not None:
            kwargs.append(f"json=_resolve_dict({repr(json_body)})")
        if data_body is not None:
            kwargs.append(f"data=_resolve_dict({repr(data_body)})")
        if timeout is not None:
            kwargs.append(f"timeout={repr(timeout)}")
        
        call = ", ".join(args + kwargs)
        func_name = _slugify(req.get("name") or f"{method}_{path}")
        func_name = f"task_{idx}_{func_name}"
        
        lines = [""]
        for t in tags:
            lines.append(f"    @tag('{t}')")
        lines.append(f"    @task({weight})")
        lines.append(f"    def {func_name}(self):")
        lines.append(f"        self.client.request({call})")
        
        return lines


def generate_locustfile(
    scenario: Dict[str, Any],
    target: Dict[str, Any],
    output_dir: Path,
) -> Path:
    """Generate a locustfile from scenario configuration.
    
    Args:
        scenario: The scenario configuration dict containing requests.
        target: The target/load configuration with host, headers, tags, etc.
        output_dir: Directory to write the generated file.
    
    Returns:
        Path to the generated locustfile.
    """
    generator = ScenarioGenerator(scenario, target)
    return generator.generate(output_dir)
