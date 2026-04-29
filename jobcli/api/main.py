import asyncio
import json
import os
import subprocess
import signal
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from queue import Queue

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from jobcli.core.engine import ApplicationEngine
from jobcli.core.schemas import Config, ResumeData, ApplicationStatus, Job
from jobcli.storage.models import Database
from jobcli.storage.repositories import UserDataRepository, JobRepository, ConfigRepository

app = FastAPI(title="JobCLI Control Center API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: Any):
        if isinstance(message, dict):
            message = json.dumps(message)
        for connection in self.active_connections:
            try:
                await connection.send_text(str(message))
            except Exception:
                pass

manager = ConnectionManager()
engine_instance: Optional[ApplicationEngine] = None
should_stop = False
main_loop: Optional[asyncio.AbstractEventLoop] = None

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()

def get_engine_callback(data: Any):
    """Callback for the ApplicationEngine to broadcast events to WebSockets."""
    global main_loop
    if main_loop and main_loop.is_running():
        main_loop.call_soon_threadsafe(
            lambda: asyncio.create_task(manager.broadcast(data))
        )

def get_engine() -> ApplicationEngine:
    """Initialize or return the global engine instance."""
    global engine_instance
    if engine_instance is None:
        db_path = os.getenv("DATABASE_PATH", "~/.jobcli/jobcli.db")
        db_path = os.path.expandvars(os.path.expanduser(db_path))
        db = Database(f"sqlite:///{Path(db_path).as_posix()}")
        session = db.get_session()
        
        user_repo = UserDataRepository(session)
        config_repo = ConfigRepository(session)
        
        resume = user_repo.get_resume()
        config = config_repo.get_all()
        # Force non-headless and AUTO mode for premium dashboard experience
        from jobcli.core.schemas import InteractionMode
        config.headless = False
        config.interaction_mode = InteractionMode.AUTO
        session.close()
        
        if not resume:
            resume = ResumeData(personal={"first_name": "Unknown", "last_name": "User", "email": "test@example.com", "phone": "000"})
            
        engine_instance = ApplicationEngine(config, resume, db, on_event=get_engine_callback)
    return engine_instance

@app.get("/api/status")
async def get_status():
    return {"status": "online", "engine": "ready"}

# Global buffer for terminal input
terminal_input_buffer = ""

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global should_stop, terminal_input_buffer
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                cmd = json.loads(data)
                if cmd.get("type") == "stop":
                    should_stop = True
                    await manager.broadcast({"type": "log", "message": "\x1b[31m[SYSTEM] Stop signal received. Aborting tasks...\x1b[0m"})
                    engine = get_engine()
                    engine.request_stop()
                elif cmd.get("type") == "input":
                    data = cmd.get("data", "")
                    if data.endswith("\r"):
                        # Strip the \r and append any leading chars to the buffer
                        terminal_input_buffer += data[:-1]
                        
                        engine = get_engine()
                        cmd_to_process = terminal_input_buffer.strip().lower()
                        terminal_input_buffer = ""

                        if cmd_to_process == "/status":
                            config = engine.config
                            msg = f"\r\n\x1b[36mJobCLI Status:\x1b[0m\r\nMode: {config.interaction_mode.value}\r\nLLM: {'Configured' if config.gemini_api_key else 'Missing'}\r\n"
                            await manager.broadcast({"type": "terminal", "message": msg})

                        elif cmd_to_process in ["cancel", "c", "/cancel", "/c", "stop", "/stop"]:
                            # ── Stop signal: works whether agent is waiting or running ──
                            should_stop = True
                            await manager.broadcast({"type": "terminal", "message": "\r\x1b[31m[SYSTEM] Cancelling...\x1b[0m\r\n"})
                            engine = get_engine()
                            engine.request_stop()

                        elif cmd_to_process in ["/r", "/resume", ""]:
                            if engine.active_agent and engine.active_agent._is_waiting:
                                engine.active_agent.remote_resume("")

                        else:
                            # Anything else: if agent waiting, pass it as a reply;
                            # otherwise, handle as a dashboard command.
                            if engine.active_agent and engine.active_agent._is_waiting:
                                engine.active_agent.remote_resume(cmd_to_process)
                            else:
                                await handle_dashboard_command(cmd_to_process)

                    else:
                        # Character by character (or chunk) buffering
                        terminal_input_buffer += data
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def handle_dashboard_command(cmd_text: str):
    """Handle commands typed in the terminal when the agent ISN'T waiting."""
    global should_stop
    cmd_text = cmd_text.strip()
    if not cmd_text:
        return

    # ── Auto-detect raw URLs: treat them exactly like "apply <url>" ──
    raw = cmd_text.lower()
    is_url = raw.startswith("http://") or raw.startswith("https://")
    if is_url:
        cmd_text = f"apply {cmd_text}"
        raw = cmd_text.lower()

    if raw == "help":
        msg = "\r\n\x1b[33mAvailable Commands:\x1b[0m\r\n"
        msg += "  \x1b[1mapply <url>\x1b[0m - Apply to a job URL (or just paste the URL)\r\n"
        msg += "  \x1b[1mbatch\x1b[0m       - Start batch application\r\n"
        msg += "  \x1b[1mdiscover\x1b[0m    - Start job discovery\r\n"
        msg += "  \x1b[1mstop / cancel\x1b[0m - Stop ongoing tasks\r\n"
        msg += "  \x1b[1mhelp\x1b[0m        - Show this help\r\n"
        await manager.broadcast({"type": "terminal", "message": msg})
    elif raw.startswith("apply "):
        url = cmd_text[6:].strip()  # everything after "apply "
        await manager.broadcast({"type": "log", "message": f"\x1b[33m[SYSTEM] Executing: apply {url}\x1b[0m"})
        
        engine = get_engine()
        def run_single():
            try:
                job = Job(url=url, company="Manual", title="Manual Submission")
                get_engine_callback({"type": "log", "message": f"\x1b[36m[SYSTEM] Starting application: {url}\x1b[0m"})
                engine.apply_to_job(job)
            except Exception as e:
                get_engine_callback({"type": "error", "message": str(e)})
                
        asyncio.get_running_loop().run_in_executor(None, run_single)
    elif raw == "start":
        # Trigger a guided start flow in the UI: ask for credentials via a structured form
        await manager.broadcast({
            "type": "log",
            "message": "\x1b[36m[SYSTEM] Starting guided setup flow...\x1b[0m"
        })
        await manager.broadcast({
            "type": "ui_form",
            "form": "login",
            "title": "JobCLI - Enter credentials",
            "fields": [
                {"name": "job_board_username", "label": "Job board username", "type": "text", "placeholder": "email@example.com"},
                {"name": "job_board_password", "label": "Job board password", "type": "password", "placeholder": "Password"},
                {"name": "openai_api_key", "label": "OpenAI API key", "type": "password", "placeholder": "sk-..."},
                {"name": "anthropic_api_key", "label": "Anthropic API key", "type": "password", "placeholder": "sk-... (optional)"},
                {"name": "gemini_api_key", "label": "Google Gemini API key", "type": "password", "placeholder": "(optional)"},
                {"name": "default_llm_provider", "label": "Default LLM provider", "type": "text", "placeholder": "openai|anthropic|gemini"}
            ]
        })
    else:
        # ── Chat Fallback ──
        engine = get_engine()
        config = engine.config
        provider = config.default_llm_provider
        
        api_key = None
        if provider == "openai": api_key = config.openai_api_key
        elif provider == "anthropic": api_key = config.anthropic_api_key
        elif provider == "gemini": api_key = config.gemini_api_key
        
        if not api_key:
            await manager.broadcast({"type": "terminal", "message": f"\r\x1b[31m[ERR] Command not recognized: {cmd_text}. (No LLM API key configured for chat fallback)\x1b[0m\r\n"})
            return

        from jobcli.llm.client import LLMClient
        try:
            # Show thinking...
            await manager.broadcast({"type": "terminal", "message": "\r\n\x1b[90mJobCLI is thinking...\x1b[0m\r"})
            
            client = LLMClient(provider, api_key)
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, client.general_chat, cmd_text)
            
            # Format response for terminal
            formatted = f"\r\n\x1b[33mAI:\x1b[0m {response}\r\n"
            await manager.broadcast({"type": "terminal", "message": formatted})
        except Exception as e:
            await manager.broadcast({"type": "terminal", "message": f"\r\x1b[31m[AI Error] {str(e)}\x1b[0m\r\n"})

