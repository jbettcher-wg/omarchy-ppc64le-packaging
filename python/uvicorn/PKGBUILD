# Maintainer: Filipe Laíns (FFY00) <lains@archlinux.org>
# Maintainer: Maxime Gauduin <alucryd@archlinux.org>

pkgname=uvicorn
pkgver=0.54.0
pkgrel=1
pkgdesc='The lightning-fast ASGI server'
arch=(any)
url=https://github.com/encode/uvicorn
license=(BSD-3-Clause)
depends=(
  python
  python-click
  python-h11
  python-typing_extensions
)

optdepends=(
  'python-a2wsgi: for WSGI support'
  'python-dotenv: for --env-file support'
  'python-gunicorn: for Gunicorn workers'
  'python-httptools: for faster HTTP protocol handling'
  'python-pyyaml: for --log-config with YAML'
  'python-uvloop: for faster event loop'
  'python-watchfiles: for --reload support'
  'python-websockets: for WebSocket support'
  'python-wsproto: for WebSocket support'
)

makedepends=(
  git
  python-build
  python-hatchling
  python-installer
)
source=(git+https://github.com/encode/uvicorn#tag=${pkgver})
b2sums=('3900a6c69f618f30b412a1b202f363ccd5d3be9f913c81528826d983910be8a276964df83d72741f80f8d575c06a0e367fe669a8b416120041e4d373b7b16fec')



build() {
  cd uvicorn
  python -m build --wheel --no-isolation
}

package() {
  python -m installer --destdir="${pkgdir}" uvicorn/dist/*.whl
  install -Dm 644 uvicorn/LICENSE.md -t "${pkgdir}"/usr/share/licenses/uvicorn/
}
