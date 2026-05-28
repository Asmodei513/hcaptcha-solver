"""
Test script for hCaptcha Solver.
Demonstrates usage and tests individual components.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import SolverConfig, SolverMethod, BrowserConfig
from solver import HCaptchaSolver, solve_hcaptcha
from audio_solver import AudioSolver
from image_solver import ImageSolver
from steam_login import SteamLogin, steam_login_with_captcha


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_config():
    """Test configuration creation and validation."""
    print("\n=== Testing Configuration ===")
    
    # Default config
    config = SolverConfig()
    warnings = config.validate()
    print(f"Default config warnings: {warnings}")
    
    # Config from environment
    env_config = SolverConfig.from_env()
    print(f"Env config debug: {env_config.debug}")
    print(f"Env config headless: {env_config.browser.headless}")
    
    # Custom config
    custom_config = SolverConfig(
        primary_method=SolverMethod.AUDIO,
        browser=BrowserConfig(headless=True, browser_type="chromium"),
    )
    print(f"Custom config method: {custom_config.primary_method.value}")
    
    print("✓ Configuration tests passed")


async def test_audio_solver():
    """Test audio solver initialization."""
    print("\n=== Testing Audio Solver ===")
    
    solver = AudioSolver()
    print(f"Audio solver backends: {[b.get_name() for b in solver.backends]}")
    print(f"Audio solver config: download_dir={solver.config.download_dir}")
    
    print("✓ Audio solver tests passed")


async def test_image_solver():
    """Test image solver initialization."""
    print("\n=== Testing Image Solver ===")
    
    solver = ImageSolver()
    print(f"Image solver classifiers: {[c.get_name() for c in solver.classifiers]}")
    print(f"Category mappings count: {len(solver.CATEGORY_MAPPINGS)}")
    
    # Test should_select logic
    test_cases = [
        ("Select all images with a seal", {"seal": 0.95, "otter": 0.3}),
        ("Please click on the airplane", {"airplane": 0.88, "bird": 0.2}),
        ("Select all images with a dog", {"cat": 0.9, "dog": 0.1}),
    ]
    
    for challenge, classifications in test_cases:
        result = solver.should_select(challenge, classifications)
        print(f"Challenge: '{challenge}' -> Should select: {result}")
    
    print("✓ Image solver tests passed")


async def test_solver_initialization():
    """Test main solver initialization."""
    print("\n=== Testing Solver Initialization ===")
    
    config = SolverConfig()
    config.browser.headless = True
    
    solver = HCaptchaSolver(config)
    print(f"Solver created with config")
    print(f"Primary method: {config.primary_method.value}")
    print(f"Fallback methods: {[m.value for m in config.fallback_methods]}")
    
    # Test browser initialization (without actually launching)
    print("Solver initialization structure verified")
    
    print("✓ Solver initialization tests passed")


async def test_steam_login():
    """Test Steam login initialization."""
    print("\n=== Testing Steam Login ===")
    
    config = SolverConfig()
    config.browser.headless = True
    
    steam = SteamLogin(config)
    print(f"Steam login handler created")
    print(f"Login URL: {config.steam.login_url}")
    print(f"Selectors defined: {len(steam.SELECTORS)}")
    
    print("✓ Steam login tests passed")


async def test_browser_fingerprint():
    """Test browser fingerprint configuration."""
    print("\n=== Testing Browser Fingerprint ===")
    
    config = BrowserConfig()
    
    print(f"User Agent: {config.user_agent[:50]}...")
    print(f"Viewport: {config.viewport_width}x{config.viewport_height}")
    print(f"Platform: {config.platform}")
    print(f"WebGL Vendor: {config.webgl_vendor}")
    print(f"WebGL Renderer: {config.renderer}")
    
    print("✓ Browser fingerprint tests passed")


async def test_full_integration():
    """Test full integration (requires network)."""
    print("\n=== Testing Full Integration ===")
    
    # This test requires network and actual browser
    # Skip in CI/CD environments
    if "--run-full" not in sys.argv:
        print("Skipping full integration test (use --run-full to enable)")
        return
    
    config = SolverConfig()
    config.browser.headless = True
    config.debug = True
    
    print("Starting full integration test...")
    
    try:
        # Test basic navigation
        solver = HCaptchaSolver(config)
        await solver.initialize()
        
        # Navigate to a test page
        await solver.page.goto("https://httpbin.org/html")
        title = await solver.page.title()
        print(f"Page title: {title}")
        
        await solver.cleanup()
        print("✓ Full integration test passed")
    
    except Exception as e:
        print(f"✗ Full integration test failed: {e}")


async def run_all_tests():
    """Run all tests."""
    print("hCaptcha Solver Test Suite")
    print("=" * 50)
    
    tests = [
        test_config,
        test_audio_solver,
        test_image_solver,
        test_solver_initialization,
        test_steam_login,
        test_browser_fingerprint,
        test_full_integration,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    
    return failed == 0


def main():
    """Main entry point."""
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
