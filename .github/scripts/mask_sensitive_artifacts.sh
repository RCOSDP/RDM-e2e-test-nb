#!/bin/bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <artifact-dir> [<artifact-dir> ...]" >&2
  exit 1
fi

base_dir=$(pwd)

mask_value() {
  local value="$1"
  local length=${#value}
  if (( length <= 8 )); then
    printf '****'
    return
  fi

  local prefix="${value:0:4}"
  local suffix="${value: -4}"
  local mask_length=$((length - 8))
  local stars
  stars=$(printf '%*s' "$mask_length" '' | tr ' ' '*')
  printf '%s%s%s' "$prefix" "$stars" "$suffix"
}

replace_in_file() {
  local file="$1"
  local value="$2"
  local masked="$3"

  VALUE="$value" MASKED="$masked" perl -0pi -e 's/\Q$ENV{VALUE}\E/$ENV{MASKED}/g' "$file"
}

replace_in_tree() {
  local target_dir="$1"
  local value="$2"
  local masked="$3"

  find "$target_dir" -type f \
    \( -name '*.ipynb' -o -name '*.log' -o -name '*.json' -o -name '*.har' -o -name '*.html' -o -name '*.js' -o -name '*.txt' -o -name '*.yaml' -o -name '*.yml' \) \
    -print0 |
    while IFS= read -r -d '' file; do
      replace_in_file "$file" "$value" "$masked"
    done

  find "$target_dir" -type f -name 'har.zip' -print0 |
    while IFS= read -r -d '' zip_file; do
      local tmp_dir
      local output_zip
      tmp_dir=$(mktemp -d)
      case "$zip_file" in
        /*)
          output_zip="$zip_file"
          ;;
        *)
          output_zip="$base_dir/$zip_file"
          ;;
      esac
      unzip -q "$zip_file" -d "$tmp_dir"
      find "$tmp_dir" -type f -print0 |
        while IFS= read -r -d '' file; do
          replace_in_file "$file" "$value" "$masked"
        done
      (cd "$tmp_dir" && zip -qr "$output_zip" .)
      rm -rf "$tmp_dir"
    done
}

while IFS='=' read -r name value; do
  case "$name" in
    *ACCESS_KEY*|*SECRET_KEY*|*PASSWORD*|*TOKEN*)
      ;;
    *)
      continue
      ;;
  esac

  if [[ -z "$value" || ${#value} -lt 8 ]]; then
    continue
  fi

  masked=$(mask_value "$value")
  echo "::add-mask::$value"

  for target_dir in "$@"; do
    if [[ -d "$target_dir" ]]; then
      replace_in_tree "$target_dir" "$value" "$masked"
    fi
  done
done < <(env)
