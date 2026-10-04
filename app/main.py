from __future__ import annotations

import asyncio
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .database import Database, utc_now
from .schemas import (
    LoginRequest,
    QueueAddRequest,
    QueueEditRequest,
    SearchRequest,
    SendRequest,
    TokenConnectRequest,
)
from .security import TokenCipher, new_csrf_token, password_matches, require_admin, require_csrf
from .threads_client import ThreadsApiError, ThreadsClient, expires_at_from


settings = get_settings()
db = Database(settings.app_database_path)
cipher = TokenCipher(settings)
threads = ThreadsClient(settings)
templates = Jinja2Templates(directory="app/templates")


class LoginLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        attempts = self._attempts[key]
        while attempts and attempts[0] < now - 900:
            attempts.popleft()
        return len(attempts) < 8

    def fail(self, key: str) -> None:
        self._attempts[key].append(time.monotonic())

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)


login_limiter = LoginLimiter()
send_job: dict[str, Any] = {
    "running": False,
    "stop_requested": False,
    "total": 0,
    "completed": 0,
    "sent": 0,
    "failed": 0,
    "current_item_id": None,
    "message": "Chưa có lượt gửi nào đang chạy.",
}
send_job_lock = asyncio.Lock()
stop_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    app.state.send_task = None
    yield
    task = getattr(app.state, "send_task", None)
    if task and not task.done():
        stop_event.set()
        task.cancel()


app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret or secrets.token_urlsafe(32),
    https_only=settings.is_production,
    same_site="lax",
    max_age=60 * 60 * 12,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.exception_handler(ThreadsApiError)
async def threads_error_handler(_: Request, exc: ThreadsApiError) -> JSONResponse:
    http_status = exc.status_code if 400 <= exc.status_code <= 599 else 502
    return JSONResponse(
        status_code=http_status,
        content={"detail": exc.safe_message, "rate_limited": exc.is_rate_limit},
    )


def account_with_token() -> tuple[dict[str, Any], str]:
    account = db.get_account()
    if not account:
        raise HTTPException(status_code=409, detail="Chưa kết nối tài khoản Threads.")
    try:
        token = cipher.decrypt(account["token_cipher"])
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return account, token


def public_account(account: dict[str, Any] | None) -> dict[str, Any] | None:
    if not account:
        return None
    return {
        "threads_user_id": account["threads_user_id"],
        "username": account["username"],
        "expires_at": account["expires_at"],
        "scopes": account["scopes"],
        "connected_at": account["connected_at"],
        "updated_at": account["updated_at"],
    }


def lead_score(text: str, query: str) -> int:
    source = text.casefold()
    score = 30
    if query.casefold() in source:
        score += 20
    strong_phrases = ("cần tìm", "tìm thợ", "tìm photographer", "book lịch", "chụp kỷ yếu")
    intent_phrases = ("báo giá", "xin giá", "tư vấn", "studio", "nhiếp ảnh", "photographer")
    score += 25 if any(phrase in source for phrase in strong_phrases) else 0
    score += 15 if any(phrase in source for phrase in intent_phrases) else 0
    if any(word in source for word in ("không cần", "đã tìm được", "đủ người")):
        score -= 30
    return max(0, min(score, 100))


def render_reply(template: str, *, username: str, keyword: str) -> str:
    clean_username = username.lstrip("@") or "bạn"
    reply = template.replace("{username}", clean_username).replace("{keyword}", keyword)
    return " ".join(reply.split())[:500]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "time": utc_now()}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("admin"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"app_name": settings.app_name, "warnings": settings.startup_warnings()},
    )


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/login", status_code=303)
    csrf_token = request.session.get("csrf_token") or new_csrf_token()
    request.session["csrf_token"] = csrf_token
    default_template = (
        "Chào @{username}, DAMI Studio có nhận chụp kỷ yếu tại Hà Nội. "
        "Nếu bạn vẫn đang tìm ekip cho {keyword}, mình có thể gửi concept và báo giá để bạn tham khảo nhé."
    )
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "app_name": settings.app_name,
            "csrf_token": csrf_token,
            "default_template": default_template,
            "max_batch_size": settings.max_batch_size,
        },
    )


