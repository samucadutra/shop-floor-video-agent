#!/usr/bin/env bash
# Downloads the 4 demo clips (docs/prd.md Appendix A) into samples/ and checks their SHA-256.
# The clips are free under the Pexels License and are never committed.
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p samples

# id | direct 720p URL | sha256
SAMPLES=(
  "16106604|https://videos.pexels.com/video-files/16106604/16106604-hd_1280_720_30fps.mp4|e20b2a53363817e70a236b7139b48a6c85bd14ba822f8f741ab64500e2e55a75"
  "4294438|https://videos.pexels.com/video-files/4294438/4294438-hd_1280_720_50fps.mp4|85f85ea690f98a8d920f9180d2538867fd4f1fa682857a28e834aa94f8e0639b"
  "13422071|https://videos.pexels.com/video-files/13422071/13422071-hd_1280_720_30fps.mp4|aadaf12cddba076bf6a7acf31abea68f75b121f90a45cf7d9283fd1082819851"
  "31751344|https://videos.pexels.com/video-files/31751344/13528205_1280_720_25fps.mp4|2d4cc7eb91aa93361a0e1d756451452c073fcbd46a741e4e954aa4e1ddf5de18"
)

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

download() {
  curl -fsSL -A "Mozilla/5.0" --retry 2 -o "$2" "$1"
}

failed=0
for row in "${SAMPLES[@]}"; do
  IFS='|' read -r id url expected <<<"$row"
  target="samples/${id}.mp4"

  if [[ -f "$target" && "$(sha256_of "$target")" == "$expected" ]]; then
    echo "OK       $target (already downloaded)"
    continue
  fi

  if ! download "$url" "$target"; then
    echo "         direct link failed for $id, trying the Pexels download page" >&2
    download "https://www.pexels.com/download/video/${id}/?h=720&w=1280" "$target" || true
  fi

  if [[ -f "$target" && "$(sha256_of "$target")" == "$expected" ]]; then
    echo "OK       $target"
  else
    echo "MISMATCH $target (the mock provider will match it by file name instead)"
    failed=1
  fi
done

exit "$failed"
