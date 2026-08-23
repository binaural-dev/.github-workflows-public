# Checks de CI para repos de clientes (Implementación)

Tres checks pensados para repos de personalización de clientes (módulos Odoo
en la raíz del repo, ej. `cdd-las-mercedes`, `giralda`, `maxcam-core`,
`maxcam-ext`, `alreyven`), que corren en cada PR contra `staging`/`release`:

- **`check-pr-tests`** — corre las pruebas unitarias/integración de los
  módulos tocados y publica la cobertura.
- **`check-openspec`** — valida que el PR tenga respaldo en OpenSpec.
- **`check-manifest-version`** — valida que la versión del `__manifest__.py`
  suba respecto a la rama base.

## Cómo se entregan (rulesets, no copias por repo)

Los tres workflows (`check-pr-tests.yml`, `check-openspec.yml`,
`check-manifest-version.yml`) viven **solo** en este repo
(`.github-workflows-public`) y se inyectan en los repos de clientes vía
**GitHub Rulesets** (required workflows) a nivel de organización — no se
copian archivos `.github/workflows/` a cada repo cliente. Esto es la misma
convención que ya usan `integra-addons`/`odoo-venezuela`.

Cada ruleset apunta a una rama fija (`release` de este repo) y a la lista
explícita de repos cliente — nunca "todos los repos", para no tener blast
radius desconocido.

## Activación: dos capas de variables (org + repo)

Cada check se activa con **dos** variables booleanas (`"1"`/vacío), y las
**dos** tienen que estar en `1` o el check sale en verde sin validar nada
(skip silencioso, no falla — hay que abrir el log para diferenciar un PASS
real de un skip):

| Check | Variable de organización | Variable de repo |
|---|---|---|
| check-pr-tests | `ENABLE_ORG_CICD_CHECK_PR_TESTS` | `ENABLE_REPO_CICD_CHECK_PR_TESTS` |
| check-openspec | `ENABLE_ORG_CICD_CHECK_OPENSPEC` | `ENABLE_REPO_CICD_CHECK_OPENSPEC` |
| check-manifest-version | `ENABLE_ORG_CICD_CHECK_MANIFEST_VERSION` | `ENABLE_REPO_CICD_CHECK_MANIFEST_VERSION` |

Las variables de **organización** requieren `admin:org` para crearse
(`gh api orgs/binaural-dev/actions/variables`). Si no se tiene ese permiso
pero se quiere activar el check en un solo repo sin esperar a un admin de
org: GitHub Actions resuelve una variable de **repo** con el mismo nombre
por encima de la de organización, así que crear
`ENABLE_ORG_CICD_CHECK_OPENSPEC=1` como variable de **repo** (no de org)
activa el check únicamente en ese repo, sin tocar nada a nivel org ni
afectar a los demás.

Variables de repo adicionales requeridas:
- `REPO_CICD_CHECK_PR_TARGET_BRANCHES` / `REPO_CICD_CHECK_OPENSPEC_TARGET_BRANCHES` / `REPO_CICD_CHECK_MANIFEST_VERSION_TARGET_BRANCHES` — ramas destino permitidas (ej. `staging,release`).
- `REPO_CICD_CHECK_OPENSPEC_MODULES_GLOB` / `REPO_CICD_CHECK_MANIFEST_VERSION_MODULES_GLOB` — glob de carpetas raíz de módulo (ej. `*/`).
- `REPO_CICD_CHECK_PR_TESTS_BRANCHES_JSON_SETTINGS` — settings de test por rama (odoo_version, mode, add_repositories, etc.).

## check-manifest-version: qué exige y qué exime

- Exige que la versión de `__manifest__.py` suba (comparación numérica por
  segmento `[Odoo].[A].[B].[C]`, no lexicográfica) para todo módulo tocado
  por el PR.
- **Exento**: módulos nuevos (no existían en la rama base) — se toma la
  versión declarada tal cual, sin exigir que "suba" contra nada.

## check-openspec: qué exige y qué exime

Exige, para cada módulo tocado por el PR que tenga carpeta `openspec/`, que
el PR incluya **al menos una** de estas señales (evaluadas contra el diff
`base_sha..head_sha`, no contra lo que ya hubiera en el disco):

- Un change nuevo o modificado en `<módulo>/openspec/changes/` (carpeta por
  change con `proposal.md`/`tasks.md`, o un `.md` suelto — conviven ambas
  convenciones).
- Un archivo tocado dentro de `<módulo>/openspec/specs/` (edición directa de
  spec ya aceptada, sin pasar por un change nuevo).

**Exenciones** (no piden spec):

- Módulo sin carpeta `openspec/` todavía — convención opt-in, se omite.
- **Bump puro de manifest**: si el único archivo tocado del módulo es
  `__manifest__.py` (subir versión sin cambio de código), no se exige spec.
- **README de módulo**: si los únicos archivos tocados del módulo son
  `__manifest__.py` y/o `README.md`/`README.rst`, no se exige spec.
- **README de la raíz del repo** (ej. el truco de tocar `/README.md` para
  forzar un rebuild en Odoo.sh): ni siquiera cuenta como "módulo tocado",
  porque el archivo no cae dentro de ninguna carpeta de módulo — no hace
  falta ninguna exención explícita para este caso.

## Gotcha importante: PASS visual ≠ validación real

Un check en verde en la lista de checks del PR **no** garantiza que corrió
la lógica — si falta cualquiera de las dos variables de activación
(org o repo), el workflow sale con `exit 0` imprimiendo
`"⚠️ Las configuraciones de activación no están habilitadas"` y nunca llega
a evaluar nada. Para confirmar que un check realmente validó, hay que abrir
el log del job y buscar la línea `✅ Todas las variables están presentes.`
antes de la validación en sí.