@app.post("/api/session/login")
async def session_login(request: Request, payload: LoginRequest):
    client_key = request.client.host if request.client else "unknown"
    if not login_limiter.allowed(client_key):
        raise HTTPException(status_code=429, detail="Đăng nhập sai quá nhiều lần. Hãy thử lại sau 15 phút.")
    if not password_matches(payload.password, settings.app_admin_password):
        login_limiter.fail(client_key)
        raise HTTPException(status_code=401, detail="Mật khẩu không đúng.")
    login_limiter.clear(client_key)
    request.session.clear()
    request.session.update({"admin": True, "csrf_token": new_csrf_token()})
    db.record_event("admin_login", "Đăng nhập quản trị thành công.")
    return {"ok": True}


@app.post("/api/session/logout")
async def session_logout(request: Request):
    require_csrf(request)
    request.session.clear()
    return {"ok": True}


@app.get("/auth/threads/start")
async def threads_oauth_start(request: Request):
    require_admin(request)
    if not settings.meta_configured:
        raise HTTPException(
            status_code=409,
            detail="Hãy cấu hình META_APP_ID, META_APP_SECRET và APP_BASE_URL trước.",
        )
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    return RedirectResponse(threads.authorization_url(state), status_code=302)


@app.get("/auth/threads/callback")
async def threads_oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    require_admin(request)
    expected_state = request.session.pop("oauth_state", "")
    if error:
        return RedirectResponse(f"/?oauth=error", status_code=303)
    if not code or not state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail="OAuth state không hợp lệ hoặc đã hết hạn.")
    token_data = await threads.exchange_code(code)
    access_token = token_data["access_token"]
    profile = await threads.profile(access_token)
    db.save_account(
        threads_user_id=str(profile["id"]),
        username=profile.get("username", "unknown"),
        token_cipher=cipher.encrypt(access_token),
        expires_at=expires_at_from(token_data.get("expires_in")),
        scopes=settings.oauth_scopes,
    )
    db.record_event("threads_connected", f"Đã kết nối @{profile.get('username', 'unknown')} qua OAuth.")
    return RedirectResponse("/?oauth=connected", status_code=303)


@app.get("/api/status")
async def api_status(request: Request):
    require_admin(request)
    return {
        "configured": settings.meta_configured,
        "warnings": settings.startup_warnings(),
        "redirect_uri": settings.redirect_uri,
        "account": public_account(db.get_account()),
        "sent_today": db.sent_today_count(settings.app_timezone),
        "max_daily_replies": settings.max_daily_replies,
        "max_batch_size": settings.max_batch_size,
        "send_delay_seconds": settings.send_delay_seconds,
        "job": send_job.copy(),
    }


@app.post("/api/threads/connect-token")
async def connect_token(request: Request, payload: TokenConnectRequest):
    require_csrf(request)
    profile = await threads.profile(payload.access_token)
    db.save_account(
        threads_user_id=str(profile["id"]),
        username=profile.get("username", "unknown"),
        token_cipher=cipher.encrypt(payload.access_token),
        expires_at=expires_at_from(payload.expires_in),
        scopes=settings.oauth_scopes,
    )
    db.record_event("threads_connected_token", f"Đã kết nối @{profile.get('username', 'unknown')} bằng token.")
    return {"ok": True, "account": public_account(db.get_account())}


@app.post("/api/threads/refresh")
async def refresh_token(request: Request):
    require_csrf(request)
    account, token = account_with_token()
    token_data = await threads.refresh_long_lived_token(token)
    new_token = token_data.get("access_token", token)
    profile = await threads.profile(new_token)
    db.save_account(
        threads_user_id=str(profile["id"]),
        username=profile.get("username", account["username"]),
        token_cipher=cipher.encrypt(new_token),
        expires_at=expires_at_from(token_data.get("expires_in")),
        scopes=account["scopes"],
    )
    db.record_event("token_refreshed", "Đã làm mới Threads access token.")
    return {"ok": True, "account": public_account(db.get_account())}


