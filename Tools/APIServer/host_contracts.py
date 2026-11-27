from pydantic import BaseModel


class WebHostingRequest(BaseModel):
    enabled: bool
    confirmed: bool = False


class WebHostingResponse(BaseModel):
    enabled: bool
    available: bool
    running: bool


class ParityEntry(BaseModel):
    feature: str
    tui_entry: str
    api_paths: list[str]
    availability: str = "runtime-dependent"


class ParityResponse(BaseModel):
    features: list[ParityEntry]
