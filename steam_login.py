"""
Steam Login Integration.
Handles Steam-specific login flow with hCaptcha solving.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from enum import Enum

from playwright.async_api import Page, BrowserContext

from config import SolverConfig, SteamConfig
from solver import HCaptchaSolver


logger = logging.getLogger(__name__)


class LoginStatus(Enum):
    """Steam login status."""
    SUCCESS = "success"
    CAPTCHA_REQUIRED = "captcha_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    STEAM_GUARD_REQUIRED = "steam_guard_required"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    UNKNOWN = "unknown"


class SteamLoginResult:
    """Result of a Steam login attempt."""
    
    def __init__(
        self,
        status: LoginStatus,
        message: str = "",
        cookies: Optional[Dict[str, str]] = None,
        page_url: Optional[str] = None,
    ):
        self.status = status
        self.message = message
        self.cookies = cookies or {}
        self.page_url = page_url
        self.timestamp = datetime.now()
    
    def __repr__(self):
        return f"SteamLoginResult(status={self.status}, message='{self.message}')"
    
    @property
    def success(self) -> bool:
        return self.status == LoginStatus.SUCCESS


class SteamLogin:
    """
    Steam login handler with integrated hCaptcha solving.
    
    Handles the complete Steam login flow including:
    - Credential entry
    - hCaptcha detection and solving
    - Steam Guard handling
    - Session management
    """
    
    # Steam login selectors
    SELECTORS = {
        "username": "#input_username",
        "password": "#input_password",
        "login_button": "#login_btn_signin button",
        "captcha_container": "#captchagame",
        "captcha_iframe": "iframe[src*='hcaptcha']",
        "error_message": ".error_msg, .login_error",
        "steam_guard_input": "#twofactorcode_entry",
        "steam_guard_submit": "#login_twofactorauth_buttonset_enterasubusedcode button",
        "steam_guard_confirm": "#login_twofactorauth_buttonset_confirm_email button",
        "remember_me": "#remember_login",
        "success_indicator": ".playerAvatar, .userAvatar, #account_pulldown",
        "rate_limit": ".rate_limit_msg, too many attempts",
    }
    
    # Steam login URLs
    URLS = {
        "login": "https://store.steampowered.com/login/",
        "login_mobile": "https://steamcommunity.com/login/",
        "home": "https://store.steampowered.com/",
        "community": "https://steamcommunity.com/",
    }
    
    def __init__(self, config: Optional[SolverConfig] = None):
        self.config = config or SolverConfig()
        self.solver = HCaptchaSolver(self.config)
        self._login_attempts = 0
    
    async def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        steam_guard_code: Optional[str] = None,
    ) -> SteamLoginResult:
        """
        Perform Steam login with hCaptcha solving.
        
        Args:
            username: Steam username (overrides config)
            password: Steam password (overrides config)
            steam_guard_code: Steam Guard 2FA code (if required)
        
        Returns:
            SteamLoginResult with login status
        """
        username = username or self.config.steam.username
        password = password or self.config.steam.password
        
        if not username or not password:
            return SteamLoginResult(
                status=LoginStatus.ERROR,
                message="Username or password not provided"
            )
        
        try:
            # Initialize solver (which initializes browser)
            await self.solver.initialize()
            
            # Navigate to login page
            logger.info(f"Navigating to Steam login: {self.config.steam.login_url}")
            await self.solver.page.goto(
                self.config.steam.login_url,
                wait_until='networkidle',
                timeout=self.config.steam.login_timeout
            )
            
            # Wait for page to load
            await asyncio.sleep(2)
            
            # Fill credentials
            await self._fill_credentials(username, password)
            
            # Submit login
            await self._submit_login()
            
            # Handle post-login state
            result = await self._handle_post_login(steam_guard_code)
            
            return result
        
        except Exception as e:
            logger.error(f"Login failed with exception: {e}")
            return SteamLoginResult(
                status=LoginStatus.ERROR,
                message=str(e)
            )
        
        finally:
            # Don't cleanup if successful (user may want to use the session)
            pass
    
    async def _fill_credentials(self, username: str, password: str):
        """Fill in Steam login credentials."""
        page = self.solver.page
        
        try:
            # Wait for username field
            await page.wait_for_selector(
                self.SELECTORS["username"],
                timeout=10000
            )
            
            # Clear and fill username
            username_field = page.locator(self.SELECTORS["username"])
            await username_field.click()
            await username_field.fill("")
            
            # Type with human-like delays
            for char in username:
                await username_field.type(char, delay=50 + (hash(char) % 50))
            
            await asyncio.sleep(0.5)
            
            # Fill password
            password_field = page.locator(self.SELECTORS["password"])
            await password_field.click()
            await password_field.fill("")
            
            for char in password:
                await password_field.type(char, delay=30 + (hash(char) % 40))
            
            await asyncio.sleep(0.5)
            
            # Check remember me if configured
            try:
                remember = page.locator(self.SELECTORS["remember_me"])
                if await remember.is_visible(timeout=1000):
                    await remember.check()
            except:
                pass
            
            logger.info("Credentials filled successfully")
        
        except Exception as e:
            logger.error(f"Failed to fill credentials: {e}")
            raise
    
    async def _submit_login(self):
        """Click the login button."""
        page = self.solver.page
        
        try:
            login_button = page.locator(self.SELECTORS["login_button"])
            await login_button.click()
            
            # Wait for response
            await asyncio.sleep(3)
            
            logger.info("Login form submitted")
        
        except Exception as e:
            logger.error(f"Failed to submit login: {e}")
            raise
    
    async def _handle_post_login(
        self,
        steam_guard_code: Optional[str] = None
    ) -> SteamLoginResult:
        """Handle the state after login submission."""
        page = self.solver.page
        max_wait = 60
        start = datetime.now()
        
        while (datetime.now() - start).seconds < max_wait:
            current_url = page.url
            
            # Check for successful login
            if await self._is_logged_in():
                logger.info("Login successful!")
                cookies = await self._get_cookies()
                return SteamLoginResult(
                    status=LoginStatus.SUCCESS,
                    message="Login successful",
                    cookies=cookies,
                    page_url=current_url
                )
            
            # Check for captcha
            if await self._has_captcha():
                logger.info("hCaptcha detected, attempting to solve...")
                
                captcha_solved = await self.solver.solve_captcha()
                
                if captcha_solved:
                    logger.info("Captcha solved, waiting for login to proceed...")
                    await asyncio.sleep(3)
                    
                    # Check if login succeeded after captcha
                    if await self._is_logged_in():
                        cookies = await self._get_cookies()
                        return SteamLoginResult(
                            status=LoginStatus.SUCCESS,
                            message="Login successful after captcha",
                            cookies=cookies,
                            page_url=current_url
                        )
                    
                    # May need to re-submit
                    try:
                        await self._submit_login()
                    except:
                        pass
                    
                    await asyncio.sleep(3)
                else:
                    logger.error("Failed to solve captcha")
                    return SteamLoginResult(
                        status=LoginStatus.CAPTCHA_REQUIRED,
                        message="Could not solve hCaptcha"
                    )
            
            # Check for Steam Guard
            if await self._needs_steam_guard():
                logger.info("Steam Guard required")
                
                if steam_guard_code:
                    await self._enter_steam_guard(steam_guard_code)
                    await asyncio.sleep(3)
                else:
                    return SteamLoginResult(
                        status=LoginStatus.STEAM_GUARD_REQUIRED,
                        message="Steam Guard code required"
                    )
            
            # Check for error messages
            error = await self._get_error_message()
            if error:
                if "rate" in error.lower() or "too many" in error.lower():
                    return SteamLoginResult(
                        status=LoginStatus.RATE_LIMITED,
                        message=error
                    )
                elif "invalid" in error.lower() or "incorrect" in error.lower():
                    return SteamLoginResult(
                        status=LoginStatus.INVALID_CREDENTIALS,
                        message=error
                    )
                else:
                    return SteamLoginResult(
                        status=LoginStatus.ERROR,
                        message=error
                    )
            
            await asyncio.sleep(1)
        
        return SteamLoginResult(
            status=LoginStatus.UNKNOWN,
            message="Login timed out"
        )
    
    async def _is_logged_in(self) -> bool:
        """Check if user is logged into Steam."""
        page = self.solver.page
        
        try:
            # Check for success indicators
            for selector in self.SELECTORS["success_indicator"].split(", "):
                try:
                    element = page.locator(selector)
                    if await element.is_visible(timeout=2000):
                        return True
                except:
                    continue
            
            # Check URL
            current_url = page.url
            if "/login" not in current_url and "store.steampowered.com" in current_url:
                return True
            
            return False
        
        except Exception:
            return False
    
    async def _has_captcha(self) -> bool:
        """Check if hCaptcha is present."""
        page = self.solver.page
        
        try:
            for selector in [self.SELECTORS["captcha_container"], self.SELECTORS["captcha_iframe"]]:
                element = page.locator(selector)
                if await element.is_visible(timeout=2000):
                    return True
            return False
        except:
            return False
    
    async def _needs_steam_guard(self) -> bool:
        """Check if Steam Guard code is needed."""
        page = self.solver.page
        
        try:
            guard_input = page.locator(self.SELECTORS["steam_guard_input"])
            return await guard_input.is_visible(timeout=2000)
        except:
            return False
    
    async def _enter_steam_guard(self, code: str):
        """Enter Steam Guard code."""
        page = self.solver.page
        
        try:
            guard_input = page.locator(self.SELECTORS["steam_guard_input"])
            await guard_input.fill(code)
            
            # Submit
            submit = page.locator(
                f'{self.SELECTORS["steam_guard_submit"]}, '
                f'{self.SELECTORS["steam_guard_confirm"]}'
            )
            await submit.click()
            
            logger.info("Steam Guard code submitted")
        
        except Exception as e:
            logger.error(f"Failed to enter Steam Guard code: {e}")
            raise
    
    async def _get_error_message(self) -> Optional[str]:
        """Get error message from login page."""
        page = self.solver.page
        
        try:
            for selector in self.SELECTORS["error_message"].split(", "):
                try:
                    element = page.locator(selector)
                    if await element.is_visible(timeout=1000):
                        text = await element.text_content()
                        if text:
                            return text.strip()
                except:
                    continue
            
            return None
        
        except Exception:
            return None
    
    async def _get_cookies(self) -> Dict[str, str]:
        """Get browser cookies."""
        try:
            cookies = await self.solver.context.cookies()
            return {c["name"]: c["value"] for c in cookies}
        except Exception:
            return {}
    
    async def get_session_data(self) -> Dict[str, Any]:
        """Get current session data for persistence."""
        return {
            "cookies": await self._get_cookies(),
            "url": self.solver.page.url if self.solver.page else None,
            "timestamp": datetime.now().isoformat(),
        }
    
    async def cleanup(self):
        """Clean up resources."""
        await self.solver.cleanup()


class SteamSessionManager:
    """Manages Steam login sessions with persistence."""
    
    def __init__(self, session_dir: str = "/tmp/steam_sessions"):
        self.session_dir = session_dir
        os.makedirs(session_dir, exist_ok=True)
    
    async def save_session(
        self,
        steam_login: SteamLogin,
        session_id: str = "default"
    ):
        """Save current session to disk."""
        import json
        
        session_data = await steam_login.get_session_data()
        filepath = os.path.join(self.session_dir, f"{session_id}.json")
        
        with open(filepath, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        logger.info(f"Session saved to {filepath}")
    
    async def load_session(
        self,
        steam_login: SteamLogin,
        session_id: str = "default"
    ) -> bool:
        """Load session from disk."""
        import json
        
        filepath = os.path.join(self.session_dir, f"{session_id}.json")
        
        if not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, 'r') as f:
                session_data = json.load(f)
            
            # Set cookies
            cookies = session_data.get("cookies", {})
            if cookies and steam_login.solver.context:
                cookie_list = [
                    {"name": k, "value": v, "domain": ".steampowered.com", "path": "/"}
                    for k, v in cookies.items()
                ]
                await steam_login.solver.context.add_cookies(cookie_list)
                
                logger.info(f"Session loaded from {filepath}")
                return True
        
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
        
        return False
    
    def session_exists(self, session_id: str = "default") -> bool:
        """Check if a saved session exists."""
        filepath = os.path.join(self.session_dir, f"{session_id}.json")
        return os.path.exists(filepath)


async def steam_login_with_captcha(
    username: str,
    password: str,
    steam_guard_code: Optional[str] = None,
    config: Optional[SolverConfig] = None,
) -> SteamLoginResult:
    """
    Convenience function for Steam login with hCaptcha solving.
    
    Args:
        username: Steam username
        password: Steam password
        steam_guard_code: Optional Steam Guard 2FA code
        config: Optional solver configuration
    
    Returns:
        SteamLoginResult with login status
    """
    steam = SteamLogin(config)
    
    try:
        result = await steam.login(
            username=username,
            password=password,
            steam_guard_code=steam_guard_code,
        )
        
        return result
    
    finally:
        # Only cleanup on failure
        if not result.success:
            await steam.cleanup()