class ApplyRequest(BaseModel):
    url: str

class UserInputRequest(BaseModel):
    """User response to UI question."""
    session_id: str
    field_name: str
    value: str

# Global session storage for tracking active applications
active_sessions: Dict[str, Dict[str, Any]] = {}
session_input_queues: Dict[str, Queue] = {}

@app.post("/api/apply/single")
async def apply_single(request: ApplyRequest, background_tasks: BackgroundTasks):
    global should_stop
    should_stop = False
    engine = get_engine()
    
    def run_single():
        try:
            job = Job(url=request.url, company="Manual", title="Manual Submission")
            get_engine_callback({"type": "log", "message": f"\x1b[36m[SYSTEM] Starting manual submission: {request.url}\x1b[0m"})
            engine.apply_to_job(job)
        except Exception as e:
            get_engine_callback({"type": "error", "message": str(e)})

    background_tasks.add_task(run_single)
    return {"message": f"Started application for {request.url}"}

@app.post("/api/apply/with-ui")
async def apply_with_ui(request: ApplyRequest, background_tasks: BackgroundTasks):
    """Apply to a job with real-time UI updates and user interaction."""
    import uuid
    
    session_id = str(uuid.uuid4())[:8]
    active_sessions[session_id] = {
        "url": request.url,
        "status": "starting",
        "events": [],
        "paused": False,
        "waiting_for": None,
    }
    session_input_queues[session_id] = Queue()
    
    def run_application():
        try:
            engine = get_engine()
            job = Job(url=request.url, company="Manual", title="Manual Submission")
            
            # Update UI
            get_engine_callback({
                "type": "application_event",
                "session_id": session_id,
                "event": "started",
                "url": request.url,
                "message": f"[LOG] Starting application to {request.url}"
            })
            
            # Run the application
            engine.apply_to_job(job)
            
            # Update UI
            active_sessions[session_id]["status"] = "completed"
            get_engine_callback({
                "type": "application_event",
                "session_id": session_id,
                "event": "completed",
                "message": "[OK] Application submitted successfully!"
            })
            
        except Exception as e:
            active_sessions[session_id]["status"] = "error"
            get_engine_callback({
                "type": "application_event",
                "session_id": session_id,
                "event": "error",
                "message": f"❌ Error: {str(e)}"
            })
        finally:
            # Cleanup
            if session_id in session_input_queues:
                del session_input_queues[session_id]
    
    background_tasks.add_task(run_application)
    return {
        "session_id": session_id,
        "message": "Application started with UI updates",
        "url": request.url
    }

