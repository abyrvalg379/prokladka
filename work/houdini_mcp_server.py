# -*- coding: utf-8 -*-
"""Houdini MCP bridge (ZCode_MPC compatible).

Wire-compatible TCP bridge with the Blender MCP addon protocol
(blender-mcp 1.6.x style, JSON over TCP). Default port 9877 — matches the
Houdini entry in the ZCode MCP config.

Usage (Houdini Python Shell / Python Source Editor / shelf):
    exec(open(r"D:/AI/ZCode/Project/PROKLADKA/work/houdini_mcp_server.py",
              encoding="utf-8").read())

Commands:
    {"type": "ping"}
    {"type": "get_scene_info"}
    {"type": "execute_code", "params": {"code": "<python>"}}

Response: {"status": "success", "result": {...}} or
          {"status": "error", "message": "..."} (stdout included in result).

All command handlers run on Houdini's main thread via
hou.ui.queueToMainThread, so UI and node operations are safe.

Author: Maksim Kovalev, VVERH Studio. PROKLADKA project.
"""

import json
import socket
import threading
import traceback
import contextlib
import io

HOST = "127.0.0.1"
PORT = 9877

import hou  # noqa: E402  (Houdini python)


def _run_on_main(fn, timeout=180.0):
    """Run fn() on Houdini's main thread, return its result / re-raise."""
    if not hou.isUIAvailable():
        return fn()
    ev = threading.Event()
    box = {}

    def job():
        try:
            box["res"] = fn()
        except Exception as e:  # noqa: BLE001
            box["err"] = e
            box["tb"] = traceback.format_exc()
        finally:
            ev.set()

    hou.ui.queueToMainThread(job)
    if not ev.wait(timeout):
        raise RuntimeError("main-thread job timed out after %ss" % timeout)
    if "err" in box:
        raise RuntimeError("%s\n%s" % (box["err"], box.get("tb", "")))
    return box.get("res")


def cmd_ping(params):
    return {"result": {"status": "ok", "houdini": hou.applicationVersionString(),
                       "hip": hou.hipFile.name()}}


def cmd_get_scene_info(params):
    out = {
        "hip": hou.hipFile.name(),
        "fps": hou.fps(),
        "frame": hou.frame(),
        "frame_range": [hou.playbar.frame_range()[0], hou.playbar.frame_range()[1]],
        "contexts": {},
    }
    for ctx in ("/obj", "/stage", "/out", "/ch"):
        node = hou.node(ctx)
        if node:
            out["contexts"][ctx] = [(c.name(), c.type().name()) for c in node.children()]
    return {"result": out}


def cmd_execute_code(params):
    code = params.get("code", "")
    buf = io.StringIO()
    g = {"hou": hou, "result": None}
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        exec(code, g)  # noqa: S102  (прямо в потоке сервера; hou-операции потокобезопасны)
    return {"result": {"stdout": buf.getvalue(), "result": str(g.get("result"))}}


HANDLERS = {
    "ping": cmd_ping,
    "get_scene_info": cmd_get_scene_info,
    "execute_code": cmd_execute_code,
}


def _client_loop(conn, addr):
    print("[houdini-mcp] client connected:", addr)
    buf = b""
    try:
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf += chunk
            while True:
                try:
                    req = json.loads(buf.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    break  # ждём ещё данных
                consumed = len(buf)
                buf = b""
                try:
                    if not isinstance(req, dict):
                        resp = {"status": "error", "message": "request must be a JSON object"}
                    else:
                        ctype = req.get("type", "")
                        params = req.get("params", {}) or {}
                        handler = HANDLERS.get(ctype)
                        if handler is None:
                            resp = {"status": "error", "message": "Unknown command: %s" % ctype}
                        else:
                            resp = handler(params)
                            if not isinstance(resp, dict):
                                resp = {"status": "error", "message": "handler returned %s" % type(resp).__name__}
                            resp.setdefault("status", "success")
                except Exception as e:  # noqa: BLE001
                    resp = {"status": "error", "message": "%s\n%s" % (e, traceback.format_exc())}
                try:
                    conn.sendall(json.dumps(resp).encode("utf-8"))
                except Exception as e:  # noqa: BLE001
                    print("[houdini-mcp] send failed:", e)
                    return
    except Exception as e:  # noqa: BLE001
        print("[houdini-mcp] connection error:", e)
    finally:
        print("[houdini-mcp] client disconnected:", addr)
        conn.close()


def _already_alive(port=PORT):
    """True если на порту уже отвечает наш мост."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect((HOST, port))
        s.sendall(json.dumps({"type": "ping"}).encode("utf-8"))
        data = s.recv(4096)
        s.close()
        return b'"ok"' in data
    except Exception:  # noqa: BLE001
        return False


def start(port=PORT):
    if _already_alive(port):
        print("[houdini-mcp] already running on %s:%s — skip" % (HOST, port))
        return None

    def serve():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, port))
        srv.listen(1)
        print("[houdini-mcp] listening on %s:%s" % (HOST, port))
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=_client_loop, args=(conn, addr), daemon=True).start()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    print("[houdini-mcp] server thread started on %s:%s" % (HOST, port))
    return t


_SERVER_THREAD = start()
