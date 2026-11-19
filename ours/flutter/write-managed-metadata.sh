#!/bin/bash
# Writes the files that make a Flutter tree a *managed* SDK (flutter-port
# patch "Add a managed, read-only SDK mode"): the bin/cache/managed-by marker,
# every artifact stamp, the version files and engine_stamp.json, and the
# bin/cache/dart-sdk link. PKGBUILD.draft runs `version` on the build tree in
# build(), and `all` on the install tree in package(), once the material fonts
# and the Gradle wrapper are in place. It only writes files and runs nothing
# emulated, so it is safe under fakeroot.
#
# usage: write-managed-metadata.sh <version|all> <flutter-root> <key>=<value>...
#   version  only the marker, the version files and the engine stamp: enough
#            for the tool to run (build() needs it for the app-jit training
#            run of flutter_tools.snapshot, which must not download anything)
#   all      also checks that every artifact is in place and writes its stamp
#   owner=            first line of bin/cache/managed-by, e.g. "pacman (flutter 3.41.9-1)"
#   arch=             host arch as the tool names it: ppc64
#   dart_sdk=         target of bin/cache/dart-sdk, e.g. /usr/lib/dart
#   framework_version= e.g. 3.41.9            channel= stable
#   framework_revision= full sha of the tag    framework_date= "YYYY-MM-DD HH:MM:SS +0000"
#   engine_revision=  the content-aware engine hash (bin/internal/engine.version)
#   engine_date=      as framework_date        engine_build_ms= build time, ms since epoch
#   dart_version=     e.g. 3.11.5             devtools_version= e.g. 2.54.2
#   check_root=       optional: where the engine artifacts are checked for, when
#                     another package installs them (flutter-engine puts them in
#                     /usr/lib/flutter/bin/cache, not in this package's $pkgdir)
#   check_dart=       optional: where the Dart SDK named by dart_sdk= is checked
#                     for (default: dart_sdk itself)
set -euo pipefail
phase=$1; root=$2; shift 2
[[ $phase == version || $phase == all ]] || { echo "phase must be version or all" >&2; exit 2; }
declare -A v
for kv in "$@"; do v[${kv%%=*}]=${kv#*=}; done
for k in owner arch dart_sdk framework_version channel framework_revision framework_date \
         engine_revision engine_date engine_build_ms dart_version devtools_version; do
  [[ -n "${v[$k]:-}" ]] || { echo "missing $k=" >&2; exit 2; }
done
cache=$root/bin/cache
mkdir -p "$cache"

need() { [[ -e "$1" ]] || { echo "missing: $1" >&2; missing=1; }; }
missing=0
a=${v[arch]}
ec=${v[check_root]:-$root}/bin/cache
need "${v[check_dart]:-${v[dart_sdk]}}/version"
if [[ $phase == all ]]; then
# What the tool's up-to-date checks look at.
need "$root/bin/internal/material_fonts.version"
need "$root/bin/internal/gradle_wrapper.version"
need "$root/packages/flutter_tools/.dart_tool/package_config.json"
need "$cache/flutter_tools.snapshot"
need "$ec/pkg/sky_engine/pubspec.yaml"
need "$ec/pkg/flutter_gpu"
need "$ec/artifacts/engine/common/flutter_patched_sdk"
need "$ec/artifacts/engine/common/flutter_patched_sdk_product"
for d in linux-$a linux-$a-profile linux-$a-release; do need "$ec/artifacts/engine/$d"; done
need "$cache/artifacts/material_fonts"
for f in gradlew gradlew.bat gradle/wrapper/gradle-wrapper.jar; do
  need "$cache/artifacts/gradle_wrapper/$f"
done
fi
(( missing == 0 )) || exit 1

printf '%s\n' "${v[owner]}" > "$cache/managed-by"
: > "$cache/.dartignore"   # as bin/internal/shared.sh would create it
ln -sfn "${v[dart_sdk]}" "$cache/dart-sdk"

e=${v[engine_revision]}
printf '%s\n' "$e" > "$cache/engine.stamp"
printf '\n' > "$cache/engine.realm"
printf '%s' "$e" > "$cache/engine_stamp.stamp"
if [[ $phase == all ]]; then
  # EngineCachedArtifact stamps hold the engine revision.
  for s in flutter_sdk linux-sdk font-subset; do
    printf '%s' "$e" > "$cache/$s.stamp"
  done
  # CachedArtifacts with their own version file hold that file's content.
  for s in material_fonts gradle_wrapper; do
    tr -d '\n' < "$root/bin/internal/$s.version" > "$cache/$s.stamp"
  done
fi

iso_date() { date -u -d "$1" '+%Y-%m-%d %H:%M:%S.000Z'; }
cat > "$cache/engine_stamp.json" <<JSON
{
  "build_time_ms": ${v[engine_build_ms]},
  "git_revision": "$e",
  "git_revision_date": "$(iso_date "${v[engine_date]}")",
  "content_hash": "$e"
}
JSON
cat > "$cache/flutter.version.json" <<JSON
{
  "frameworkVersion": "${v[framework_version]}",
  "channel": "${v[channel]}",
  "repositoryUrl": "https://github.com/flutter/flutter.git",
  "frameworkRevision": "${v[framework_revision]}",
  "frameworkCommitDate": "${v[framework_date]}",
  "engineRevision": "$e",
  "engineCommitDate": "${v[engine_date]}",
  "engineContentHash": "$e",
  "engineBuildDate": "$(date -u -d "@$(( ${v[engine_build_ms]} / 1000 ))" '+%Y-%m-%d %H:%M:%S.000Z')",
  "dartSdkVersion": "${v[dart_version]}",
  "devToolsVersion": "${v[devtools_version]}",
  "flutterVersion": "${v[framework_version]}"
}
JSON
printf '%s' "${v[framework_version]}" > "$root/version"
# The compile key bin/internal/shared.sh would write; read by
# Cache.isOlderThanToolsStamp.
printf '%s:\n' "${v[framework_revision]}" > "$cache/flutter_tools.stamp"
echo "managed metadata ($phase) written to $root (owner: ${v[owner]})"
