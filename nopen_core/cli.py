"""Turkish command-line interface for Nopen Studio Core W001."""

import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import re
import signal
import sqlite3
import sys
import time

from . import core
from .store import CoreError, STATES, connect

WARNING = """========================================================================
NOPEN STUDIO CORE | İLK KURULUM VE İZİN BİLDİRİMİ

Bu sürüm görev hafızasını bu bilgisayarda saklar ve ağ bağlantısı kurmaz.
Ekran izleme ve ekran kontrolü KAPALI — NOT IMPLEMENTED.
Onayınız yalnız bu bildirimi okuduğunuzu kaydeder. İşletim sistemi
izni vermez. Reddetseniz de konsol ve görev hafızası çalışır.

Parola, token veya hassas kişisel verileri görev alanlarına girmeyin.
Kaynağı resmî Nopen Studio bağlantısından doğrulayın.
https://github.com/nopen-admin/NopenStudioCore
========================================================================"""


def identifier(value):
    if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", value) is None:
        raise argparse.ArgumentTypeError("Kimlik 1–64 ASCII harf, rakam veya ._- içermelidir.")
    return value


def note(value):
    if len(value) > 4000 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise argparse.ArgumentTypeError("Metin en fazla 4000 karakter olmalı ve kontrol karakteri içermemeli.")
    return value


def required_note(value):
    if not note(value).strip():
        raise argparse.ArgumentTypeError("Metin boş olamaz.")
    return value


def deadline(value):
    try:
        return datetime.date.fromisoformat(value).isoformat() if value else ""
    except ValueError:
        raise argparse.ArgumentTypeError("Tarih YYYY-MM-DD biçiminde olmalı.") from None


def parser():
    root = argparse.ArgumentParser(prog="nopen", description="Nopen Studio Core yerel görev hafızası.")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="İlk kurulum bildirimini ve izin durumunu göster.")
    decision = init.add_mutually_exclusive_group()
    decision.add_argument("--accept", action="store_true", help="Bildirimi okuduğunuzu açıkça kaydet.")
    decision.add_argument("--decline", action="store_true", help="Bildirimi reddet ve konsol modunu kullan.")

    commands.add_parser("status", help="Hafıza, kuyruk ve izin durumunu göster.")
    run = commands.add_parser("run", help="Yerel işlem kuyruğunu terminalde çalıştır.")
    run.add_argument("--once", action="store_true", help="En fazla bir kontrol noktası işle ve çık.")
    commands.add_parser("pause", help="Yeni işlem başlamasını duraklat.")
    commands.add_parser("resume", help="Duraklatılan kuyruğu yeniden etkinleştir.")
    commands.add_parser("stop", help="Kuyruğu kapat ve açık çalıştırıcıdan çık.")
    commands.add_parser("simulate-intervention", help="Test amacıyla insan müdahalesi olayını kaydet ve duraklat.")
    handoff = commands.add_parser("handoff", help="Görev bağlamını ve son kontrol noktasını göster.")
    handoff.add_argument("id", type=identifier)
    commands.add_parser("export", help="Yerel hafızayı JSON olarak standart çıktıya yaz.")
    revoke = commands.add_parser("revoke", help="Kaydedilmiş ekran izni kararını iptal et.")
    revoke.add_argument("capability", choices=(*core.CAPABILITIES, "all"))
    commands.add_parser("doctor", help="Masaüstü desteğine ilişkin yerel göstergeleri salt okunur incele.")

    task = commands.add_parser("task", help="Görev ve kaynaklı bağlam kayıtlarını yönet.")
    tasks = task.add_subparsers(dest="task_command", required=True)
    add = tasks.add_parser("add", help="Yeni görev oluştur.")
    add.add_argument("id", type=identifier)
    add.add_argument("goal", type=required_note)
    add.add_argument("--priority", type=int, choices=range(1, 6), default=3)
    add.add_argument("--deadline", type=deadline, default="")

    context = tasks.add_parser("context", help="Sıkıştırılmış bağlam alanlarını güncelle.")
    context.add_argument("id", type=identifier)
    context.add_argument("--summary", type=note)
    context.add_argument("--unknowns", type=note)
    context.add_argument("--next-step", type=note)
    context.add_argument("--priority", type=int, choices=range(1, 6))
    context.add_argument("--deadline", type=deadline)

    evidence = tasks.add_parser("evidence", help="Kaynak referansı olan kanıt ekle.")
    evidence.add_argument("id", type=identifier)
    evidence.add_argument("reference", type=required_note)
    evidence.add_argument("text", type=required_note)
    human_decision = tasks.add_parser("decision", help="İnsan kararı ekle.")
    human_decision.add_argument("id", type=identifier)
    human_decision.add_argument("decision", choices=("approve", "deny", "note"))
    human_decision.add_argument("text", type=required_note)
    state = tasks.add_parser("state", help="Görev durumunu kaydet.")
    state.add_argument("id", type=identifier)
    state.add_argument("state", choices=STATES)
    checkpoint = tasks.add_parser("checkpoint", help="Tekrar gönderilebilir bir kontrol noktası isteği sırala.")
    checkpoint.add_argument("id", type=identifier)
    checkpoint.add_argument("action_id", type=identifier)
    checkpoint.add_argument("--note", type=note, default="")
    return root


