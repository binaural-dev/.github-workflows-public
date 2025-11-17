#!/bin/bash

set -e  # Salir si ocurre cualquier error

HOST_REPO_DIR="$(pwd)"

REPO_URL="git@github.com:binaural-dev/.github-workflows-public-old.git"
TARGET_DIR=".github"
HASH_FILE="$HOST_REPO_DIR/gw_hash.txt"
BRANCH="rls_feat-ta_56178_check_test_from_pull_requests"

# Mostrar configuración actual
echo "📦 Configuración:"
echo ""
echo "HOST_REPO_DIR: $HOST_REPO_DIR"
echo "REPO_URL:      $REPO_URL"
echo "TARGET_DIR:    $TARGET_DIR"
echo "BRANCH:        $BRANCH"
echo "HASH_FILE:     $HASH_FILE"
echo ""
echo ""

# Crear el directorio .github si no existe
echo ""
echo ""
echo "🔧 Asegurando que el directorio .github exista..."
mkdir -p .github

echo ""
echo ""
echo "🔄 Sincronizando $TARGET_DIR desde $REPO_URL en la rama $BRANCH..."


if [ -d "$TARGET_DIR" ] && [ ! -d "$TARGET_DIR/.git" ]; then
  echo "$TARGET_DIR existe pero no es un repositorio git. Se debe eliminar para obtenerlo como un repositorio y lograr la actualizacion. Eliminando..."
  rm -rf "$TARGET_DIR"
fi

if [ ! -d "$TARGET_DIR/.git" ]; then
  echo ""
  echo ""
  echo "📥 Clonando repositorio limpio..."
  git clone --branch "$BRANCH" "$REPO_URL" "$TARGET_DIR"
else

  echo ""
  echo ""
  echo "🧹 Limpiando y forzando sincronización..."
  cd "$TARGET_DIR"

  # Asegura que no haya cambios locales
  git fetch origin
  git checkout "$BRANCH"
  git reset --hard origin/"$BRANCH"
  git clean -fdx  # Elimina archivos no rastreados y carpetas

  cd - > /dev/null
fi

echo ""
echo ""
echo "📄 Actualizando archivo de hash con la ultima referencia (hash)..."

# Crear el archivo si no existe
if [ ! -f "$HASH_FILE" ]; then
  echo ""
  echo ""
  echo "📄 El archivo $HASH_FILE no existe. Creándolo..."

  touch "$HASH_FILE"
fi

# Obtener el hash actual
CURRENT_HASH=$(git -C "$TARGET_DIR" rev-parse HEAD)

# Guardar el hash en el archivo
echo "$CURRENT_HASH" > "$HASH_FILE"

echo ""
echo ""
echo "✅ Hash actual guardado en $HASH_FILE: $CURRENT_HASH"

echo ""
echo ""
echo "📤 Comiteando y pusheando cambios al repositorio host..."
echo ""

git -C "$HOST_REPO_DIR" add "$HASH_FILE" # Agregar el archivo de hash
git -C "$HOST_REPO_DIR" add "$TARGET_DIR" # Agregar los cambios en el submódulo
git -C "$HOST_REPO_DIR" commit -m "chore: Actualizar $TARGET_DIR a la última versión de $BRANCH; ($CURRENT_HASH)" || echo "No hay cambios para commitear en $TARGET_DIR" # Comitear solo si hay cambios
git -C "$HOST_REPO_DIR" push origin HEAD || echo "No hay cambios para pushear en $TARGET_DIR" # Pushear solo si hay cambios

echo ""
echo "✅ Sincronización completada."
echo ""
