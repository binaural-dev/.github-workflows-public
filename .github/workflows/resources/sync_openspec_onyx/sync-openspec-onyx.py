#!/usr/bin/env python3
"""
Sincroniza las specs OpenSpec de un repo de addons hacia el índice de Onyx.

Existe porque el connector de GitHub de Onyx indexa **Pull Requests e Issues, no
archivos del repositorio** — así que `openspec/specs/` no llega a Onyx por esa vía.
Sin esto, las specs solo las leen los roles técnicos del repo clonado.

Usa la API de ingestión de Onyx (POST /onyx-api/ingestion), que hace upsert por
`document.id`: correrlo dos veces actualiza, no duplica.

Es un archivo suelto y sin dependencias a propósito: está pensado para vendorearse
o descargarse dentro del CI de cada repo de addons.

Configuración:

    export ONYX_API_KEY=...      # Onyx > Admin > Service Accounts

Uso, parado en el repo de addons (o apuntándole con --repo-dir):

    python3 sync-openspec-onyx.py --dry-run
    python3 sync-openspec-onyx.py
    python3 sync-openspec-onyx.py --repo-dir ~/integra-addons --vertical nomina

En CI, después de un merge que toque openspec/specs/.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ONYX_BASE = os.environ.get("ONYX_BASE_URL", "https://cloud.onyx.app/api")
INGESTION_URL = f"{ONYX_BASE}/onyx-api/ingestion"


def git(repo_dir, *args):
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_dir), *args],
            capture_output=True, text=True, timeout=15, check=False,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def datos_repo(repo_dir):
    """Nombre del repo y URL base para enlazar, derivados del remote."""
    remote = git(repo_dir, "config", "--get", "remote.origin.url")
    nombre = Path(repo_dir).resolve().name
    base = None
    m = re.search(r"[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?$", remote or "")
    if m:
        owner, repo = m.group(1), m.group(2)
        nombre = repo
        rama = git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD"
        base = f"https://github.com/{owner}/{repo}/blob/{rama}"
    return nombre, base


def fecha_git(repo_dir, ruta):
    """Última modificación del archivo según git; si no hay git, el mtime."""
    iso = git(repo_dir, "log", "-1", "--format=%cI", "--", str(ruta))
    if iso:
        return iso
    try:
        ts = Path(ruta).stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except OSError:
        return None


def titulo_de(texto, respaldo):
    """Primer encabezado markdown del archivo, o el nombre de la capability."""
    m = re.search(r"^#\s+(.+)$", texto, re.M)
    return m.group(1).strip() if m else respaldo


def capabilities(repo_dir):
    """Cada carpeta bajo openspec/specs/ es una capability.

    Se toma todo el markdown de la carpeta, no solo spec.md: algunas capabilities
    parten el contenido en varios archivos y perderlos deja la spec a medias.
    """
    raiz = Path(repo_dir) / "openspec" / "specs"
    if not raiz.is_dir():
        return None
    salida = []
    for carpeta in sorted(p for p in raiz.iterdir() if p.is_dir()):
        # spec.md primero: es el archivo principal, del que sale el título y el
        # enlace. Sin esto, un anexo.md alfabéticamente anterior se lleva ambos.
        archivos = sorted(carpeta.rglob("*.md"),
                          key=lambda f: (f.name != "spec.md", str(f)))
        if not archivos:
            continue
        partes, rutas = [], []
        for f in archivos:
            try:
                t = f.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeDecodeError) as e:
                print(f"  ⚠️  no se pudo leer {f}: {e}")
                continue
            if not t:
                continue
            rel = f.relative_to(repo_dir)
            partes.append(t if len(archivos) == 1 else f"<!-- {rel} -->\n{t}")
            rutas.append(rel)
        if partes:
            salida.append((carpeta.name, "\n\n---\n\n".join(partes), rutas))
    return salida


def a_documento(nombre_repo, base_url, capability, texto, rutas, vertical, fecha):
    principal = rutas[0]
    doc = {
        "id": f"openspec-{nombre_repo}-{capability}",
        "semantic_identifier": f"{nombre_repo} · {titulo_de(texto, capability)}",
        "title": titulo_de(texto, capability),
        "sections": [{
            "text": texto,
            "link": f"{base_url}/{principal}" if base_url else str(principal),
        }],
        "source": "ingestion_api",
        "metadata": {
            "fuente": "openspec",
            "repo": nombre_repo,
            "capability": capability,
            "archivos": [str(r) for r in rutas],
        },
        "from_ingestion_api": True,
    }
    if vertical:
        doc["metadata"]["vertical"] = vertical
    if fecha:
        doc["doc_updated_at"] = fecha
    return doc


def upsert(doc, onyx_key, cc_pair_id=None):
    payload = {"document": doc}
    if cc_pair_id is not None:
        payload["cc_pair_id"] = cc_pair_id
    req = urllib.request.Request(
        INGESTION_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {onyx_key}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def main():
    ap = argparse.ArgumentParser(
        description="Sincroniza openspec/specs/ de un repo de addons hacia Onyx."
    )
    ap.add_argument("--repo-dir", default=".", help="Repo de addons (default: cwd).")
    ap.add_argument("--vertical", help="Vertical al que pertenece, para filtrar en Onyx.")
    ap.add_argument("--dry-run", action="store_true", help="No escribe en Onyx.")
    ap.add_argument("--cc-pair-id", type=int, help="cc_pair de Onyx, si ya creaste uno.")
    args = ap.parse_args()

    repo_dir = Path(args.repo_dir).resolve()
    if not repo_dir.is_dir():
        sys.exit(f"ERROR: no existe el directorio {repo_dir}")

    caps = capabilities(repo_dir)
    if caps is None:
        sys.exit(
            f"ERROR: no encontré {repo_dir}/openspec/specs/\n"
            "¿Estás parado en un repo de addons con OpenSpec inicializado?\n"
            "Ver docs-as-code/README.md del stack."
        )
    if not caps:
        print(f"No hay capabilities con contenido en {repo_dir}/openspec/specs/ — nada que hacer.")
        return

    onyx_key = None if args.dry_run else os.environ.get("ONYX_API_KEY")
    if not args.dry_run and not onyx_key:
        sys.exit("ERROR: falta ONYX_API_KEY (Onyx > Admin > Service Accounts).")

    nombre_repo, base_url = datos_repo(repo_dir)
    print(f"Repo: {nombre_repo}  ({repo_dir})")
    print(f"Enlaces: {base_url or '(sin remote git — se usan rutas relativas)'}")
    print(f"Onyx: {INGESTION_URL}{'  (DRY RUN — no escribe)' if args.dry_run else ''}")
    print(f"\n{len(caps)} capabilities\n")

    ok = nuevos = errores = 0
    for capability, texto, rutas in caps:
        fecha = fecha_git(repo_dir, rutas[0])
        doc = a_documento(nombre_repo, base_url, capability, texto, rutas,
                          args.vertical, fecha)
        detalle = f"{len(texto)} chars, {len(rutas)} archivo(s)"
        if args.dry_run:
            ok += 1
            print(f"  →  {capability}  ({detalle})")
            continue
        res, err = upsert(doc, onyx_key, args.cc_pair_id)
        if err:
            errores += 1
            print(f"  ✘  {capability} — {err}")
        else:
            ok += 1
            if not res.get("already_existed"):
                nuevos += 1
            print(f"  ✔  {capability} — "
                  f"{'actualizado' if res.get('already_existed') else 'NUEVO'}")

    print(f"\nResumen: {ok} enviadas ({nuevos} nuevas) · {errores} errores")
    if errores:
        sys.exit(1)


# ---------------------------------------------------------------------------
# NOTA SOBRE PERMISOS
#
# Los documentos que entran por la API de ingestión NO heredan permisos: quedan
# visibles para quien pueda buscar en el índice de Onyx.
#
# Las specs describen desarrollos de clientes concretos. Antes de sincronizar
# repos con specs sensibles, definí si eso es aceptable, si se filtra por
# vertical, o si van a un Document Set restringido en Onyx.
#
# El metadato `vertical` que agrega --vertical existe justamente para poder
# filtrar después sin volver a indexar.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