@app.post("/api/threads/disconnect")
async def disconnect_threads(request: Request):
    require_csrf(request)
    account = db.get_account()
    db.disconnect_account()
    if account:
        db.record_event("threads_disconnected", f"Đã ngắt kết nối @{account['username']}.")
    return {"ok": True}


@app.post("/api/search")
async def search_threads(request: Request, payload: SearchRequest):
    require_csrf(request)
    _, token = account_with_token()
    response = await threads.keyword_search(
        token,
        q=payload.q,
        search_type=payload.search_type,
        search_mode=payload.search_mode,
        limit=payload.limit,
    )
    existing = {
        item["target_thread_id"]: item["status"] for item in db.list_queue(include_sent=True, limit=1000)
    }
    results: list[dict[str, Any]] = []
    for item in response.get("data", []):
        thread_id = str(item.get("id", ""))
        if not thread_id:
            continue
        text = item.get("text") or ""
        results.append(
            {
                "id": thread_id,
                "username": item.get("username") or (item.get("owner") or {}).get("username") or "",
                "text": text,
                "permalink": item.get("permalink") or "",
                "timestamp": item.get("timestamp"),
                "media_type": item.get("media_type"),
                "topic_tag": item.get("topic_tag"),
                "lead_score": lead_score(text, payload.q),
                "queue_status": existing.get(thread_id),
            }
        )
    results.sort(key=lambda item: item["lead_score"], reverse=True)
    db.record_event("keyword_search", f"Tìm '{payload.q}' nhận {len(results)} kết quả thật.")
    return {"data": results, "paging": response.get("paging", {}), "query": payload.q}


@app.post("/api/queue")
async def add_to_queue(request: Request, payload: QueueAddRequest):
    require_csrf(request)
    if len(payload.items) > settings.max_batch_size:
        raise HTTPException(status_code=400, detail=f"Tối đa {settings.max_batch_size} bài mỗi lượt.")
    added = []
    for item in payload.items:
        reply = render_reply(
            payload.template,
            username=item.username,
            keyword=payload.keyword or "buổi chụp kỷ yếu",
        )
        added.append(
            db.add_queue_item(
                target_thread_id=item.id,
                target_username=item.username,
                target_text=item.text,
                permalink=item.permalink,
                reply_text=reply,
            )
        )
    db.record_event("queue_added", f"Đã thêm {len(added)} bài vào hàng chờ.")
    return {"data": added}


@app.get("/api/queue")
async def get_queue(request: Request):
    require_admin(request)
    return {"data": db.list_queue(include_sent=False)}


@app.post("/api/queue/{item_id}/edit")
async def edit_queue_item(request: Request, item_id: int, payload: QueueEditRequest):
    require_csrf(request)
    current = db.get_queue_item(item_id)
    if not current:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục trong hàng chờ.")
    if current["status"] in {"sending", "sent"}:
        raise HTTPException(status_code=409, detail="Không thể sửa mục đang gửi hoặc đã gửi.")
    item = db.update_queue_item(item_id, reply_text=" ".join(payload.reply_text.split()), status="draft", error=None)
    return {"data": item}


@app.post("/api/queue/{item_id}/approve")
async def approve_queue_item(request: Request, item_id: int):
    require_csrf(request)
    current = db.get_queue_item(item_id)
    if not current:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục trong hàng chờ.")
    if current["status"] in {"sending", "sent"}:
        raise HTTPException(status_code=409, detail="Mục này không thể duyệt lại.")
    item = db.update_queue_item(item_id, status="approved", error=None)
    return {"data": item}


@app.delete("/api/queue/{item_id}")
async def delete_queue_item(request: Request, item_id: int):
    require_csrf(request)
    if not db.delete_queue_item(item_id):
        raise HTTPException(status_code=409, detail="Không thể xóa mục đang gửi, đã gửi hoặc không tồn tại.")
    return {"ok": True}