def doctor():
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session not in {"wayland", "x11"}:
        session = "wayland" if os.environ.get("WAYLAND_DISPLAY") else "unknown"
        if session == "unknown" and os.environ.get("DISPLAY"):
            session = "x11"
    portal_directory = Path("/usr/share/xdg-desktop-portal/portals")
    interfaces = ("org.freedesktop.impl.portal.ScreenCast", "org.freedesktop.impl.portal.RemoteDesktop")
    available = dict.fromkeys(interfaces, False)
    for path in portal_directory.glob("*.portal"):
        try:
            manifest = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for interface in interfaces:
            available[interface] |= interface in manifest
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    libraries = (Path("/usr/lib64"), Path("/usr/lib"), Path("/usr/local/lib64"))
    try:
        distro = platform.freedesktop_os_release().get("ID", "unknown")
    except OSError:
        distro = "unknown"
    return {
        "platform": sys.platform,
        "distribution": distro,
        "session": session,
        "portal_manifest_interfaces": available,
        "pipewire_socket_present": bool(os.path.isabs(runtime) and (Path(runtime) / "pipewire-0").is_socket()),
        "libei_library_present": any(any(path.glob("libei.so*")) for path in libraries),
        "desktop_access": "NOT IMPLEMENTED",
        "probe": "Yerel ortam ve dosya göstergeleri. Portal oturumu açılmadı.",
    }


def print_json(value):
    print(json.dumps(value, ensure_ascii=True, indent=2), flush=True)


def run(db, once):
    terminating = False

    def request_stop(_signum, _frame):
        nonlocal terminating
        terminating = True

    with core.runner_lock():
        previous_handler = signal.signal(signal.SIGTERM, request_stop)
        try:
            core.change_mode(db, "run")
            while not terminating:
                mode, action = core.step(db)
                if once:
                    print_json({"mode": mode, "processed": action})
                    return
                if mode == "STOPPED":
                    return
                if action is not None:
                    print_json({"processed": action})
                else:
                    time.sleep(0.25)
        except KeyboardInterrupt:
            terminating = True
            raise
        finally:
            try:
                if terminating:
                    core.change_mode(db, "stop")
            finally:
                signal.signal(signal.SIGTERM, previous_handler)


def task_command(db, args):
    task_id = args.id
    if args.task_command == "add":
        return core.add_task(db, task_id, args.goal, args.priority, args.deadline)
    if args.task_command == "checkpoint":
        return core.queue_checkpoint(db, task_id, args.action_id, args.note)
    if args.task_command == "context":
        detail = {key: getattr(args, key) for key in core.CONTEXT_FIELDS if getattr(args, key) is not None}
        if not detail:
            raise CoreError("En az bir bağlam alanı belirtin.")
        kind = "context"
    elif args.task_command == "evidence":
        kind, detail = "evidence", {"reference": args.reference, "text": args.text}
    elif args.task_command == "decision":
        kind, detail = "human-decision", {"decision": args.decision, "text": args.text}
    else:
        kind, detail = "task-state", {"state": args.state}
    return {"event": core.update_task(db, task_id, kind, detail)}


def dispatch(db, args):
    command = args.command
    if command == "run":
        run(db, args.once)
        return
    if command == "task":
        result = task_command(db, args)
    elif command == "handoff":
        result = core.handoff(db, args.id)
    elif command == "status":
        result = core.status(db)
    elif command == "export":
        result = core.export_memory(db)
    elif command == "revoke":
        result = core.revoke(db, args.capability)
    else:
        operation = "human-intervention" if command == "simulate-intervention" else command
        result = {"mode": core.change_mode(db, operation)}
    print_json(result)


def main(argv=None):
    args = parser().parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == "doctor":
            print_json(doctor())
        elif args.command == "init":
            print(WARNING, file=sys.stderr, flush=True)
            accepted = args.accept
            if not args.accept and not args.decline and sys.stdin.isatty():
                print("Bildirimi okuduğunuzu kaydetmek için EVET yazın [varsayılan HAYIR].",
                      file=sys.stderr, flush=True)
                accepted = sys.stdin.readline().strip().casefold() == "evet"
            with connect(initialize=True) as db:
                print_json(core.initialize(db, accepted))
        else:
            with connect() as db:
                core.require_initialized(db)
                dispatch(db, args)
        return 0
    except KeyboardInterrupt:
        return 130
    except CoreError as exc:
        print(f"nopen — {exc}", file=sys.stderr)
    except (OSError, sqlite3.Error, json.JSONDecodeError):
        print("nopen — Yerel hafıza veya dosya işlemi başarısız. Durum yolunu ve veritabanını denetleyin.",
              file=sys.stderr)
    return 1
