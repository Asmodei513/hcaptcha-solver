"""
Configuration for hCaptcha Solver.
Contains all settings, API keys, and browser fingerprint configuration.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from enum import Enum


class SolverMethod(Enum):
    """Available solving methods."""
    AUDIO = "audio"
    IMAGE = "image"
    API_2CAPTCHA = "2captcha"
    API_ANTICAPTCHA = "anticaptcha"


@dataclass
class BrowserConfig:
    """Browser automation configuration."""
    headless: bool = False
    browser_type: str = "chromium"  # chromium, firefox, webkit
    slow_mo: int = 100
    timeout: int = 30000
    
    # Realistic browser fingerprint
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "en-US"
    timezone_id: str = "America/New_York"
    
    # Realistic navigator properties
    platform: str = "Win32"
    vendor: str = "Google Inc."
    renderer: str = "ANGLE (Intel, Intel(R) UHD Graphics 630, OpenGL 4.5)"
    
    # WebGL fingerprint
    webgl_vendor: str = "Intel Inc."
    webgl_renderer: str = "Intel(R) UHD Graphics 630"


@dataclass
class ProxyConfig:
    """Proxy configuration."""
    enabled: bool = False
    server: str = ""
    username: str = ""
    password: str = ""
    
    # Rotate through multiple proxies
    proxy_list: List[Dict[str, str]] = field(default_factory=list)
    
    def get_proxy_dict(self) -> Optional[Dict[str, str]]:
        """Get proxy configuration for Playwright."""
        if not self.enabled:
            return None
        if self.server:
            proxy = {"server": self.server}
            if self.username:
                proxy["username"] = self.username
            if self.password:
                proxy["password"] = self.password
            return proxy
        return None


@dataclass
class AudioSolverConfig:
    """Audio challenge solver configuration."""
    # STT backends in order of preference
    stt_backends: List[str] = field(
        default_factory=lambda: ["whisper_local", "google_free"]
    )
    
    # Whisper settings
    whisper_model: str = "base"  # tiny, base, small, medium, large
    whisper_language: str = "en"
    
    # Google Speech Recognition settings
    google_language: str = "en-US"
    google_show_all: bool = False
    
    # Audio processing
    download_dir: str = "/tmp/hcaptcha_audio"
    max_duration: float = 30.0  # Max audio duration in seconds
    
    # Retry settings
    max_retries: int = 3
    retry_delay: float = 2.0


@dataclass
class ImageSolverConfig:
    """Image challenge solver configuration."""
    # Image classification method
    method: str = "api"  # api, local_model
    
    # Download settings
    download_dir: str = "/tmp/hcaptcha_images"
    
    # Classification confidence threshold
    confidence_threshold: float = 0.7
    
    # Retry settings
    max_retries: int = 3
    retry_delay: float = 2.0


@dataclass
class CaptchaApiConfig:
    """Third-party CAPTCHA solving API configuration."""
    # 2Captcha
    twocaptcha_api_key: str = os.getenv("TWOCAPTCHA_API_KEY", "")
    twocaptcha_timeout: int = 120
    twocaptcha_polling_interval: int = 5
    
    # AntiCaptcha
    anticaptcha_api_key: str = os.getenv("ANTICAPTCHA_API_KEY", "")
    anticaptcha_timeout: int = 120
    anticaptcha_polling_interval: int = 5
    
    # Common
    max_retries: int = 3
    retry_delay: float = 5.0


@dataclass
class SteamConfig:
    """Steam-specific configuration."""
    login_url: str = "https://store.steampowered.com/login/"
    max_login_attempts: int = 3
    login_timeout: int = 60000
    
    # Steam credentials (set via environment variables)
    username: str = os.getenv("STEAM_USERNAME", "")
    password: str = os.getenv("STEAM_PASSWORD", "")
    
    # Login selectors
    username_selector: str = "#input_username"
    password_selector: str = "#input_password"
    login_button_selector: str = "#login_btn_signin button"
    captcha_container: str = "#captchagame"


@dataclass
class SolverConfig:
    """Main solver configuration."""
    # Primary solving method
    primary_method: SolverMethod = SolverMethod.AUDIO
    
    # Fallback methods (in order)
    fallback_methods: List[SolverMethod] = field(
        default_factory=lambda: [
            SolverMethod.IMAGE,
            SolverMethod.API_2CAPTCHA,
            SolverMethod.API_ANTICAPTCHA,
        ]
    )
    
    # Sub-configurations
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    audio: AudioSolverConfig = field(default_factory=AudioSolverConfig)
    image: ImageSolverConfig = field(default_factory=ImageSolverConfig)
    captcha_api: CaptchaApiConfig = field(default_factory=CaptchaApiConfig)
    steam: SteamConfig = field(default_factory=SteamConfig)
    
    # Global settings
    max_retries: int = 3
    retry_delay: float = 2.0
    debug: bool = False
    log_file: str = "hcaptcha_solver.log"
    
    # Session management
    save_session: bool = True
    session_dir: str = "/tmp/hcaptcha_sessions"
    
    @classmethod
    def from_env(cls) -> "SolverConfig":
        """Create configuration from environment variables."""
        config = cls()
        
        # Override with environment variables if set
        if os.getenv("HCAPTCHA_HEADLESS"):
            config.browser.headless = os.getenv("HCAPTCHA_HEADLESS").lower() == "true"
        
        if os.getenv("HCAPTCHA_PROXY_SERVER"):
            config.proxy.enabled = True
            config.proxy.server = os.getenv("HCAPTCHA_PROXY_SERVER", "")
            config.proxy.username = os.getenv("HCAPTCHA_PROXY_USERNAME", "")
            config.proxy.password = os.getenv("HCAPTCHA_PROXY_PASSWORD", "")
        
        if os.getenv("HCAPTCHA_DEBUG"):
            config.debug = os.getenv("HCAPTCHA_DEBUG").lower() == "true"
        
        return config
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of warnings."""
        warnings = []
        
        if not self.steam.username:
            warnings.append("Steam username not set (set STEAM_USERNAME env var)")
        
        if not self.steam.password:
            warnings.append("Steam password not set (set STEAM_PASSWORD env var)")
        
        if self.primary_method == SolverMethod.API_2CAPTCHA:
            if not self.captcha_api.twocaptcha_api_key:
                warnings.append("2Captcha API key not set (set TWOCAPTCHA_API_KEY env var)")
        
        if self.primary_method == SolverMethod.API_ANTICAPTCHA:
            if not self.captcha_api.anticaptcha_api_key:
                warnings.append("AntiCaptcha API key not set (set ANTICAPTCHA_API_KEY env var)")
        
        if self.proxy.enabled and not self.proxy.server:
            warnings.append("Proxy enabled but no server configured")
        
        return warnings


# Default configuration instance
default_config = SolverConfig()