async def run_send_job(ids: list[int]) -> None:
    global send_job
    account, token = account_with_token()
    items = db.get_queue_items(ids)
    approved = [item for item in items if item["status"] == "approved"]
    async with send_job_lock:
        send_job.update(
            {
                "running": True,
                "stop_requested": False,
                "total": len(approved),
                "completed": 0,
                "sent": 0,
                "failed": 0,
                "current_item_id": None,
                "message": f"Đang gửi bằng tài khoản @{account['username']}.",
            }
        )
    stop_event.clear()
    try:
        for index, item in enumerate(approved):
            if stop_event.is_set():
                break
            send_job["current_item_id"] = item["id"]
            send_job["message"] = f"Đang gửi {index + 1}/{len(approved)} tới @{item['target_username']}..."
            db.update_queue_item(item["id"], status="sending", error=None)
            try:
                published_id = await threads.reply_to_post(
                    token,
                    thread_id=item["target_thread_id"],
                    text=item["reply_text"],
                )
                db.update_queue_item(
                    item["id"],
                    status="sent",
                    published_reply_id=published_id,
                    sent_at=utc_now(),
                    error=None,
                )
                send_job["sent"] += 1
                db.record_event(
                    "reply_sent",
                    f"Đã phản hồi bài của @{item['target_username']}.",
                    {"target_thread_id": item["target_thread_id"], "published_reply_id": published_id},
                )
            except ThreadsApiError as exc:
                db.update_queue_item(item["id"], status="failed", error=exc.safe_message)
                send_job["failed"] += 1
                db.record_event("reply_failed", exc.safe_message, {"item_id": item["id"]})
                if exc.is_rate_limit:
                    send_job["message"] = "Meta báo giới hạn tốc độ. Hệ thống đã dừng lượt gửi."
                    stop_event.set()
            except Exception as exc:  # defensive: retain audit trail without exposing secrets
                message = f"Lỗi nội bộ khi gửi: {type(exc).__name__}"
                db.update_queue_item(item["id"], status="failed", error=message)
                send_job["failed"] += 1
                db.record_event("reply_failed", message, {"item_id": item["id"]})
            finally:
                send_job["completed"] += 1
            if stop_event.is_set():
                break
            if index < len(approved) - 1:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=settings.send_delay_seconds)
                except TimeoutError:
                    pass
    finally:
        send_job["running"] = False
        send_job["current_item_id"] = None
        send_job["stop_requested"] = stop_event.is_set()
        if not send_job["message"].startswith("Meta báo"):
            send_job["message"] = (
                f"Hoàn tất: {send_job['sent']} thành công, {send_job['failed']} lỗi."
                if not stop_event.is_set()
                else f"Đã dừng: {send_job['sent']} thành công, {send_job['failed']} lỗi."
            )


@app.post("/api/queue/send")
async def send_queue(request: Request, payload: SendRequest):
    require_csrf(request)
    account_with_token()
    if send_job["running"]:
        raise HTTPException(status_code=409, detail="Một lượt gửi khác đang chạy.")
    unique_ids = list(dict.fromkeys(payload.ids))
    if len(unique_ids) > settings.max_batch_size:
        raise HTTPException(status_code=400, detail=f"Tối đa {settings.max_batch_size} bài mỗi lượt.")
    items = db.get_queue_items(unique_ids)
    approved = [item for item in items if item["status"] == "approved"]
    if not approved:
        raise HTTPException(status_code=400, detail="Hãy duyệt ít nhất một bình luận trước khi gửi.")
    remaining = settings.max_daily_replies - db.sent_today_count(settings.app_timezone)
    if len(approved) > remaining:
        raise HTTPException(
            status_code=429,
            detail=f"Giới hạn nội bộ hôm nay chỉ còn {max(remaining, 0)} phản hồi.",
        )
    request.app.state.send_task = asyncio.create_task(run_send_job([item["id"] for item in approved]))
    return {"ok": True, "count": len(approved)}


@app.post("/api/queue/stop")
async def stop_send(request: Request):
    require_csrf(request)
    if send_job["running"]:
        send_job["stop_requested"] = True
        send_job["message"] = "Đang dừng sau yêu cầu hiện tại..."
        stop_event.set()
    return {"ok": True, "job": send_job.copy()}


@app.get("/api/job")
async def get_send_job(request: Request):
    require_admin(request)
    return {"job": send_job.copy()}


@app.get("/api/history")
async def history(request: Request):
    require_admin(request)
    return {"data": db.history(), "events": db.recent_events()}
