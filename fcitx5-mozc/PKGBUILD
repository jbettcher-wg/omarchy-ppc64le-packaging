# Maintainer: Jiachen Yang <farseerfc@archlinux.org>
# Contributor: Felix Yan <felixonmars@archlinux.org>
# Contributor: ponsfoot <cabezon dot hashimoto at gmail dot com>
# Contributor: UTUMI Hirosi <utuhiro78 at yahoo dot co dot jp>
# Contributor: Weng Xuetian <wengxt@gmail.com>
# Contributor: Masato TOYOSHIMA <phoepsilonix at phoepsilonix dot love>

## Mozc compile option
_mozc_commit=a74b67127d710da4dc6fdbbd17320d04741174de

_bcr_commit=b0cb0e8ec70689252e3b35f109ffa4a32329b900
# Following are subject to change if bcr, bazel, and mozc commit changes.
# The build process does not necessary use all of them, but it is required to allow a no download build process.
# https://github.com/fcitx/flatpak-fcitx5/blob/master/mozc-deps.yaml has a constantly maintain list of these files
#
# Also jigyosyo.zip and ken_all.zip may be updated without notice.
_bazel_deps=(
    https://github.com/abseil/abseil-cpp/releases/download/20260107.1/abseil-cpp-20260107.1.tar.gz
    abseil-py-2.1.0.tar.gz::https://github.com/abseil/abseil-py/archive/refs/tags/v2.1.0.tar.gz
    https://github.com/astral-sh/python-build-standalone/releases/download/20251031/cpython-3.11.14+20251031-aarch64-unknown-linux-gnu-install_only.tar.gz
    https://github.com/astral-sh/python-build-standalone/releases/download/20251031/cpython-3.11.14+20251031-x86_64-unknown-linux-gnu-install_only.tar.gz
    bats-core-1.10.0.tar.gz::https://github.com/bats-core/bats-core/archive/v1.10.0.tar.gz
    https://github.com/bazel-contrib/bazel-lib/releases/download/v2.22.5/bazel-lib-v2.22.5.tar.gz
    https://github.com/bazel-contrib/bazel-lib/releases/download/v3.0.0/bazel-lib-v3.0.0.tar.gz
    https://github.com/bazel-contrib/bazel_features/releases/download/v1.42.1/bazel_features-v1.42.1.tar.gz
    https://github.com/bazel-contrib/rules_go/releases/download/v0.60.0/rules_go-v0.60.0.zip
    https://github.com/bazel-contrib/rules_python/releases/download/1.9.0/rules_python-1.9.0.tar.gz
    https://github.com/bazel-contrib/tar.bzl/releases/download/v0.5.1/tar.bzl-v0.5.1.tar.gz
    https://github.com/bazelbuild/apple_support/releases/download/2.4.0/apple_support.2.4.0.tar.gz
    https://github.com/bazelbuild/bazel-skylib/releases/download/1.9.0/bazel-skylib-1.9.0.tar.gz
    https://github.com/bazelbuild/platforms/releases/download/1.0.0/platforms-1.0.0.tar.gz
    https://github.com/bazelbuild/rules_android/releases/download/v0.7.1/rules_android-v0.7.1.tar.gz
    https://github.com/bazelbuild/rules_android_ndk/releases/download/v0.1.5/rules_android_ndk-v0.1.5.tar.gz
    https://github.com/bazelbuild/rules_apple/releases/download/4.5.2/rules_apple.4.5.2.tar.gz
    https://github.com/bazelbuild/rules_cc/releases/download/0.2.17/rules_cc-0.2.17.tar.gz
    https://github.com/bazelbuild/rules_java/releases/download/9.3.0/rules_java-9.3.0.tar.gz
    https://github.com/bazelbuild/rules_kotlin/releases/download/v2.2.2/rules_kotlin-v2.2.2.tar.gz
    https://github.com/bazelbuild/rules_license/releases/download/1.0.0/rules_license-1.0.0.tar.gz
    https://github.com/bazelbuild/rules_pkg/releases/download/1.2.0/rules_pkg-1.2.0.tar.gz
    https://github.com/bazelbuild/rules_shell/releases/download/v0.6.1/rules_shell-v0.6.1.tar.gz
    https://github.com/bazelbuild/rules_swift/releases/download/3.5.0/rules_swift.3.5.0.tar.gz
    https://github.com/hiroyuki-komatsu/japanese-usage-dictionary/archive/refs/tags/2025-01-25.zip
    https://github.com/hiroyuki-komatsu/japanpost_zipcode/raw/621d059fbcbfae17bfca15b439692bae934268c3/jigyosyo.zip
    https://github.com/hiroyuki-komatsu/japanpost_zipcode/raw/621d059fbcbfae17bfca15b439692bae934268c3/ken_all.zip
    https://github.com/madler/zlib/releases/download/v1.3.1/zlib-1.3.1.tar.gz
    https://github.com/protocolbuffers/protobuf/releases/download/v34.1/protobuf-34.1.bazel.tar.gz
    https://github.com/protocolbuffers/protobuf/releases/download/v34.1/protoc-34.1-linux-aarch_64.zip
    https://github.com/protocolbuffers/protobuf/releases/download/v34.1/protoc-34.1-linux-x86_64.zip
)

