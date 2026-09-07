import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

# Engine configuration
database_url = settings.DATABASE_URL
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    # OLT Settings
    olt_ip = Column(String, default="192.168.1.100")
    olt_port = Column(Integer, default=22) # SSH (or 23 Telnet)
    olt_user = Column(String, default="admin")
    olt_password = Column(String, default="admin")
    olt_interval_minutes = Column(Integer, default=120) # Default 2h
    olt_command_delay = Column(Float, default=0.5) # Seconds delay between commands to avoid CPU spikes

    # MikroTik Settings
    mikrotik_ip = Column(String, default="192.168.88.1")
    mikrotik_port = Column(Integer, default=8728) # REST or RouterOS API
    mikrotik_user = Column(String, default="admin")
    mikrotik_password = Column(String, default="")
    mikrotik_interval_minutes = Column(Integer, default=20) # Default 20m
    mikrotik_drop_threshold = Column(Integer, default=2) # Notify if drops by >= 2 clients

    # Telegram Alert Settings
    telegram_bot_token = Column(String, default="")
    telegram_chat_id = Column(String, default="")
    telegram_alerts_enabled = Column(Boolean, default=True)

    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)


class OLTONU(Base):
    __tablename__ = "olt_onus"

    id = Column(Integer, primary_key=True, index=True)
    slot_port = Column(String, index=True) # e.g. "GPON 1"
    onu_id = Column(Integer, index=True)   # e.g. 1
    name = Column(String, index=True)      # e.g. "DOMINGOSRITOLIMA_SITIOFIBRA" or "ONU_1"
    serial = Column(String, index=True)    # e.g. "E6CC4BAB"
    status = Column(String, default="online") # online (Active) / offline (Inactive)
    omci_status = Column(String, default="OK")
    olt_rx_power = Column(Float, default=0.0) # OLT Rx Power (e.g. -26.20)
    onu_rx_power = Column(Float, default=0.0) # ONU Rx Power (e.g. -23.01)
    rx_power = Column(Float, default=0.0)     # Primary display power
    tx_power = Column(Float, default=0.0)     # Primary tx power
    distance_km = Column(Float, default=0.0)  # Distance in km
    uptime = Column(String, default="")       # e.g. "1:5:53:29"
    vendor_id = Column(String, default="")    # e.g. "ITBS", "HWTC", "D011"
    model_id = Column(String, default="")     # e.g. "R1v2", "HG8310M", "TK-ONU-1P-D"
    ont_version = Column(String, default="")   # e.g. "F670.1A", "ONUR1_v2.0"
    software_version = Column(String, default="") # e.g. "V1.2.3", "V3R017C00S101"
    updated_at = Column(DateTime, default=datetime.datetime.now)


class OLTCardStats(Base):
    __tablename__ = "olt_card_stats"

    id = Column(Integer, primary_key=True, index=True)
    cpu_usage = Column(Float, default=0.0)
    memory_used_percent = Column(Float, default=0.0)
    memory_avail_kb = Column(Float, default=0.0)
    uptime = Column(String, default="")
    firmware_version = Column(String, default="")
    timestamp = Column(DateTime, default=datetime.datetime.now)


class OLTPonPort(Base):
    __tablename__ = "olt_pon_ports"

    id = Column(Integer, primary_key=True, index=True)
    port_number = Column(Integer, index=True) # 1 to 8
    temperature = Column(String, default="")
    voltage = Column(String, default="")
    tx_power_dbm = Column(Float, default=0.0)
    rx_power_dbm = Column(Float, default=0.0)
    status = Column(String, default="OK")
    updated_at = Column(DateTime, default=datetime.datetime.now)


class OLTMetricsHistory(Base):
    __tablename__ = "olt_metrics_history"

    id = Column(Integer, primary_key=True, index=True)
    total_onus = Column(Integer, default=0)
    online_onus = Column(Integer, default=0)
    offline_onus = Column(Integer, default=0)
    avg_rx_power = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.datetime.now)


class MikrotikMetrics(Base):
    __tablename__ = "mikrotik_metrics"

    id = Column(Integer, primary_key=True, index=True)
    active_connections = Column(Integer, default=0)
    cpu_load = Column(Integer, default=0)
    free_memory_mb = Column(Float, default=0.0)
    total_memory_mb = Column(Float, default=0.0)
    uptime = Column(String, default="")
    board_name = Column(String, default="")
    timestamp = Column(DateTime, default=datetime.datetime.now)


class BgpPeerState(Base):
    __tablename__ = "bgp_peer_state"

    id = Column(Integer, primary_key=True, index=True)
    peer_name = Column(String, index=True)
    remote_address = Column(String, index=True)
    remote_as = Column(String, default="")
    state = Column(String, default="established")
    is_established = Column(Boolean, default=True)
    uptime = Column(String, default="")
    last_check = Column(DateTime, default=datetime.datetime.now)


class MikrotikTopClient(Base):
    __tablename__ = "mikrotik_top_clients"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    ip_address = Column(String)
    mac_address = Column(String)
    uptime = Column(String)
    uptime_seconds = Column(Integer, default=0)
    service = Column(String, default="pppoe")
    updated_at = Column(DateTime, default=datetime.datetime.now)


class MikrotikInterface(Base):
    __tablename__ = "mikrotik_interfaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String, default="ether")
    running = Column(Boolean, default=True)
    disabled = Column(Boolean, default=False)
    comment = Column(String, default="")
    mac_address = Column(String, default="")
    last_check = Column(DateTime, default=datetime.datetime.now)


class MikrotikRadius(Base):
    __tablename__ = "mikrotik_radius"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String, index=True)
    service = Column(String, default="ppp")
    timeout = Column(String, default="300ms")
    disabled = Column(Boolean, default=False)
    status = Column(String, default="UP (OK)") # UP (OK) / DOWN (Timeout/Disabled)
    requests = Column(Integer, default=0)
    accepts = Column(Integer, default=0)
    rejects = Column(Integer, default=0)
    last_check = Column(DateTime, default=datetime.datetime.now)


class MikrotikBlockedClient(Base):
    __tablename__ = "mikrotik_blocked_clients"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    ip_address = Column(String, index=True)
    mac_address = Column(String, default="")
    uptime = Column(String, default="")
    list_name = Column(String, default="rbfull_pgcorte")
    updated_at = Column(DateTime, default=datetime.datetime.now)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(Base.metadata.tables["system_settings"].select())
        row = result.first()
        if not row:
            default_settings = SystemSettings()
            session.add(default_settings)
            await session.commit()
