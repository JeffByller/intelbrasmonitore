import datetime
import logging
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.database import (
    init_db, AsyncSessionLocal, SystemSettings, 
    OLTONU, OLTCardStats, OLTPonPort, OLTMetricsHistory, MikrotikMetrics, BgpPeerState, 
    MikrotikTopClient, MikrotikInterface, MikrotikRadius, MikrotikBlockedClient
)
from app.scheduler import start_scheduler, reschedule_jobs, scheduled_olt_job, scheduled_mikrotik_job
from app.services.telegram import send_telegram_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("main_app")

app = FastAPI(title="Intelbras 8820 & MikroTik Monitor", version="1.2.0")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.on_event("startup")
async def on_startup():
    await init_db()
    await start_scheduler()

# --- Auth Helper ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.now() + datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire.timestamp()})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def get_current_user_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    
    if not token:
        return None
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user = payload.get("sub")
        if user == "admin":
            return user
    except JWTError:
        return None
    return None

# --- Page Routes ---
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    user = get_current_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request=request, name="index.html", context={"admin_user": user})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user_from_cookie(request)
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, password: str = Form(...)):
    if password == settings.ADMIN_PASSWORD:
        token = create_access_token({"sub": "admin"})
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key="access_token", 
            value=token, 
            httponly=True, 
            samesite="lax",
            max_age=43200 # 12 horas de expiração
        )
        return response
    else:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Senha incorreta!"})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response

# --- API Models ---
class SettingsPayload(BaseModel):
    olt_ip: str
    olt_port: int
    olt_user: str
    olt_password: str
    olt_interval_minutes: int
    olt_command_delay: float
    mikrotik_ip: str
    mikrotik_port: int
    mikrotik_user: str
    mikrotik_password: str
    mikrotik_interval_minutes: int
    mikrotik_drop_threshold: int
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_alerts_enabled: bool

class TelegramTestPayload(BaseModel):
    bot_token: str
    chat_id: str

# --- API Endpoints ---
@app.get("/api/settings")
async def get_settings(request: Request):
    if not get_current_user_from_cookie(request):
        raise HTTPException(status_code=401, detail="Não autorizado")
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SystemSettings).where(SystemSettings.id == 1))
        s = result.scalar_one_or_none()
        if not s:
            return {}
        return {
            "olt_ip": s.olt_ip,
            "olt_port": s.olt_port,
            "olt_user": s.olt_user,
            "olt_password": s.olt_password,
            "olt_interval_minutes": s.olt_interval_minutes,
            "olt_command_delay": s.olt_command_delay,
            "mikrotik_ip": s.mikrotik_ip,
            "mikrotik_port": s.mikrotik_port,
            "mikrotik_user": s.mikrotik_user,
            "mikrotik_password": s.mikrotik_password,
            "mikrotik_interval_minutes": s.mikrotik_interval_minutes,
            "mikrotik_drop_threshold": s.mikrotik_drop_threshold,
            "telegram_bot_token": s.telegram_bot_token,
            "telegram_chat_id": s.telegram_chat_id,
            "telegram_alerts_enabled": s.telegram_alerts_enabled,
        }

@app.post("/api/settings")
async def update_settings(payload: SettingsPayload, request: Request):
    if not get_current_user_from_cookie(request):
        raise HTTPException(status_code=401, detail="Não autorizado")
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SystemSettings).where(SystemSettings.id == 1))
        s = result.scalar_one_or_none()
        if not s:
            s = SystemSettings()
            session.add(s)
        
        s.olt_ip = payload.olt_ip
        s.olt_port = payload.olt_port
        s.olt_user = payload.olt_user
        s.olt_password = payload.olt_password
        s.olt_interval_minutes = payload.olt_interval_minutes
        s.olt_command_delay = payload.olt_command_delay
        
        s.mikrotik_ip = payload.mikrotik_ip
        s.mikrotik_port = payload.mikrotik_port
        s.mikrotik_user = payload.mikrotik_user
        s.mikrotik_password = payload.mikrotik_password
        s.mikrotik_interval_minutes = payload.mikrotik_interval_minutes
        s.mikrotik_drop_threshold = payload.mikrotik_drop_threshold

        s.telegram_bot_token = payload.telegram_bot_token
        s.telegram_chat_id = payload.telegram_chat_id
        s.telegram_alerts_enabled = payload.telegram_alerts_enabled
        
        await session.commit()
    
    reschedule_jobs(payload.olt_interval_minutes, payload.mikrotik_interval_minutes)
    return {"status": "success", "message": "Configurações salvas com sucesso!"}

