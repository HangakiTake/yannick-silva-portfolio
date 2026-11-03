"""Recalculate an xlsx with LibreOffice and read values back.

The workbook on disk is not overwritten. Callers read calculated values from
the open document, so Excel-style formulas stay as openpyxl wrote them.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import uno
from com.sun.star.beans import PropertyValue


class LibreOfficeSession:
    def __init__(self, port: int = 2002) -> None:
        self.port = port
        self.profile = Path(f"/tmp/lo-rubs-profile-{port}")
        self.proc: subprocess.Popen[bytes] | None = None
        self.desktop = None

    def start(self) -> None:
        subprocess.run(["pkill", "-f", "soffice"], check=False)
        time.sleep(0.4)
        env = os.environ.copy()
        env["SAL_USE_VCLPLUGIN"] = "svp"
        self.proc = subprocess.Popen(
            [
                "soffice",
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--norestore",
                "--nolockcheck",
                f"-env:UserInstallation=file://{self.profile}",
                f"--accept=socket,host=127.0.0.1,port={self.port};urp;StarOffice.ComponentContext",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), 0.2):
                    break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("LibreOffice did not open a listener")
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local
        )
        context = resolver.resolve(
            f"uno:socket,host=127.0.0.1,port={self.port};urp;StarOffice.ComponentContext"
        )
        self.desktop = context.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", context
        )

    def open(self, path: Path):
        if self.desktop is None:
            self.start()
        url = uno.systemPathToFileUrl(str(Path(path).resolve()))
        hidden = PropertyValue()
        hidden.Name = "Hidden"
        hidden.Value = True
        document = self.desktop.loadComponentFromURL(url, "_blank", 0, (hidden,))
        document.calculateAll()
        return document

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self.desktop = None
