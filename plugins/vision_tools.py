import time
from pathlib import Path
from core.plugins import BasePlugin, PluginMetadata

class ScreenshotPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="take_screenshot",
            description="Captures the desktop screen and returns an image preview link.",
            version="1.0.0",
            mode="VISION",
            parameters=[]
        )

    async def execute(self, **kwargs):
        static_dir = Path(__file__).resolve().parent.parent / "static" / "screenshots"
        static_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        filename = f"screen_{timestamp}.png"
        filepath = static_dir / filename
        latest_path = static_dir / "latest.png"

        # Attempt 1: mss
        try:
            import mss
            import mss.tools
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(latest_path))

            return {
                "status": "captured",
                "image_url": f"/static/screenshots/{filename}",
                "latest_url": "/static/screenshots/latest.png",
                "resolution": f"{monitor['width']}x{monitor['height']}",
                "note": "Screen captured via mss."
            }
        except Exception as e_mss:
            # Attempt 2: PIL ImageGrab
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                img.save(str(filepath))
                img.save(str(latest_path))
                return {
                    "status": "captured",
                    "image_url": f"/static/screenshots/{filename}",
                    "latest_url": "/static/screenshots/latest.png",
                    "resolution": f"{img.width}x{img.height}",
                    "note": "Screen captured via ImageGrab."
                }
            except Exception as e_pil:
                return {
                    "status": "permission_blocked",
                    "error": f"Interactive desktop session required. Windows GDI blocked headless grab ({e_mss}).",
                    "resolution": "Launch JARVIS in an active desktop session via start_jarvis.bat."
                }