@app.get("/api/dashboard/summary")
async def get_dashboard_summary(request: Request):
    if not get_current_user_from_cookie(request):
        raise HTTPException(status_code=401, detail="Não autorizado")

    async with AsyncSessionLocal() as session:
        # Latest OLT metrics
        olt_hist = await session.execute(select(OLTMetricsHistory).order_by(OLTMetricsHistory.id.desc()).limit(1))
        latest_olt = olt_hist.scalar_one_or_none()

        # OLT Card stats
        c_stats = await session.execute(select(OLTCardStats).order_by(OLTCardStats.id.desc()).limit(1))
        card_stat = c_stats.scalar_one_or_none()
        
        # Latest MikroTik metrics
        mk_hist = await session.execute(select(MikrotikMetrics).order_by(MikrotikMetrics.id.desc()).limit(1))
        latest_mk = mk_hist.scalar_one_or_none()

        # BGP count
        bgp_res = await session.execute(select(BgpPeerState))
        bgps = bgp_res.scalars().all()
        bgp_total = len(bgps)
        bgp_established = sum(1 for b in bgps if b.is_established)

        # Blocked count
        blk_res = await session.execute(select(MikrotikBlockedClient))
        blocked_count = len(blk_res.scalars().all())

        return {
            "olt": {
                "total_onus": latest_olt.total_onus if latest_olt else 0,
                "online_onus": latest_olt.online_onus if latest_olt else 0,
                "offline_onus": latest_olt.offline_onus if latest_olt else 0,
                "avg_rx_power": latest_olt.avg_rx_power if latest_olt else 0.0,
                "cpu_usage": card_stat.cpu_usage if card_stat else 0.0,
                "memory_used_percent": card_stat.memory_used_percent if card_stat else 0.0,
                "firmware_version": card_stat.firmware_version if card_stat else "2.106",
                "uptime": card_stat.uptime if card_stat else "N/A",
                "last_update": latest_olt.timestamp.strftime("%H:%M:%S - %d/%m/%Y") if latest_olt else "N/A"
            },
            "mikrotik": {
                "active_connections": latest_mk.active_connections if latest_mk else 0,
                "cpu_load": latest_mk.cpu_load if latest_mk else 0,
                "free_memory_mb": latest_mk.free_memory_mb if latest_mk else 0.0,
                "total_memory_mb": latest_mk.total_memory_mb if latest_mk else 0.0,
                "uptime": latest_mk.uptime if latest_mk else "N/A",
                "board_name": latest_mk.board_name if latest_mk else "MikroTik",
                "blocked_count": blocked_count,
                "last_update": latest_mk.timestamp.strftime("%H:%M:%S - %d/%m/%Y") if latest_mk else "N/A"
            },
            "bgp": {
                "total_sessions": bgp_total,
                "established_sessions": bgp_established
            }
        }

@app.get("/api/dashboard/onus")
async def get_onus_list(request: Request, search: Optional[str] = None, status_filter: Optional[str] = None):
    if not get_current_user_from_cookie(request):
        raise HTTPException(status_code=401, detail="Não autorizado")

    async with AsyncSessionLocal() as session:
        query = select(OLTONU).order_by(OLTONU.slot_port.asc(), OLTONU.onu_id.asc())
        result = await session.execute(query)
        onus = result.scalars().all()

        filtered = []
        for o in onus:
            if status_filter and status_filter != "all":
                if status_filter == "online" and o.status != "online": continue
                if status_filter == "offline" and o.status == "online": continue
                if status_filter == "warning" and not (-27.5 <= o.rx_power <= -24.5 and o.status == "online"): continue

            if search:
                s = search.lower()
                fields_to_check = [
                    o.name, o.serial, o.slot_port,
                    o.vendor_id or "", o.model_id or "",
                    o.ont_version or "", o.software_version or ""
                ]
                if not any(s in (f or "").lower() for f in fields_to_check):
                    continue

            filtered.append({
                "id": o.id,
                "slot_port": o.slot_port,
                "onu_id": o.onu_id,
                "name": o.name,
                "serial": o.serial,
                "status": o.status,
                "omci_status": o.omci_status,
                "olt_rx_power": o.olt_rx_power,
                "onu_rx_power": o.onu_rx_power,
                "rx_power": o.rx_power,
                "tx_power": o.tx_power,
                "distance_km": o.distance_km,
                "uptime": o.uptime,
                "vendor_id": o.vendor_id,
                "model_id": o.model_id,
                "ont_version": o.ont_version,
                "software_version": o.software_version,
                "updated_at": o.updated_at.strftime("%H:%M:%S %d/%m/%Y")
            })

        return filtered

@app.get("/api/dashboard/olt/ports")
async def get_olt_ports(request: Request):
    if not get_current_user_from_cookie(request):
        raise HTTPException(status_code=401, detail="Não autorizado")

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(OLTPonPort).order_by(OLTPonPort.port_number.asc()))
        ports = res.scalars().all()
        return [
            {
                "port_number": p.port_number,
                "temperature": p.temperature,
                "voltage": p.voltage,
                "tx_power_dbm": p.tx_power_dbm,
                "rx_power_dbm": p.rx_power_dbm,
                "status": p.status
            } for p in ports
        ]