_pkgbase=mozc
pkgname=fcitx5-mozc
pkgdesc="Fcitx5 Module of A Japanese Input Method for Chromium OS, Windows, Mac and Linux (the Open Source Edition of Google Japanese Input)"
pkgver=3.35.6354.2
pkgrel=1
arch=('x86_64')
url="https://github.com/google/mozc"
license=('BSD-3-Clause' 'Apache-2.0' 'LGPL-2.0-or-later' 'LicenseRef-Unicode-DFS-2015' 'LicenseRef-NAIST-2003')
depends=(
  'qt6-base'
  'fcitx5'
  'hicolor-icon-theme'
  'libgcc'
  'libstdc++'
  'glibc'
)
makedepends=('git' 'bazelisk' 'python')
replaces=('mozc-fcitx')
conflicts=('mozc' 'mozc-server' 'mozc-utils-gui' 'mozc-fcitx' 'fcitx-mozc')
source=(git+https://github.com/fcitx/mozc.git#commit=${_mozc_commit}
        git+https://github.com/bazelbuild/bazel-central-registry#commit=${_bcr_commit}
)

for _bazel_dep in "${_bazel_deps[@]}"; do
  if [[ ! " ${source[*]} " =~ [[:space:]]${_bazel_dep}[[:space:]] ]]; then
    source+=("$_bazel_dep")
  fi
  _bazel_dep=${_bazel_dep%%::*}
  if [[ ! " ${noextract[*]} " =~ [[:space:]]${_bazel_dep##*/}[[:space:]] ]]; then
    noextract+=("${_bazel_dep##*/}")
  fi
done

sha512sums=('8a301ed40ad041a37cfbf916c659aa1d3a62faa167a6dc0aaff5a12c64ab8802c2a4842c6595bba3dc1b9c6fdc8e1a6197ae6c2831f8a4881261fc52b33ad093'
            'ed7cd6082f6ca62e4d6564881d383009a8f6f3dd2cf7c0b6bb4733d4b18325d995187fa1539e3dc75a6605577e2a8258a31574d54ac950e4a7a3b5127b188366'
            'f5012885d6b6844a9cf5ed92ad5468b8757db33dfe1364bfb232fff928e06c550c7eb4557f45186a8ac4d18b178df9be267681abab4a6de40823b574afbe9960'
            '298a876ed850085836cb1ff6fddf98aca6a3283780bece8c0a7d118fd4e16cc258e51f721e4a5fcbe62b23d2da05638475d426bb650b0694ff7c1d0119e3be97'
            '171ecb5ca4c30adc9297245209b2bf4a2d8baa25d3c28e5ef3e415f9cb08367f18cf4a2e39469d1c1eb4e674339f66576c36842d18e5e56c570bbd1e49851983'
            'b484436e5cf51d382264f74435769bdee8910d505ec8995ea18a6e1976de3b1d94bc8b1f03190e02b2c39808d5dfafb298bd1731838eb1e3fba5b2d7525a71d4'
            '31d98e26ff79354e8afd8eba2b19b1ca15ea4f1fbd16ad3936572688f49b33d68d38b6410c794f672572ee72cb535b11901759db67d4fa5656be2d0f6e050a99'
            '454f3dea077f9469b516b2173acf43c6645cc242f538bba34415adfc1b51aadaa3b33306b6155f6dac9409e168f8b453979fe0d810390cac9104e4d59e94cca7'
            '2001433611f10a9fa4866034a521f12fc0befe8fe8af8ea2dab8d4e486afd48f966dc1da66012bbc41d3c02106c892cab45a1ce236ffa55b9a46eaf9f9682074'
            'c5c032bcb8abf0c37b6490a57c6b8f263ee68f125876eff050eeb731213026a4ec391164b6b018f7f3c3eb742e666fadc1c03c1512051e59dae4a7f90fc8cd54'
            'f82d206ba8d59066bdcec87d4ac0bdcffa220a9fa5b9bc2082893e2efa9f3f175b33203c81b06fdf0502efe55b63546f1df4ab8c3b90deb8e38fe97fa9f76cf5'
            'b878eaf84ccff7a2b46a70f39ce5043f5e30e7baa0612b5770baed1be31dd603a8087d0fa3177014086fdd30fc799db84999883042097eaa8c207fcb26046ebd'
            '9b37b54051dff7dc947fb7b6e76f9f1276e1be5b451e6267910abf510a57abce07ef1286bbc9d936fd94c600e27375c81d81845b5a94b6634a3065dcdf7d73bb'
            '18a9ba69e55de792ad615fc6fc241182012bba69ab2bb05ad998b4fd78aad1f67dde477ecf62db186a85a5bd1249227ac0d983fae56755ad28d54f7a6cb54cef'
            'ec641d526b71ea2cc5ff9e642fb4f0db67a65e6c840ff4c96dcf80da5e2e0cb6a2016322c8f55aaa1761e34bd38301baf432a9dce3af6f8efd5f02970ee92c83'
            'cb05b7157e4e3b8ec05f1e4ac3e5eecc73d9a3ed5729455058a1290a5f04fb4e58be30368fc2ce6a90d6938ada331ea2abaeaaeaede16d1ae2ee091fa0c1faef'
            'f82193ab1c097ad26121980b4ea1fb584612b5db8593e810925540d06e96ccdba4be21bea4779ed981d7baff0fb59bc6835f03396adec0f5f7276b5bcd870ad4'
            '8feb8571d3952329be68408241b421797bcdeabf38c6d04be7a6de48b3052a1e39e17acf12ceff4e2d9d701a62f1f92ab8fb4eb974b9946c8e22aca5472b06fc'
            '89e5d98bc172a72a8c6ec741a028c521e24f07e76aad230330814d05d6227a7c529d19a3b98732f19ba9fdf8d3b4712cb5622945c597a0fa817b2c5bf7640859'
            'f2fd4acb20ec352e1a0b1ff562e1ca9bb3d9cc2b81d7f89ec371252d1b46d77eab73f4f2f576cd724e9a4eddbc89ca5f6e5223c35283fbe5bbae657f0c43ab1e'
            '5b94adf337c1baead4bee2716f3fc3489d2da9eb252f6f76a9fbf23e6a1bc87e3ebd93a88ba98d1ed770777cfc5e5f3c9330cf2c0205c8b8913b2c6f7ce1252a'
            '0e71df542b663af217a756b1a5d3106002b2bfd6d87f2a807dced6ec594f03ba95de548cc6d6aa5f27d4a8f8e5845120be996d0882f7850d84bc31689bfc225c'
            '17801f13c8a019de7e85a81ccfe6147ee9b996bbb72bbf4753aadb62e13c7c05040012182f3e557395a36453d8c7e9ca504b624bd2e490447656d0196c0fc6bb'
            '1d0de3048d3bb7f60162922891e27bea649537e8674be68e080883c7705cb2aa7af05fe64a174640b9f044fa18853b2d1df5b0e878fb9e71520fe2638fca6d09'
            '5f7e37729a06a2d6999c610dec1bd31255170b888af77e6a730b46991942f9e076fc541c022126fe6c079a7b92ade9f5feab4b69a30b997bb6a249ff9240fce5'
            '043ea6f1d7751e27f7dbc8d9ce4f0bff8cfa447e4a7d6a07c3bd3e0f994fadbd9c6525c16c3f00bcb719a1a9886fedd439d1e776ecc541d2c434ee973a6b1e84'
            'e2d71432836855192bee9ccf45781aef797d0112a0444684c782a5310cec35ff96793c2d4aba80ad2e71b789839f4fa1c70eb175be09a1c92e747639b0f6ab3e'
            'b99066b666e77babb34d09622261ce2df9ac92d030302487c9873babaf7d25d5519639484a619b87fef1db299ff3f288c63ad04e2b8ae34a81a30d68311c1da4'
            'd893c137569f008202ec7f7d1871c35641b9c5d502cf35c588ea0a95950af9e2dff891181d5c76ed905201016da6aa855d74c99267d739bd4a966ccda10d6b53'
            '580677aad97093829090d4b605ac81c50327e74a6c2de0b85dd2e8525553f3ddde17556ea46f8f007f89e435493c9a20bc997d1ef1c1c2c23274528e3c46b94f'
            '42d290c8ce0c093266e9f302115ff416702d32e1149af857e7e1aadfcc9b5097883b4e80d78697517236d83aa4d6742b810cc91836f10f897adbfc15160f0626'
            'b85337903ee031ae5ea2c9b1ac51d45bd9a9d7dde6572c2e7a1c41f5554206fad06e7e43f6e1b861d8f97405670ca32f954a42f4245f5ba1c4ec7ff5af4a9945'
            'cd3ab7d29756750de7599c89787ad8bf3d51d6a2112f9608186c6e0c40e9a14148c88cde80e676c9e972695c02b5482111ab6f7ea034cfdd2625d7576e9a8802')
validpgpkeys=('2CC8A0609AD2A479C65B6D5C8E8B898CBF2412F9')  # Weng Xuetian

pkgver(){
  cd mozc/src
  # https://github.com/google/mozc/discussions/1429
  # REVISION in mozc_version_template.bzl is no longer used by Bazel builds.
  # REVISION will be probably removed once GYP builds are completely removed.
  bazel build --config oss_linux --config stable_channel --config release_build --config no_sframe base:mozc_version_txt >/dev/null 2>&1
  source <(grep -E '^(MAJOR|MINOR|BUILD_OSS|REVISION)\s*=' bazel-bin/base/mozc_version.txt)
   _bzr_ver="$MAJOR.$MINOR.$BUILD_OSS.$REVISION"
  printf "%s" "${_bzr_ver}"
}

prepare() {
  # Bazel's distdir lookup uses the original URL basenames.
  ln -sf abseil-py-2.1.0.tar.gz "$srcdir/v2.1.0.tar.gz"
  ln -sf bats-core-1.10.0.tar.gz "$srcdir/v1.10.0.tar.gz"
}

build() {
  cd mozc/src

  # Use srcdir for pre-download files and override registry with local mirror.
  # bazel only respects CC from environment, not CXXFLAGS and LDFLAGS.
  # Pass them with --cxxopt, and --linkopt.
  bazel build \
      --config oss_linux \
      --config stable_channel \
      --config release_build \
      --config no_sframe \
      --distdir="${srcdir}" \
      --registry="file://${srcdir}/bazel-central-registry" \
      --copt=-DNDEBUG \
      $(echo "${CFLAGS}"|xargs -n1 echo "--conlyopt") \
      $(echo "${CXXFLAGS}"|xargs -n1 echo "--cxxopt") \
      --nostart_end_lib \
      --linkopt=-fuse-ld=bfd \
      $(echo "${LDFLAGS}"|xargs -n1 echo "--linkopt") \
      --copt="-Wno-uninitialized" \
      --host_copt="-Wno-uninitialized" --verbose_failures \
      unix/fcitx5:fcitx5-mozc.so \
      server:mozc_server \
      gui/tool:mozc_tool
}

package() {
  cd mozc/src
  export PREFIX="${pkgdir}/usr"
  ../scripts/install_server_bazel
  ../scripts/install_fcitx5_bazel

  install -d "${pkgdir}/usr/share/licenses/$pkgname/"
  install -m 644 ../LICENSE data/installer/*.html "${pkgdir}/usr/share/licenses/${pkgname}/"
}
