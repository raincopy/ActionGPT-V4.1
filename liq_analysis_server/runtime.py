from .config import ALLOWED_WEB_HOSTS, WEB_HOSTS_CFG, ensure_data_dirs
from .path_service import PathService
from .task_manager import TaskManager
from .file_service import FileService
from .db_service import DbService
from .artifact_service import ArtifactService
from .verification_service import VerificationService
from .execution.command_builder import CommandBuilder
from .execution.process_registry import ProcessRegistry
from .execution.process_manager import ProcessManager
from .execution.probe_service import ProbeService
from .browser.browser_runtime import BrowserRuntime
from .browser.browser_service import BrowserService
from .windows_ui.window_registry import WindowRegistry
from .windows_ui.screenshot_service import ScreenshotService
from .windows_ui.windows_ui_service import WindowsUIService
from .execution_service import ExecutionService
from .web_host_config import WebHostConfig

path_service=PathService();task_manager=TaskManager();file_service=FileService(path_service);db_service=DbService();artifact_service=ArtifactService();verification_service=VerificationService();command_builder=CommandBuilder(path_service);process_registry=ProcessRegistry();process_manager=ProcessManager(path_service,process_registry,command_builder);web_host_config=WebHostConfig(WEB_HOSTS_CFG,ALLOWED_WEB_HOSTS);probe_service=ProbeService(path_service,process_manager,web_host_config);browser_runtime=BrowserRuntime();browser_service=BrowserService(browser_runtime,artifact_service,probe_service);window_registry=WindowRegistry();screenshot_service=ScreenshotService(artifact_service);windows_ui_service=WindowsUIService(process_manager,window_registry,screenshot_service);execution_service=ExecutionService(task_manager,command_builder,process_manager,probe_service,browser_service,windows_ui_service,artifact_service,verification_service,path_service)
_started=False
def initialize_runtime():
    global _started
    if _started:return
    ensure_data_dirs();task_manager.start();artifact_service.start();process_manager.start();browser_service.start();_started=True
def stop_runtime():
    global _started
    if not _started:return
    browser_service.close();task_manager.stop();_started=False