@app.get("/api/dashboard/mikrotik")
async def get_mikrotik_details(request: Request):
    if not get_current_user_from_cookie(request):
        raise HTTPException(status_code=401, detail="Não autorizado")

    async with AsyncSessionLocal() as session:
        bgp_res = await session.execute(select(BgpPeerState).order_by(BgpPeerState.id.asc()))
        bgp_list = bgp_res.scalars().all()

        clients_res = await session.execute(select(MikrotikTopClient).order_by(MikrotikTopClient.id.asc()).limit(30))
        clients_list = clients_res.scalars().all()

        if_res = await session.execute(select(MikrotikInterface).order_by(MikrotikInterface.id.asc()))
        if_list = if_res.scalars().all()

        rad_res = await session.execute(select(MikrotikRadius).order_by(MikrotikRadius.id.asc()))
        rad_list = rad_res.scalars().all()

        blk_res = await session.execute(select(MikrotikBlockedClient).order_by(MikrotikBlockedClient.id.asc()))
        blk_list = blk_res.scalars().all()

        return {
            "bgp_peers": [
                {
                    "peer_name": b.peer_name,
                    "remote_address": b.remote_address,
                    "remote_as": b.remote_as,
                    "state": b.state,
                    "is_established": b.is_established,
                    "uptime": b.uptime,
                    "last_check": b.last_check.strftime("%H:%M:%S")
                } for b in bgp_list
            ],
            "top_clients": [
                {
                    "username": c.username,
                    "ip_address": c.ip_address,
                    "mac_address": c.mac_address,
                    "uptime": c.uptime,
                    "service": c.service
                } for c in clients_list
            ],
            "interfaces": [
                {
                    "name": i.name,
                    "type": i.type,
                    "running": i.running,
                    "disabled": i.disabled,
                    "comment": i.comment,
                    "mac_address": i.mac_address
                } for i in if_list
            ],
            "radius": [
                {
                    "address": r.address,
                    "service": r.service,
                    "timeout": r.timeout,
                    "disabled": r.disabled,
                    "status": r.status,
                    "requests": r.requests,
                    "accepts": r.accepts,
                    "rejects": r.rejects
                } for r in rad_list
            ],
            "blocked_clients": [
                {
                    "username": b.username,
                    "ip_address": b.ip_address,
                    "mac_address": b.mac_address,
                    "uptime": b.uptime,
                    "list_name": b.list_name
                } for b in blk_list
            ]
        }

@app.get("/api/dashboard/history")
async def get_history_charts(request: Request):
    if not get_current_user_from_cookie(request):
        raise HTTPException(status_code=401, detail="Não autorizado")

    async with AsyncSessionLocal() as session:
        olt_res = await session.execute(select(OLTMetricsHistory).order_by(OLTMetricsHistory.id.desc()).limit(20))
        olt_list = list(reversed(olt_res.scalars().all()))

        mk_res = await session.execute(select(MikrotikMetrics).order_by(MikrotikMetrics.id.desc()).limit(20))
        mk_list = list(reversed(mk_res.scalars().all()))

        return {
            "olt_history": [
                {
                    "time": h.timestamp.strftime("%H:%M"),
                    "online": h.online_onus,
                    "offline": h.offline_onus,
                    "avg_rx": h.avg_rx_power
                } for h in olt_list
            ],
            "mikrotik_history": [
                {
                    "time": m.timestamp.strftime("%H:%M"),
                    "active_connections": m.active_connections,
                    "cpu_load": m.cpu_load
                } for m in mk_list
            ]
        }

@app.post("/api/routine/olt")
async def trigger_olt_routine(request: Request):
    if not get_current_user_from_cookie(request):
        raise HTTPException(status_code=401, detail="Não autorizado")
    await scheduled_olt_job()
    return {"status": "success", "message": "Rotina da OLT executada com sucesso!"}

@app.post("/api/routine/mikrotik")
async def trigger_mikrotik_routine(request: Request):
    if not get_current_user_from_cookie(request):
        raise HTTPException(status_code=401, detail="Não autorizado")
    await scheduled_mikrotik_job()
    return {"status": "success", "message": "Rotina do MikroTik executada com sucesso!"}

@app.post("/api/telegram/test")
async def test_telegram(payload: TelegramTestPayload, request: Request):
    if not get_current_user_from_cookie(request):
        raise HTTPException(status_code=401, detail="Não autorizado")
    
    msg = (
        "🚀 <b>TESTE DE NOTIFICAÇÃO - SYSTEM MONITOR</b>\n\n"
        "Seu bot do Telegram foi configurado com sucesso para alertas de <b>BGP</b> e <b>Desconexões de Clientes</b>!"
    )
    success = send_telegram_alert(payload.bot_token, payload.chat_id, msg)
    if success:
        return {"status": "success", "message": "Mensagem de teste enviada com sucesso no grupo do Telegram!"}
    else:
        return {"status": "error", "message": "Falha ao enviar mensagem no Telegram. Verifique o Token e Chat ID."}