@app.post("/api/apply/user-input")
async def submit_user_input(request: UserInputRequest):
    """Submit user input to a waiting application."""
    if request.session_id not in session_input_queues:
        return {"error": "Session not found"}, 404
    
    # Put input in queue for application to consume
    session_input_queues[request.session_id].put({
        "field": request.field_name,
        "value": request.value
    })
    
    # Update UI
    get_engine_callback({
        "type": "application_event",
        "session_id": request.session_id,
        "event": "user_input_received",
        "field": request.field_name,
        "value": request.value,
        "message": f"✓ Received: {request.field_name} = {request.value}"
    })
    
    return {"status": "input_received", "session_id": request.session_id}

@app.get("/api/apply/session/{session_id}")
async def get_session_status(session_id: str):
    """Get status of an application session."""
    if session_id not in active_sessions:
        return {"error": "Session not found"}, 404
    
    session = active_sessions[session_id]
    return {
        "session_id": session_id,
        "status": session["status"],
        "url": session["url"],
        "paused": session["paused"],
        "waiting_for": session["waiting_for"],
        "events_count": len(session["events"])
    }

@app.post("/api/apply/batch")
async def apply_batch(background_tasks: BackgroundTasks):
    global should_stop
    should_stop = False
    engine = get_engine()
    
    def run_batch():
        session = engine.database.get_session()
        job_repo = JobRepository(session)
        jobs = job_repo.list_pending()
        session.close()
        
        for job in jobs:
            if should_stop:
                get_engine_callback({"type": "log", "message": "\x1b[31m[SYSTEM] Batch processing stopped by user.\x1b[0m"})
                break
            try:
                get_engine_callback({"type": "log", "message": f"Processing job: {job.url}"})
                engine.apply_to_job(job)
            except Exception as e:
                get_engine_callback({"type": "error", "message": str(e)})
    
    background_tasks.add_task(run_batch)
    return {"message": "Batch application started in background"}


