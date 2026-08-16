# Resolve DATA_DIR the same way for every entry point:
#   an existing DATA_DIR environment variable > a DATA_DIR line in .env >
#   the portable default ./.data
# Source this from each script; never re-implement the precedence.
resolve_data_dir() {
  local root="$1"
  if [[ -z "${DATA_DIR:-}" && -f "$root/.env" ]]; then
    DATA_DIR="$(grep -E '^[[:space:]]*DATA_DIR[[:space:]]*=' "$root/.env" | tail -1 \
      | sed -E 's/^[[:space:]]*DATA_DIR[[:space:]]*=[[:space:]]*//; s/^["'\'']//; s/["'\'']$//')"
  fi
  export DATA_DIR="${DATA_DIR:-$root/.data}"
}
