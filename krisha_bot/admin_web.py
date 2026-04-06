from __future__ import annotations

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import BotDB


def create_admin_app(db: BotDB, admin_password: str) -> FastAPI:
    app = FastAPI(title="Krisha Bot Admin")
    templates = Jinja2Templates(directory="krisha_bot/templates")

    def is_authed(request: Request) -> bool:
        return request.cookies.get("admin_auth") == "1"

    @app.get("/admin/login", response_class=HTMLResponse)
    async def admin_login_page(request: Request):
        return templates.TemplateResponse("login.html", {"request": request, "error": None})

    @app.post("/admin/login", response_class=HTMLResponse)
    async def admin_login(request: Request, password: str = Form(...)):
        if password != admin_password:
            return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})
        response = RedirectResponse(url="/admin", status_code=302)
        response.set_cookie("admin_auth", "1", httponly=True)
        return response

    @app.get("/admin/logout")
    async def admin_logout():
        response = RedirectResponse(url="/admin/login", status_code=302)
        response.delete_cookie("admin_auth")
        return response

    @app.get("/admin", response_class=HTMLResponse)
    async def dashboard(request: Request):
        if not is_authed(request):
            return RedirectResponse(url="/admin/login", status_code=302)
        stats = await db.get_dashboard_stats()
        return templates.TemplateResponse("dashboard.html", {"request": request, "stats": stats})

    @app.get("/admin/users", response_class=HTMLResponse)
    async def users_page(request: Request):
        if not is_authed(request):
            return RedirectResponse(url="/admin/login", status_code=302)
        users = await db.get_users_admin()
        return templates.TemplateResponse("users.html", {"request": request, "users": users})

    @app.post("/admin/users/extend")
    async def extend_user(request: Request, user_id: int = Form(...), role: int = Form(...)):
        if not is_authed(request):
            return RedirectResponse(url="/admin/login", status_code=302)
        await db.grant_subscription(user_id, role)
        await db.log_event("grant", f"admin-panel grant user={user_id} role={role}")
        return RedirectResponse(url="/admin/users", status_code=302)

    @app.post("/admin/users/block")
    async def block_user(request: Request, user_id: int = Form(...), blocked: int = Form(...)):
        if not is_authed(request):
            return RedirectResponse(url="/admin/login", status_code=302)
        await db.set_user_blocked(user_id, bool(blocked))
        await db.log_event("block", f"admin-panel block={blocked} user={user_id}")
        return RedirectResponse(url="/admin/users", status_code=302)

    @app.get("/admin/subscriptions", response_class=HTMLResponse)
    async def subscriptions_page(request: Request):
        if not is_authed(request):
            return RedirectResponse(url="/admin/login", status_code=302)
        return templates.TemplateResponse("subscriptions.html", {"request": request})

    @app.post("/admin/subscriptions")
    async def subscriptions_submit(request: Request, user_id: int = Form(...), role: int = Form(...), days: int = Form(...)):
        if not is_authed(request):
            return RedirectResponse(url="/admin/login", status_code=302)
        end = await db.grant_subscription(user_id, role)
        await db.log_event("grant", f"admin-panel form user={user_id} role={role} days={days} end={end}")
        return RedirectResponse(url="/admin/subscriptions", status_code=302)

    @app.get("/admin/logs", response_class=HTMLResponse)
    async def logs_page(request: Request):
        if not is_authed(request):
            return RedirectResponse(url="/admin/login", status_code=302)
        logs = await db.get_recent_events(100)
        return templates.TemplateResponse("logs.html", {"request": request, "logs": logs})

    return app