class LoginRequest(BaseModel):
    job_board_username: Optional[str] = None
    job_board_password: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    default_llm_provider: Optional[str] = None


@app.post("/api/ui/login")
async def ui_login(request: LoginRequest):
    """Accept credentials from the UI and save them to the config repository."""
    try:
        db_path = os.getenv("DATABASE_PATH", "~/.jobcli/jobcli.db")
        db_path = os.path.expandvars(os.path.expanduser(db_path))
        db = Database(f"sqlite:///{Path(db_path).as_posix()}")
        session = db.get_session()
        config_repo = ConfigRepository(session)

        # Persist each provided field
        if request.job_board_username:
            config_repo.set("job_board_username", request.job_board_username)
        if request.job_board_password:
            config_repo.set("job_board_password", request.job_board_password)
        if request.openai_api_key:
            config_repo.set("openai_api_key", request.openai_api_key)
        if request.anthropic_api_key:
            config_repo.set("anthropic_api_key", request.anthropic_api_key)
        if request.gemini_api_key:
            config_repo.set("gemini_api_key", request.gemini_api_key)
        if request.default_llm_provider:
            config_repo.set("default_llm_provider", request.default_llm_provider)

        session.close()
        # Inform UI
        await manager.broadcast({"type": "log", "message": "\x1b[32m[SYSTEM] Credentials saved successfully.\x1b[0m"})
        return {"status": "ok", "message": "Credentials saved"}
    except Exception as e:
        await manager.broadcast({"type": "error", "message": str(e)})
        return {"status": "error", "message": str(e)}

@app.post("/api/discover")
async def discover_jobs(background_tasks: BackgroundTasks):
    def run_discover():
        process = subprocess.Popen(
            ["jobcli", "discover"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in process.stdout:
            get_engine_callback({"type": "log", "message": line.strip()})
    
    background_tasks.add_task(run_discover)
    return {"message": "Discovery started"}

# Mount the static files
ui_dist = Path(__file__).parent.parent.parent / "ui" / "dist"
if ui_dist.exists():
    app.mount("/", StaticFiles(directory=str(ui_dist), html=True), name="ui")
else:
    @app.get("/")
    async def root_warning():
        return {"message": "UI not built. Run 'npm run build' in the ui folder."}

if __name__ == "__main__":
    import uvicorn

    def _env_bool(key: str, default: bool) -> bool:
        raw = os.getenv(key)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}

    host = os.getenv("JOBCLI_API_HOST", "0.0.0.0")
    port = int(os.getenv("JOBCLI_API_PORT", "8000"))
    reload = _env_bool("JOBCLI_API_RELOAD", True)
    uvicorn.run("jobcli.api.main:app", host=host, port=port, reload=reload)
