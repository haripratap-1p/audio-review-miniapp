import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

EOD_HOUR = 19  # IST
PIPELINE_MODEL = "whisper-large + pyannote + gemma3:4b"
MAX_BODY = 32768  # a vote can carry a mark and note for every transcript line
MAX_LINES = 300
IST = ZoneInfo("Asia/Kolkata")
# call: <number or contact name>_<YYYYMMDD-HHMMSS>; in-store clip: <YYYYMMDD_HHMMSS>
STEM = re.compile(r"(?:(.+?)_+)?(\d{4})(\d\d)(\d\d)[-_](\d\d)(\d\d)(\d\d)$")
SYSTEMS = ("pipeline", "gemma", "gemini", "lfm")
REFERENCE = "gemini"  # the reference transcript: shown, judged against, never scored or voted
SCORED = tuple(s for s in SYSTEMS if s != REFERENCE)
LABELS = {"pipeline": "Audio pipeline", "gemma": "Gemma 4 12B", "gemini": "Reference (Gemini)", "lfm": "LFM3-Omni 2B"}
MEMBER_OK = {"creator", "administrator", "member", "restricted"}


@dataclass(frozen=True)
class Settings:
    token: str
    chat: str
    cost_chat: str
    post_from: str  # review list: result folders (day a recording reached us) from this date
    poster_call_date_from: str  # poster: calls whose file-name date is on or after this; same POST_FROM env
    origin: str
    app_link: str
    port: int
    home: Path
    results: Path
    db: Path
    gemini_keys: tuple = field(repr=False)
    judge_model: str
    judge_cap: int  # judge requests per run
    judge_price_in: float  # USD per 1M tokens
    judge_price_out: float  # USD per 1M tokens, thinking included

    @property
    def tunnel_log(self) -> Path:
        return self.home / "review_tunnel.log"

    @property
    def roles_file(self) -> Path:
        return self.home / "roles.json"  # {"owner": <telegram id>, "tech": [ids]}; everyone else is General

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        home = Path(env.get("REVIEW_HOME") or Path.cwd())
        return cls(
            token=env.get("TG_TOKEN", ""),
            chat=env.get("TG_CHAT", ""),
            cost_chat=env.get("TG_COST_CHAT", ""),
            post_from=env.get("POST_FROM", "2026-10-28"),
            poster_call_date_from=env.get("POST_FROM", "0000-00-00"),
            origin=env.get("REVIEW_ORIGIN", "https://haripratap-1p.github.io"),
            app_link=env.get("REVIEW_APP_LINK", "https://t.me/audio_pipeline_calls_bot/review"),
            port=int(env.get("REVIEW_PORT", "8787")),
            home=home,
            results=Path(env.get("RESULTS_BASE", home / "live_results")),
            db=Path(env.get("REVIEW_DB", home / "reviews.db")),
            gemini_keys=tuple(k.strip() for k in env.get("GEMINI_API_KEYS", "").split(",") if k.strip()),
            judge_model=env.get("JUDGE_MODEL", "gemini-3.5-flash-lite"),
            judge_cap=int(env.get("JUDGE_DAILY_CAP", "300")),
            judge_price_in=float(env.get("JUDGE_PRICE_IN", "0.30")),
            judge_price_out=float(env.get("JUDGE_PRICE_OUT", "2.50")),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
