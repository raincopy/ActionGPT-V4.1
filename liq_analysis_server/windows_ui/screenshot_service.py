from io import BytesIO
class ScreenshotService:
    def __init__(self,artifacts):self.artifacts=artifacts
    def capture(self,wrapper,source):
        image=wrapper.capture_as_image(); buf=BytesIO(); image.save(buf,format="PNG"); return self.artifacts.create_bytes(buf.getvalue(),kind="windows_screenshot",suffix=".png",source=source)

