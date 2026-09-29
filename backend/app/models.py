"""Stable, browser-safe API contracts for AuraLAN v1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

HealthState = Literal["healthy", "degraded", "warning", "critical", "unknown"]
ServiceState = Literal["online", "offline", "unknown"]
InterfaceRole = Literal["access_point", "uplink", "vpn", "container_bridge", "virtual", "unknown"]


class BrandResponse(BaseModel):
    product_name: str = Field(alias="productName")
    short_name: str = Field(alias="shortName")
    tagline: str
    version: str
    api_version: str = Field(alias="apiVersion")
    repository: dict[str, str] = Field(default_factory=dict)
    accent: dict[str, str] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class MetaResponse(BaseModel):
    brand: BrandResponse
    mode: Literal["local-metadata"] = "local-metadata"
    capabilities: dict[str, bool] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    ok: bool
    mode: Literal["local-metadata"] = "local-metadata"
    api_version: str = "v1"
    version: str


class HostResponse(BaseModel):
    name: str
    uptime: str
    load: str
    memory_used_percent: int | None = None
    storage_used_percent: int | None = None
    temperature_celsius: float | None = None


class AccessPointResponse(BaseModel):
    available: bool = False
    connection: str | None = None
    interface: str | None = None
    ssid: str | None = None
    channel: int | None = None
    band: str | None = None
    frequency_mhz: int | None = None
    ipv4: str | None = None
    subnet: str | None = None
    state: ServiceState = "unknown"


class UplinkResponse(BaseModel):
    interface: str | None = None
    gateway: str | None = None
    ipv4: str | None = None
    state: ServiceState = "unknown"


class DhcpResponse(BaseModel):
    detected: bool = False
    state: ServiceState = "unknown"
    unit: str | None = None
    interface: str | None = None
    lease_count: int = 0


class InterfaceResponse(BaseModel):
    name: str
    type: str = "unknown"
    addresses: list[str] = Field(default_factory=list)
    state: str = "unknown"
    mtu: int | None = None
    role: InterfaceRole = "unknown"


class NetworkResponse(BaseModel):
    access_point: AccessPointResponse
    uplink: UplinkResponse
    dhcp: DhcpResponse
    interfaces: list[InterfaceResponse] = Field(default_factory=list)
    routes: list[dict[str, str]] = Field(default_factory=list)


DeviceCategory = Literal[
    "phone", "tablet", "computer", "tv", "media_player", "speaker", "smart_home", "iot", "camera", "printer",
    "router", "access_point", "server", "raspberry_pi", "microcontroller", "console", "watch", "unknown",
]
DeviceIconKey = Literal[
    "phone", "tablet", "laptop", "apple_tv", "tv", "media_player", "speaker", "iot", "camera", "printer",
    "router", "access_point", "server", "raspberry_pi", "microcontroller", "console", "watch", "vacuum",
    "garage", "heat_pump", "vr_headset", "device_generic",
]
IdentityConfidence = Literal["high", "medium", "low"]


class IdentityValueResponse(BaseModel):
    value: str
    source: str
    confidence: IdentityConfidence


class IdentitySourceResponse(BaseModel):
    source: str
    confidence: IdentityConfidence


class DeviceIdentityResponse(BaseModel):
    display_name: IdentityValueResponse | None = None
    vendor: IdentityValueResponse | None = None
    model: IdentityValueResponse | None = None
    device_type: IdentityValueResponse | None = None
    sources: list[IdentitySourceResponse] = Field(default_factory=list)


class DeviceMetadataResponse(BaseModel):
    alias: str | None = None
    category_override: DeviceCategory | None = None
    note: str | None = None
    favorite: bool = False


class DeviceObservationResponse(BaseModel):
    source: str
    interface: str | None = None
    ip: str | None = None
    neighbor_state: str | None = None


class DeviceLeaseResponse(BaseModel):
    present: bool = False
    expires_at: int | None = None


class DeviceMetadataUpdate(BaseModel):
    alias: str | None = Field(default=None, max_length=80)
    category_override: DeviceCategory | None = None
    note: str | None = Field(default=None, max_length=280)
    favorite: bool = False


class DeviceResponse(BaseModel):
    id: str
    display_name: str
    hostname: str | None = None
    vendor: str | None = None
    model: str | None = None
    device_type: DeviceCategory = "unknown"
    category: DeviceCategory = "unknown"
    icon_key: DeviceIconKey = "device_generic"
    ip: str
    ip_addresses: list[str] = Field(default_factory=list)
    mac: str
    mac_addresses: list[str] = Field(default_factory=list)
    mac_type: Literal["private", "global", "unknown"] = "unknown"
    interface: str | None = None
    connection_type: Literal["wifi", "ethernet", "vpn", "unknown"] = "unknown"
    online: bool | None = None
    state: Literal["online", "recently_seen", "offline", "known", "unknown"] = "unknown"
    signal_dbm: int | None = None
    signal_quality: Literal["excellent", "good", "fair", "weak"] | None = None
    dhcp: bool = False
    lease_expires_at: int | None = None
    lease: DeviceLeaseResponse = Field(default_factory=DeviceLeaseResponse)
    first_seen_at: int | None = None
    last_seen_at: int | None = None
    identity: DeviceIdentityResponse = Field(default_factory=DeviceIdentityResponse)
    metadata: DeviceMetadataResponse = Field(default_factory=DeviceMetadataResponse)
    observations: list[DeviceObservationResponse] = Field(default_factory=list)


class DevicesResponse(BaseModel):
    items: list[DeviceResponse] = Field(default_factory=list)


class ContainerResponse(BaseModel):
    name: str
    image: str
    state: str
    status: str
    network_mode: str | None = None
    ports: str | None = None
    health: str | None = None


class ServiceResponse(BaseModel):
    id: str
    name: str
    detected: bool
    state: ServiceState
    runtime: str | None = None
    summary: str
    description_key: str | None = None
    short_description: str = ""
    category: str = "other"
    capabilities: dict[str, bool] = Field(default_factory=dict)
    importance: Literal["core", "standard", "optional"] = "optional"
    details: dict[str, Any] = Field(default_factory=dict)


class ServicesResponse(BaseModel):
    items: list[ServiceResponse] = Field(default_factory=list)


class ActivityEventResponse(BaseModel):
    id: int
    event_type: Literal["device_first_seen", "favorite_not_seen", "favorite_seen_again"]
    entity_id: str
    display_name: str | None = None
    ip: str | None = None
    mac: str | None = None
    created_at: int


class ActivityResponse(BaseModel):
    items: list[ActivityEventResponse] = Field(default_factory=list)


class NotificationStatusResponse(BaseModel):
    configured: bool = False
    include_identifiers: bool = False
    last_attempt_at: int | None = None
    last_success_at: int | None = None
    last_error: str | None = None
    pending_events: int = 0


class SystemStateResponse(BaseModel):
    state: HealthState
    title: str
    summary: str
    attention_count: int = 0


class MonitorResponse(BaseModel):
    enabled: bool = False
    interval_seconds: int = 0
    running: bool = False
    last_attempt_at: int | None = None
    last_success_at: int | None = None
    last_error: str | None = None


class StatusResponse(BaseModel):
    version: str = ""
    api_version: str = "v1"
    generated_at: str
    system: SystemStateResponse
    host: HostResponse
    network: NetworkResponse
    devices: list[DeviceResponse] = Field(default_factory=list)
    services: ServicesResponse
    activity: list[ActivityEventResponse] = Field(default_factory=list)
    monitor: MonitorResponse = Field(default_factory=MonitorResponse)
    notifications: NotificationStatusResponse = Field(default_factory=NotificationStatusResponse)
    errors: list[str] = Field(default_factory=list)


class DiagnosticsResponse(BaseModel):
    generated_at: str
    api_version: str
    app_version: str
    mode: Literal["local-metadata"] = "local-metadata"
    host: HostResponse
    network: NetworkResponse
    services: ServicesResponse
    monitor: MonitorResponse = Field(default_factory=MonitorResponse)
    notifications: NotificationStatusResponse = Field(default_factory=NotificationStatusResponse)
    discovery_errors: list[str] = Field(default_factory=list)
