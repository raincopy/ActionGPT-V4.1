from __future__ import annotations

import json
import os
import tkinter as tk
import ctypes
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from .config import SERVER_PORT
from .runtime import (
    artifact_service,
    browser_service,
    db_service,
    file_service,
    path_service,
    process_manager,
    task_manager,
    web_host_config,
    windows_ui_service,
)


EXCLUDED_NAMES = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
}


class ActionEditorUI:
    """관리 UI.

    기존 파일 탐색/상세/작업 목록 흐름을 유지하면서 확장 기능을 별도 탭으로 제공한다.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Liq-analysis Action GPT v0.2.0")
        self.root.geometry("1450x850")
        self.root.minsize(1100, 680)
        self._apply_dark_title_bar()

        self.status = tk.StringVar()
        self._update_root_status()
        self.file_path_var = tk.StringVar(value="선택 항목 없음")
        self._file_items: dict[str, dict[str, Any]] = {}
        self._refreshing = False
        self._task_refresh_pending = False

        self._configure_style()
        self._build_header()
        self._build_tabs()
        self._load_file_root()
        self.refresh()
        task_manager.subscribe(self._on_task_records_changed)
        self.root.bind("<Destroy>", self._on_destroy, add="+")

    def _configure_style(self) -> None:
        self.color_bg = "#1f1f1f"
        self.color_panel = "#2b2b2b"
        self.color_panel_alt = "#252525"
        self.color_border = "#5a5a5a"
        self.color_text = "#f2f2f2"
        self.color_muted = "#c8c8c8"
        self.color_selection = "#0b66d5"
        self.root.configure(background=self.color_bg)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=self.color_bg, foreground=self.color_text, fieldbackground=self.color_panel)
        style.configure("TFrame", background=self.color_bg)
        style.configure("TLabel", background=self.color_bg, foreground=self.color_text)
        style.configure("TLabelframe", background=self.color_bg, foreground=self.color_text, bordercolor=self.color_border, lightcolor=self.color_border, darkcolor=self.color_border)
        style.configure("TLabelframe.Label", background=self.color_bg, foreground=self.color_text)
        style.configure("TButton", background=self.color_panel_alt, foreground=self.color_text, bordercolor=self.color_border, padding=(9, 5))
        style.map("TButton", background=[("active", "#353535"), ("pressed", "#181818")], foreground=[("disabled", "#808080"), ("!disabled", self.color_text)])
        style.configure("Treeview", background=self.color_panel, fieldbackground=self.color_panel, foreground=self.color_text, bordercolor=self.color_border, rowheight=24, font=("맑은 고딕", 9))
        style.map("Treeview", background=[("selected", self.color_selection)], foreground=[("selected", "#ffffff")])
        style.configure("Treeview.Heading", background=self.color_panel_alt, foreground=self.color_text, bordercolor=self.color_border, font=("맑은 고딕", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", "#353535")])
        style.configure("TNotebook", background=self.color_bg, bordercolor=self.color_border)
        style.configure("TNotebook.Tab", background=self.color_panel_alt, foreground=self.color_muted, bordercolor=self.color_border, padding=(12, 6), font=("맑은 고딕", 9))
        style.map("TNotebook.Tab", background=[("selected", self.color_bg), ("active", "#353535")], foreground=[("selected", "#ffffff"), ("active", "#ffffff")])
        style.configure("TScrollbar", background=self.color_panel_alt, troughcolor=self.color_bg, bordercolor=self.color_border, arrowcolor=self.color_text)
        style.configure("Header.TLabel", background=self.color_bg, foreground=self.color_text, font=("맑은 고딕", 9))
        style.configure("Section.TLabel", background=self.color_bg, foreground=self.color_text, font=("맑은 고딕", 9, "bold"))

    def _apply_dark_title_bar(self) -> None:
        if os.name != "nt":
            return
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            enabled = ctypes.c_int(1)
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled)
            )
            if result != 0:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 19, ctypes.byref(enabled), ctypes.sizeof(enabled)
                )
        except Exception:
            pass

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, padding=(8, 7))
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.status, style="Header.TLabel").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(header, text="전체 새로고침", command=self.refresh).pack(side="right")

    def _build_tabs(self) -> None:
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._build_work_tab()
        self._build_root_management_tab()
        self._build_process_tab()
        self._build_browser_tab()
        self._build_windows_tab()
        self._build_artifact_tab()

    def _build_work_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=4)
        self.tabs.add(tab, text="파일·작업")

        panes = ttk.Panedwindow(tab, orient="horizontal")
        panes.pack(fill="both", expand=True)

        file_frame = ttk.Labelframe(panes, text="Liq-Map 파일 구조", padding=5)
        detail_frame = ttk.Labelframe(panes, text="선택 항목 상세", padding=5)
        task_frame = ttk.Labelframe(panes, text="작업 진행 목록", padding=5)
        panes.add(file_frame, weight=4)
        panes.add(detail_frame, weight=3)
        panes.add(task_frame, weight=4)

        file_toolbar = ttk.Frame(file_frame)
        file_toolbar.pack(fill="x", pady=(0, 5))
        ttk.Button(file_toolbar, text="루트 새로고침", command=self._load_file_root).pack(
            side="left"
        )
        ttk.Button(file_toolbar, text="선택 파일 열기", command=self.open_selected_file).pack(
            side="left", padx=(6, 0)
        )

        file_tree_wrap = ttk.Frame(file_frame)
        file_tree_wrap.pack(fill="both", expand=True)
        self.file_tree = ttk.Treeview(
            file_tree_wrap,
            columns=("path",),
            show="tree headings",
            selectmode="browse",
        )
        self.file_tree.heading("#0", text="이름", anchor="w")
        self.file_tree.heading("path", text="경로", anchor="w")
        self.file_tree.column("#0", width=190, minwidth=120, stretch=True)
        self.file_tree.column("path", width=190, minwidth=120, stretch=True)
        file_y = ttk.Scrollbar(file_tree_wrap, orient="vertical", command=self.file_tree.yview)
        file_x = ttk.Scrollbar(file_tree_wrap, orient="horizontal", command=self.file_tree.xview)
        self.file_tree.configure(yscrollcommand=file_y.set, xscrollcommand=file_x.set)
        self.file_tree.grid(row=0, column=0, sticky="nsew")
        file_y.grid(row=0, column=1, sticky="ns")
        file_x.grid(row=1, column=0, sticky="ew")
        file_tree_wrap.rowconfigure(0, weight=1)
        file_tree_wrap.columnconfigure(0, weight=1)
        self.file_tree.bind("<<TreeviewOpen>>", self._on_file_open)
        self.file_tree.bind("<<TreeviewSelect>>", self._on_file_select)
        self.file_tree.bind("<Double-1>", self._on_file_double_click)

        ttk.Label(detail_frame, textvariable=self.file_path_var).pack(fill="x", pady=(0, 5))
        detail_wrap = ttk.Frame(detail_frame)
        detail_wrap.pack(fill="both", expand=True)
        self.file_detail = tk.Text(
            detail_wrap,
            wrap="none",
            undo=False,
            font=("Consolas", 10),
            relief="solid",
            borderwidth=1,
            background=self.color_panel,
            foreground=self.color_text,
            insertbackground=self.color_text,
            selectbackground=self.color_selection,
            selectforeground="#ffffff",
            highlightbackground=self.color_border,
            highlightcolor=self.color_border,
        )
        detail_y = ttk.Scrollbar(detail_wrap, orient="vertical", command=self.file_detail.yview)
        detail_x = ttk.Scrollbar(detail_wrap, orient="horizontal", command=self.file_detail.xview)
        self.file_detail.configure(yscrollcommand=detail_y.set, xscrollcommand=detail_x.set)
        self.file_detail.grid(row=0, column=0, sticky="nsew")
        detail_y.grid(row=0, column=1, sticky="ns")
        detail_x.grid(row=1, column=0, sticky="ew")
        detail_wrap.rowconfigure(0, weight=1)
        detail_wrap.columnconfigure(0, weight=1)

        task_toolbar = ttk.Frame(task_frame)
        task_toolbar.pack(fill="x", pady=(0, 5))
        ttk.Button(task_toolbar, text="작업 새로고침", command=self.refresh).pack(side="left")
        ttk.Button(task_toolbar, text="완료 기록 삭제", command=self._clear_completed_notice).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(task_toolbar, text="실패 기록 삭제", command=self._clear_failed_notice).pack(
            side="left", padx=(6, 0)
        )

        task_wrap = ttk.Frame(task_frame)
        task_wrap.pack(fill="both", expand=True)
        self.task_tree = ttk.Treeview(
            task_wrap,
            columns=("started", "api", "command", "status", "progress"),
            show="headings",
            selectmode="browse",
        )
        headings = {
            "started": "요청 시작",
            "api": "API",
            "command": "명령",
            "status": "상태",
            "progress": "진행",
        }
        widths = {"started": 145, "api": 95, "command": 150, "status": 90, "progress": 55}
        for column, title in headings.items():
            self.task_tree.heading(column, text=title, anchor="w")
            self.task_tree.column(column, width=widths[column], minwidth=45, stretch=column in {"started", "command"})
        task_y = ttk.Scrollbar(task_wrap, orient="vertical", command=self.task_tree.yview)
        task_x = ttk.Scrollbar(task_wrap, orient="horizontal", command=self.task_tree.xview)
        self.task_tree.configure(yscrollcommand=task_y.set, xscrollcommand=task_x.set)
        self.task_tree.grid(row=0, column=0, sticky="nsew")
        task_y.grid(row=0, column=1, sticky="ns")
        task_x.grid(row=1, column=0, sticky="ew")
        task_wrap.rowconfigure(0, weight=1)
        task_wrap.columnconfigure(0, weight=1)
        self.task_tree.bind("<<TreeviewSelect>>", self._on_task_select)

    def _build_root_management_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=7)
        self.tabs.add(tab, text="Dir_DB")

        pane = ttk.Panedwindow(tab, orient="vertical")
        pane.pack(fill="both", expand=True)
        directory_frame = ttk.Labelframe(pane, text="디렉토리 관리", padding=6)
        database_frame = ttk.Labelframe(pane, text="DB 연결 관리", padding=6)
        web_host_frame = ttk.Labelframe(pane, text="URL 허용 호스트 관리", padding=6)
        pane.add(directory_frame, weight=3)
        pane.add(database_frame, weight=2)
        pane.add(web_host_frame, weight=2)

        toolbar = ttk.Frame(directory_frame)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="새로고침", command=self._load_root_manager).pack(side="left")
        ttk.Button(toolbar, text="루트 추가", command=self.add_file_root).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="선택 루트 수정", command=self.edit_file_root).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="선택 루트 삭제", command=self.delete_file_root).pack(side="left", padx=(6, 0))

        ttk.Label(
            directory_frame,
            text="첫 번째 루트가 상대 경로의 기본 루트입니다. 추가 루트는 절대 경로로 사용할 수 있습니다.",
            style="Section.TLabel",
        ).pack(fill="x", pady=(0, 6))

        list_wrap = ttk.Frame(directory_frame)
        list_wrap.pack(fill="both", expand=True)
        self.root_manager_tree = ttk.Treeview(
            list_wrap,
            columns=("order", "path"),
            show="headings",
            selectmode="browse",
        )
        self.root_manager_tree.heading("order", text="순서", anchor="w")
        self.root_manager_tree.heading("path", text="등록 디렉토리", anchor="w")
        self.root_manager_tree.column("order", width=80, minwidth=60, stretch=False)
        self.root_manager_tree.column("path", width=1000, minwidth=300, stretch=True)
        ybar = ttk.Scrollbar(list_wrap, orient="vertical", command=self.root_manager_tree.yview)
        xbar = ttk.Scrollbar(list_wrap, orient="horizontal", command=self.root_manager_tree.xview)
        self.root_manager_tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.root_manager_tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        list_wrap.rowconfigure(0, weight=1)
        list_wrap.columnconfigure(0, weight=1)

        db_toolbar = ttk.Frame(database_frame)
        db_toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(db_toolbar, text="새로고침", command=self._load_db_manager).pack(side="left")
        ttk.Button(db_toolbar, text="DB 추가", command=self.add_db_connection).pack(side="left", padx=(6, 0))
        ttk.Button(db_toolbar, text="선택 DB 수정", command=self.edit_db_connection).pack(side="left", padx=(6, 0))
        ttk.Button(db_toolbar, text="선택 DB 삭제", command=self.delete_db_connection).pack(side="left", padx=(6, 0))

        ttk.Label(
            database_frame,
            text="마우스 오른쪽 버튼으로 기본 DB를 지정합니다. DB_API는 기본으로 표시된 DB에만 접근합니다.",
            style="Section.TLabel",
        ).pack(fill="x", pady=(0, 6))

        db_wrap = ttk.Frame(database_frame)
        db_wrap.pack(fill="both", expand=True)
        db_columns = ("order", "id", "host", "port", "dbname", "user", "sslmode")
        self.db_manager_tree = ttk.Treeview(db_wrap, columns=db_columns, show="headings", selectmode="browse")
        db_headings = {
            "order": "순서", "id": "DB ID", "host": "호스트", "port": "포트",
            "dbname": "DB 이름", "user": "사용자", "sslmode": "SSL",
        }
        db_widths = {"order": 70, "id": 130, "host": 180, "port": 80, "dbname": 180, "user": 170, "sslmode": 100}
        for column in db_columns:
            self.db_manager_tree.heading(column, text=db_headings[column], anchor="w")
            self.db_manager_tree.column(column, width=db_widths[column], minwidth=55, stretch=column in {"host", "dbname", "user"})
        db_y = ttk.Scrollbar(db_wrap, orient="vertical", command=self.db_manager_tree.yview)
        db_x = ttk.Scrollbar(db_wrap, orient="horizontal", command=self.db_manager_tree.xview)
        self.db_manager_tree.configure(yscrollcommand=db_y.set, xscrollcommand=db_x.set)
        self.db_manager_tree.grid(row=0, column=0, sticky="nsew")
        db_y.grid(row=0, column=1, sticky="ns")
        db_x.grid(row=1, column=0, sticky="ew")
        db_wrap.rowconfigure(0, weight=1)
        db_wrap.columnconfigure(0, weight=1)
        self.db_context_menu = tk.Menu(
            self.root,
            tearoff=False,
            background=self.color_panel,
            foreground=self.color_text,
            activebackground=self.color_selection,
            activeforeground="#ffffff",
        )
        self.db_context_menu.add_command(label="기본 DB로 설정", command=self.set_selected_db_default)
        self.db_manager_tree.bind("<Button-3>", self._show_db_context_menu)

        host_toolbar = ttk.Frame(web_host_frame)
        host_toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(host_toolbar, text="새로고침", command=self._load_web_host_manager).pack(side="left")
        ttk.Button(host_toolbar, text="URL/호스트 추가", command=self.add_web_host).pack(side="left", padx=(6, 0))
        ttk.Button(host_toolbar, text="선택 항목 수정", command=self.edit_web_host).pack(side="left", padx=(6, 0))
        ttk.Button(host_toolbar, text="선택 항목 삭제", command=self.delete_web_host).pack(side="left", padx=(6, 0))

        ttk.Label(
            web_host_frame,
            text="URL을 입력해도 호스트명만 저장됩니다. 같은 호스트의 모든 경로와 포트가 허용됩니다.",
            style="Section.TLabel",
        ).pack(fill="x", pady=(0, 6))

        host_wrap = ttk.Frame(web_host_frame)
        host_wrap.pack(fill="both", expand=True)
        self.web_host_tree = ttk.Treeview(
            host_wrap, columns=("order", "host"), show="headings", selectmode="browse"
        )
        self.web_host_tree.heading("order", text="순서", anchor="w")
        self.web_host_tree.heading("host", text="허용 호스트", anchor="w")
        self.web_host_tree.column("order", width=80, minwidth=60, stretch=False)
        self.web_host_tree.column("host", width=1000, minwidth=300, stretch=True)
        host_y = ttk.Scrollbar(host_wrap, orient="vertical", command=self.web_host_tree.yview)
        host_x = ttk.Scrollbar(host_wrap, orient="horizontal", command=self.web_host_tree.xview)
        self.web_host_tree.configure(yscrollcommand=host_y.set, xscrollcommand=host_x.set)
        self.web_host_tree.grid(row=0, column=0, sticky="nsew")
        host_y.grid(row=0, column=1, sticky="ns")
        host_x.grid(row=1, column=0, sticky="ew")
        host_wrap.rowconfigure(0, weight=1)
        host_wrap.columnconfigure(0, weight=1)
        self._load_root_manager()
        self._load_db_manager()
        self._load_web_host_manager()

    def _build_process_tab(self) -> None:
        self.process_tree, self.process_detail = self._build_list_tab(
            "프로세스",
            ("id", "pid", "status", "path", "started"),
            {"id": "ID", "pid": "PID", "status": "상태", "path": "경로", "started": "시작"},
            {"id": 145, "pid": 80, "status": 100, "path": 650, "started": 170},
            self._process_object,
            (
                ("선택 프로세스 종료", self.stop_process),
                ("선택 이력 삭제", self.delete_selected_process_record),
                ("종료 이력 전체 삭제", self.delete_finished_process_records),
            ),
        )

    def _build_browser_tab(self) -> None:
        self.browser_tree, self.browser_detail = self._build_list_tab(
            "브라우저",
            ("id", "url", "title", "errors"),
            {"id": "ID", "url": "URL", "title": "제목", "errors": "오류"},
            {"id": 160, "url": 650, "title": 250, "errors": 70},
            self._browser_object,
        )

    def _build_windows_tab(self) -> None:
        self.windows_tree, self.windows_detail = self._build_list_tab(
            "Windows UI",
            ("id", "pid", "title", "status"),
            {"id": "ID", "pid": "PID", "title": "제목", "status": "상태"},
            {"id": 160, "pid": 80, "title": 700, "status": 120},
            self._windows_object,
        )

    def _build_artifact_tab(self) -> None:
        self.artifact_tree, self.artifact_detail = self._build_list_tab(
            "아티팩트",
            ("id", "type", "size", "created"),
            {"id": "ID", "type": "종류", "size": "크기", "created": "생성"},
            {"id": 170, "type": 120, "size": 100, "created": 190},
            self._artifact_object,
            (("선택 아티팩트 열기", self.open_artifact),),
        )

    def _build_list_tab(
        self,
        title: str,
        columns: tuple[str, ...],
        headings: dict[str, str],
        widths: dict[str, int],
        resolver,
        buttons: tuple[tuple[str, Any], ...] = (),
    ) -> tuple[ttk.Treeview, tk.Text]:
        tab = ttk.Frame(self.tabs, padding=7)
        self.tabs.add(tab, text=title)

        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="새로고침", command=self.refresh).pack(side="left")
        for label, command in buttons:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(6, 0))

        pane = ttk.Panedwindow(tab, orient="vertical")
        pane.pack(fill="both", expand=True)
        list_frame = ttk.Frame(pane)
        detail_frame = ttk.Labelframe(pane, text="선택 항목 상세", padding=5)
        pane.add(list_frame, weight=4)
        pane.add(detail_frame, weight=2)

        tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        for column in columns:
            tree.heading(column, text=headings[column], anchor="w")
            tree.column(column, width=widths[column], minwidth=55, stretch=column in {"path", "url", "title"})
        ybar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(list_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        detail_wrap = ttk.Frame(detail_frame)
        detail_wrap.pack(fill="both", expand=True)
        detail = tk.Text(
            detail_wrap,
            wrap="none",
            font=("Consolas", 9),
            relief="solid",
            borderwidth=1,
            background=self.color_panel,
            foreground=self.color_text,
            insertbackground=self.color_text,
            selectbackground=self.color_selection,
            selectforeground="#ffffff",
            highlightbackground=self.color_border,
            highlightcolor=self.color_border,
        )
        detail_y = ttk.Scrollbar(detail_wrap, orient="vertical", command=detail.yview)
        detail_x = ttk.Scrollbar(detail_wrap, orient="horizontal", command=detail.xview)
        detail.configure(yscrollcommand=detail_y.set, xscrollcommand=detail_x.set)
        detail.grid(row=0, column=0, sticky="nsew")
        detail_y.grid(row=0, column=1, sticky="ns")
        detail_x.grid(row=1, column=0, sticky="ew")
        detail_wrap.rowconfigure(0, weight=1)
        detail_wrap.columnconfigure(0, weight=1)
        tree.bind("<<TreeviewSelect>>", lambda event: self._show_resolved_detail(tree, detail, resolver))
        return tree, detail

    def _load_file_root(self) -> None:
        selected_path = self._selected_file_path()
        self.file_tree.delete(*self.file_tree.get_children())
        self._file_items.clear()
        result = file_service.list_root()
        for root_item in result.get("children", []):
            root_path = str(root_item.get("absolute_path") or root_item.get("path", ""))
            name = Path(root_path).name or root_path
            item = {
                **root_item,
                "path": root_path,
                "absolute_path": root_path,
                "is_registered_root": True,
            }
            root_id = self.file_tree.insert("", "end", text=name, values=(root_path,), open=True)
            self._file_items[root_id] = item
            self._load_directory_children(root_id, root_path)
        self._update_root_status()
        self._load_root_manager()
        if selected_path:
            self._select_visible_path(selected_path)

    def _update_root_status(self) -> None:
        roots = path_service.roots
        primary = roots[0] if roots else "없음"
        self.status.set(
            f"서버 http://127.0.0.1:{SERVER_PORT} | 작업 루트 {len(roots)}개 | 기본 {primary}"
        )

    def _load_root_manager(self) -> None:
        if not hasattr(self, "root_manager_tree"):
            return
        selected = self._selected_registered_root()
        self.root_manager_tree.delete(*self.root_manager_tree.get_children())
        selected_id = None
        for index, root in enumerate(path_service.roots, start=1):
            item_id = self.root_manager_tree.insert(
                "", "end", values=("기본" if index == 1 else index, str(root))
            )
            if selected == str(root):
                selected_id = item_id
        if selected_id:
            self.root_manager_tree.selection_set(selected_id)
            self.root_manager_tree.see(selected_id)

    def _selected_registered_root(self) -> str | None:
        if not hasattr(self, "root_manager_tree"):
            return None
        selection = self.root_manager_tree.selection()
        if not selection:
            return None
        values = self.root_manager_tree.item(selection[0], "values")
        return str(values[1]) if len(values) > 1 else None

    def add_file_root(self) -> None:
        selected = filedialog.askdirectory(title="추가할 작업 루트 선택", mustexist=True)
        if not selected:
            return
        try:
            path_service.add_root(selected)
            self._load_file_root()
        except Exception as exc:
            messagebox.showerror("루트 추가 실패", str(exc))

    def edit_file_root(self) -> None:
        current = self._selected_registered_root()
        if not current:
            messagebox.showinfo("루트 수정", "수정할 등록 루트를 먼저 선택하십시오.")
            return
        selected = filedialog.askdirectory(
            title="변경할 작업 루트 선택", initialdir=current, mustexist=True
        )
        if not selected:
            return
        try:
            path_service.update_root(current, selected)
            self._load_file_root()
        except Exception as exc:
            messagebox.showerror("루트 수정 실패", str(exc))

    def delete_file_root(self) -> None:
        current = self._selected_registered_root()
        if not current:
            messagebox.showinfo("루트 삭제", "삭제할 등록 루트를 먼저 선택하십시오.")
            return
        if not messagebox.askyesno("루트 삭제", f"등록 목록에서 삭제하시겠습니까?\n{current}"):
            return
        try:
            path_service.remove_root(current)
            self._load_file_root()
        except Exception as exc:
            messagebox.showerror("루트 삭제 실패", str(exc))

    def _load_web_host_manager(self) -> None:
        if not hasattr(self, "web_host_tree"):
            return
        selected = self._selected_web_host()
        try:
            hosts = web_host_config.reload()
        except Exception as exc:
            messagebox.showerror("URL 허용 설정 읽기 실패", str(exc))
            return
        self.web_host_tree.delete(*self.web_host_tree.get_children())
        selected_id = None
        for index, host in enumerate(hosts, start=1):
            item_id = self.web_host_tree.insert("", "end", values=(index, host))
            if selected == host:
                selected_id = item_id
        if selected_id:
            self.web_host_tree.selection_set(selected_id)
            self.web_host_tree.see(selected_id)

    def _selected_web_host(self) -> str | None:
        if not hasattr(self, "web_host_tree"):
            return None
        selection = self.web_host_tree.selection()
        if not selection:
            return None
        values = self.web_host_tree.item(selection[0], "values")
        return str(values[1]) if len(values) > 1 else None

    def add_web_host(self) -> None:
        value = simpledialog.askstring(
            "URL/호스트 추가",
            "허용할 URL 또는 호스트명을 입력하십시오.",
            parent=self.root,
        )
        if value is None:
            return
        try:
            web_host_config.add(value)
            self._load_web_host_manager()
        except Exception as exc:
            messagebox.showerror("URL/호스트 추가 실패", str(exc))

    def edit_web_host(self) -> None:
        current = self._selected_web_host()
        if not current:
            messagebox.showinfo("URL/호스트 수정", "수정할 허용 호스트를 먼저 선택하십시오.")
            return
        value = simpledialog.askstring(
            "URL/호스트 수정",
            "변경할 URL 또는 호스트명을 입력하십시오.",
            initialvalue=current,
            parent=self.root,
        )
        if value is None:
            return
        try:
            web_host_config.update(current, value)
            self._load_web_host_manager()
        except Exception as exc:
            messagebox.showerror("URL/호스트 수정 실패", str(exc))

    def delete_web_host(self) -> None:
        current = self._selected_web_host()
        if not current:
            messagebox.showinfo("URL/호스트 삭제", "삭제할 허용 호스트를 먼저 선택하십시오.")
            return
        if not messagebox.askyesno("URL/호스트 삭제", f"허용 목록에서 삭제하시겠습니까?\n{current}"):
            return
        try:
            web_host_config.remove(current)
            self._load_web_host_manager()
        except Exception as exc:
            messagebox.showerror("URL/호스트 삭제 실패", str(exc))

    def _load_db_manager(self) -> None:
        if not hasattr(self, "db_manager_tree"):
            return
        selected = self._selected_db_connection_id()
        try:
            items = db_service.connections.reload()
        except Exception as exc:
            messagebox.showerror("DB 설정 읽기 실패", str(exc))
            return
        self.db_manager_tree.delete(*self.db_manager_tree.get_children())
        selected_id = None
        for index, item in enumerate(items, start=1):
            item_id = self.db_manager_tree.insert(
                "",
                "end",
                values=(
                    "기본" if item["id"] == db_service.connections.default_id else index,
                    item["id"], item["host"], item["port"], item["dbname"],
                    item["user"], item.get("sslmode", "prefer"),
                ),
            )
            if selected == item["id"]:
                selected_id = item_id
        if selected_id:
            self.db_manager_tree.selection_set(selected_id)
            self.db_manager_tree.see(selected_id)

    def _show_db_context_menu(self, event) -> None:
        item_id = self.db_manager_tree.identify_row(event.y)
        if not item_id:
            return
        self.db_manager_tree.selection_set(item_id)
        self.db_manager_tree.focus(item_id)
        try:
            self.db_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.db_context_menu.grab_release()

    def set_selected_db_default(self) -> None:
        connection_id = self._selected_db_connection_id()
        if not connection_id:
            return
        try:
            db_service.connections.set_default(connection_id)
            self._load_db_manager()
        except Exception as exc:
            messagebox.showerror("기본 DB 변경 실패", str(exc))

    def _selected_db_connection_id(self) -> str | None:
        if not hasattr(self, "db_manager_tree"):
            return None
        selection = self.db_manager_tree.selection()
        if not selection:
            return None
        values = self.db_manager_tree.item(selection[0], "values")
        return str(values[1]) if len(values) > 1 else None

    def add_db_connection(self) -> None:
        values = self._db_connection_dialog(
            "DB 연결 추가",
            {"id": "", "host": "127.0.0.1", "port": 5432, "dbname": "", "user": "", "password": "", "sslmode": "prefer"},
        )
        if values is None:
            return
        try:
            db_service.connections.add(values)
            self._load_db_manager()
        except Exception as exc:
            messagebox.showerror("DB 추가 실패", str(exc))

    def edit_db_connection(self) -> None:
        connection_id = self._selected_db_connection_id()
        if not connection_id:
            messagebox.showinfo("DB 수정", "수정할 DB 연결을 먼저 선택하십시오.")
            return
        try:
            current = db_service.connections.get(connection_id)
        except Exception as exc:
            messagebox.showerror("DB 설정 읽기 실패", str(exc))
            return
        values = self._db_connection_dialog("DB 연결 수정", current)
        if values is None:
            return
        try:
            db_service.connections.update(connection_id, values)
            self._load_db_manager()
        except Exception as exc:
            messagebox.showerror("DB 수정 실패", str(exc))

    def delete_db_connection(self) -> None:
        connection_id = self._selected_db_connection_id()
        if not connection_id:
            messagebox.showinfo("DB 삭제", "삭제할 DB 연결을 먼저 선택하십시오.")
            return
        if not messagebox.askyesno("DB 삭제", f"등록 목록에서 삭제하시겠습니까?\n{connection_id}"):
            return
        try:
            db_service.connections.remove(connection_id)
            self._load_db_manager()
        except Exception as exc:
            messagebox.showerror("DB 삭제 실패", str(exc))

    def _db_connection_dialog(self, title: str, initial: dict[str, Any]) -> dict[str, Any] | None:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.configure(background=self.color_bg)
        dialog.transient(self.root)
        dialog.resizable(False, False)

        fields = (
            ("id", "DB ID"), ("host", "호스트"), ("port", "포트"),
            ("dbname", "DB 이름"), ("user", "사용자"),
            ("password", "비밀번호"), ("sslmode", "SSL 모드"),
        )
        variables: dict[str, tk.StringVar] = {}
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        first_entry = None
        for row, (key, label) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            variable = tk.StringVar(value=str(initial.get(key, "")))
            variables[key] = variable
            entry = ttk.Entry(body, textvariable=variable, width=42, show="*" if key == "password" else "")
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            if first_entry is None:
                first_entry = entry

        result: dict[str, Any] | None = None

        def save() -> None:
            nonlocal result
            try:
                port = int(variables["port"].get().strip())
            except ValueError:
                messagebox.showerror("입력 오류", "포트는 숫자여야 합니다.", parent=dialog)
                return
            result = {key: variable.get().strip() for key, variable in variables.items()}
            result["port"] = port
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="저장", command=save).pack(side="left")
        ttk.Button(buttons, text="취소", command=dialog.destroy).pack(side="left", padx=(6, 0))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.bind("<Return>", lambda _event: save())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()
        if first_entry is not None:
            first_entry.focus_set()
        self.root.wait_window(dialog)
        return result

    def _load_directory_children(self, parent_id: str, relative_path: str) -> None:
        for child_id in self.file_tree.get_children(parent_id):
            self.file_tree.delete(child_id)
            self._file_items.pop(child_id, None)
        try:
            result = file_service.list_directory(relative_path)
        except Exception as exc:
            error_id = self.file_tree.insert(parent_id, "end", text=f"<읽기 실패: {exc}>", values=(relative_path,))
            self._file_items[error_id] = {"name": str(exc), "path": relative_path, "type": "error"}
            return

        for child in result.get("children", []):
            name = str(child.get("name", ""))
            if self._is_excluded(name):
                continue
            item_id = self.file_tree.insert(
                parent_id,
                "end",
                text=name,
                values=(child.get("path", ""),),
            )
            self._file_items[item_id] = child
            if child.get("type") == "directory":
                self.file_tree.insert(item_id, "end", text="", values=("",), tags=("dummy",))

    def _is_excluded(self, name: str) -> bool:
        lower = name.lower()
        return (
            name in EXCLUDED_NAMES
            or lower.endswith((".pyc", ".pyo"))
            or "_org_" in lower
        )

    def _on_file_open(self, _event=None) -> None:
        selection = self.file_tree.selection()
        if not selection:
            return
        item_id = selection[0]
        item = self._file_items.get(item_id, {})
        if item.get("type") != "directory":
            return
        children = self.file_tree.get_children(item_id)
        if len(children) == 1 and "dummy" in self.file_tree.item(children[0], "tags"):
            self._load_directory_children(item_id, str(item.get("path", ".")))

    def _on_file_select(self, _event=None) -> None:
        selection = self.file_tree.selection()
        if not selection:
            return
        item = self._file_items.get(selection[0])
        if not item:
            return
        path = str(item.get("path", "."))
        self.file_path_var.set(path)
        if item.get("type") == "file":
            try:
                result = file_service.read_file(path, max_chars=1_000_000)
                text = result.get("text", "")
                if result.get("truncated"):
                    text += "\n\n[표시 한도에 따라 내용이 잘렸습니다.]"
                self._set_text(self.file_detail, text)
            except Exception as exc:
                self._set_text(self.file_detail, json.dumps({"path": path, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            self._set_text(self.file_detail, json.dumps(item, ensure_ascii=False, indent=2, default=str))

    def _on_file_double_click(self, _event=None) -> None:
        selection = self.file_tree.selection()
        if not selection:
            return
        item = self._file_items.get(selection[0], {})
        if item.get("type") == "file":
            self.open_selected_file()

    def open_selected_file(self) -> None:
        path = self._selected_file_path()
        if not path:
            return
        item = self._file_items.get(self.file_tree.selection()[0], {})
        if item.get("type") != "file":
            return
        try:
            absolute = path_service.resolve(path, must_exist=True)
            os.startfile(str(absolute))
        except Exception as exc:
            messagebox.showerror("파일 열기 실패", str(exc))

    def _selected_file_path(self) -> str | None:
        selection = self.file_tree.selection() if hasattr(self, "file_tree") else ()
        if not selection:
            return None
        item = self._file_items.get(selection[0])
        return str(item.get("path")) if item else None

    def _select_visible_path(self, path: str) -> None:
        for item_id, item in self._file_items.items():
            if item.get("path") == path:
                self.file_tree.selection_set(item_id)
                self.file_tree.see(item_id)
                return

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._refresh_tasks()
            self._refresh_processes()
            self._refresh_browsers()
            self._refresh_windows()
            self._refresh_artifacts()
        finally:
            self._refreshing = False

    def _refresh_tasks(self) -> None:
        selected = self._selected_iid(self.task_tree)
        rows = []
        for item in task_manager.list():
            rows.append(
                (
                    item["task_id"],
                    (
                        item.get("requested_at")
                        or item.get("started_at")
                        or item.get("created_at")
                        or ""
                    ),
                    item.get("api_name", ""),
                    item.get("command_code", ""),
                    item.get("status", ""),
                    item.get("progress", ""),
                )
            )
        self._replace_rows(self.task_tree, rows, selected)

    def _refresh_processes(self) -> None:
        selected = self._selected_iid(self.process_tree)
        rows = [
            (
                item["process_id"],
                self._short_id(item["process_id"]),
                item.get("pid", ""),
                item.get("status", ""),
                item.get("path", ""),
                item.get("started_at", ""),
            )
            for item in process_manager.list()
        ]
        self._replace_rows(self.process_tree, rows, selected)

    def _refresh_browsers(self) -> None:
        selected = self._selected_iid(self.browser_tree)
        rows = []
        for session_id, value in browser_service.sessions.items():
            page = value.get("page")
            rows.append(
                (
                    session_id,
                    self._short_id(session_id),
                    getattr(page, "url", ""),
                    value.get("title", "Playwright"),
                    len(value.get("console", [])) + len(value.get("network", [])),
                )
            )
        self._replace_rows(self.browser_tree, rows, selected)

    def _refresh_windows(self) -> None:
        selected = self._selected_iid(self.windows_tree)
        rows = []
        for item in windows_ui_service.registry.windows.values():
            try:
                title = item["wrapper"].window_text()
            except Exception:
                title = ""
            rows.append(
                (
                    item["window_id"],
                    self._short_id(item["window_id"]),
                    item.get("pid", ""),
                    title,
                    item.get("status", "관리"),
                )
            )
        self._replace_rows(self.windows_tree, rows, selected)

    def _refresh_artifacts(self) -> None:
        selected = self._selected_iid(self.artifact_tree)
        rows = [
            (
                item["artifact_id"],
                self._short_id(item["artifact_id"]),
                item.get("type", ""),
                item.get("size", ""),
                item.get("created_at", ""),
            )
            for item in artifact_service.list()
        ]
        self._replace_rows(self.artifact_tree, rows, selected)

    def _replace_rows(self, tree: ttk.Treeview, rows: list[tuple[Any, ...]], selected: str | None) -> None:
        yview = tree.yview()
        current = list(tree.get_children())
        wanted = [str(row[0]) for row in rows]
        if current == wanted:
            for row in rows:
                tree.item(str(row[0]), values=row[1:])
        else:
            tree.delete(*current)
            for row in rows:
                iid = str(row[0])
                tree.insert("", "end", iid=iid, values=row[1:])
        if selected and tree.exists(selected) and tree.selection() != (selected,):
            tree.selection_set(selected)
        if yview:
            tree.yview_moveto(yview[0])

    def _on_task_select(self, _event=None) -> None:
        if self._refreshing:
            return
        selection = self.task_tree.selection()
        if not selection:
            return
        task_id = selection[0]
        obj = next((item for item in task_manager.list() if item.get("task_id") == task_id), None)
        label = f"선택 작업: {task_id}"
        preserve_view = self.file_path_var.get() == label
        self.file_path_var.set(label)
        self._set_text(
            self.file_detail,
            json.dumps(obj or {"task_id": task_id}, ensure_ascii=False, indent=2, default=str),
            preserve_view=preserve_view,
        )

    def _show_resolved_detail(self, tree: ttk.Treeview, detail: tk.Text, resolver) -> None:
        selection = tree.selection()
        if not selection:
            return
        obj = resolver(selection[0])
        self._set_text(detail, json.dumps(obj, ensure_ascii=False, indent=2, default=str))

    def _process_object(self, item_id: str) -> dict[str, Any]:
        return next((x for x in process_manager.list() if x.get("process_id") == item_id), {"id": item_id})

    def _browser_object(self, item_id: str) -> dict[str, Any]:
        value = browser_service.sessions.get(item_id)
        if not value:
            return {"id": item_id}
        result = {key: val for key, val in value.items() if key not in {"browser", "context", "page"}}
        page = value.get("page")
        result["url"] = getattr(page, "url", "")
        return result

    def _windows_object(self, item_id: str) -> dict[str, Any]:
        value = windows_ui_service.registry.windows.get(item_id)
        if not value:
            return {"id": item_id}
        result = {key: val for key, val in value.items() if key != "wrapper"}
        try:
            result["title"] = value["wrapper"].window_text()
        except Exception:
            result["title"] = ""
        return result

    def _artifact_object(self, item_id: str) -> dict[str, Any]:
        try:
            return artifact_service.info(item_id)
        except Exception as exc:
            return {"id": item_id, "error": str(exc)}

    def stop_process(self) -> None:
        selection = self.process_tree.selection()
        if not selection:
            return
        try:
            process_manager.stop(selection[0])
            self.refresh()
        except Exception as exc:
            messagebox.showerror("종료 실패", str(exc))

    def delete_selected_process_record(self) -> None:
        selection = self.process_tree.selection()
        if not selection:
            return
        record = self._process_object(selection[0])
        if record.get("status") not in {"EXITED", "FAILED", "STOPPED", "LOST"}:
            messagebox.showinfo("삭제 불가", "실행 중인 프로세스 이력은 삭제할 수 없습니다.")
            return
        if not messagebox.askyesno("확인", "선택한 종료 프로세스 이력을 삭제하시겠습니까?"):
            return
        process_manager.delete_finished_records([selection[0]])
        self._set_text(self.process_detail, "")
        self.refresh()

    def delete_finished_process_records(self) -> None:
        if not messagebox.askyesno("확인", "종료·실패·중지·유실 프로세스 이력을 모두 삭제하시겠습니까?"):
            return
        count = process_manager.delete_finished_records()
        self._set_text(self.process_detail, "")
        self.refresh()
        messagebox.showinfo("완료", f"프로세스 이력 {count}개를 삭제했습니다.")

    def open_artifact(self) -> None:
        selection = self.artifact_tree.selection()
        if not selection:
            return
        try:
            path, _ = artifact_service.file(selection[0])
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("열기 실패", str(exc))

    def _clear_completed_notice(self) -> None:
        self._clear_task_records({"COMPLETED"}, "완료")

    def _clear_failed_notice(self) -> None:
        self._clear_task_records({"FAILED"}, "실패")

    def _clear_task_records(self, statuses: set[str], label: str) -> None:
        if not messagebox.askyesno("확인", f"{label} 작업 기록을 삭제하시겠습니까?"):
            return
        count = task_manager.delete_by_status(statuses)
        if self.file_path_var.get().startswith("선택 작업:"):
            self.file_path_var.set("선택 항목 없음")
            self._set_text(self.file_detail, "")
        self.refresh()
        messagebox.showinfo("완료", f"{label} 작업 기록 {count}개를 삭제했습니다.")

    @staticmethod
    def _set_text(widget: tk.Text, value: str, *, preserve_view: bool = False) -> None:
        yview = widget.yview()
        xview = widget.xview()
        current = widget.get("1.0", "end-1c")
        if current == value:
            return
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        if preserve_view:
            if yview:
                widget.yview_moveto(yview[0])
            if xview:
                widget.xview_moveto(xview[0])

    @staticmethod
    def _selected_iid(tree: ttk.Treeview) -> str | None:
        selection = tree.selection()
        return selection[0] if selection else None

    @staticmethod
    def _short_id(value: Any, length: int = 12) -> str:
        text = str(value)
        return text if len(text) <= length else f"{text[:length]}…"

    def _on_task_records_changed(self) -> None:
        try:
            self.root.after(0, self._queue_task_refresh)
        except tk.TclError:
            pass

    def _queue_task_refresh(self) -> None:
        if self._task_refresh_pending:
            return
        self._task_refresh_pending = True
        self.root.after_idle(self._refresh_tasks_from_event)

    def _refresh_tasks_from_event(self) -> None:
        self._task_refresh_pending = False
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._refresh_tasks()
        finally:
            self._refreshing = False

    def _on_destroy(self, event) -> None:
        if event.widget is self.root:
            task_manager.unsubscribe(self._on_task_records_changed)
