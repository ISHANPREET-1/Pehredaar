"""Runtime settings for Pehredaar, read from the environment with sensible local defaults.

Nothing here talks to AWS. Every field has a default so the project runs with
no .env file at all, per CLAUDE.md section 3's offline requirement.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PEHREDAAR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # AWS, unused until Phase 4 but declared now so nothing later needs a
    # magic string. See CLAUDE.md section 3 and section 6.
    region: str = "ap-south-1"
    table_name: str = "pehredaar"
    bucket_name: str = "pehredaar-snapshots-dev"
    queue_url: str = ""

    # Politeness, see CLAUDE.md section 2, rule 4.
    per_host_delay_seconds: float = 2.0
    global_concurrency: int = 5
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    max_requests_per_host_per_scan: int = 8
    max_redirect_hops: int = 10
    max_fetch_retries: int = 2

    # Scope, see CLAUDE.md section 7, the /scan rules.
    allowed_domain_suffixes: list[str] = [
        ".gov.in",
        ".nic.in",
        ".ac.in",
        ".edu.in",
        ".res.in",
    ]

    # Scoring, see CLAUDE.md section 5.
    suspicious_threshold: int = 20
    likely_compromised_threshold: int = 50
    compromised_threshold: int = 75
    min_signals_for_compromised: int = 2

    # S6 similarity, see CLAUDE.md section 5. Below this Jaccard similarity
    # between the googlebot and desktop profiles, S6 fires.
    similarity_jaccard_threshold: float = 0.3


settings = Settings()
