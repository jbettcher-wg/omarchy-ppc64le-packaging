# Maintainer: Lukas Fleischer <lfleischer@archlinux.org>
# Contributor: Allan McRae <allan@archlinux.org>
# Contributor: judd <jvinet@zeroflux.org>

pkgname=automake
pkgver=1.20
pkgrel=1
pkgdesc="A GNU tool for automatically creating Makefiles"
arch=('any')
license=('GPL')
url="https://www.gnu.org/software/automake"
depends=('perl' 'bash')
makedepends=('autoconf' 'git')
checkdepends=('dejagnu' 'gcc-fortran' 'java-environment' 'vala' 'emacs' 'cscope'
              'expect' 'ncompress' 'gettext' 'lzip' 'zip' 'sharutils' 'help2man'
              # disable TeX tests for now, lots of them fail and need upstream
              # fixes for current texlive release
              #'texlive-bin' 'texinfo'
              'python' 'python-virtualenv')
source=("git+https://git.savannah.gnu.org/git/automake.git#tag=v${pkgver}?signed"
        "enable-reproducible-builds.patch")
sha512sums=('9720dd855e7c7e810b4cb11453ed160af60b2c3147cf23885f1f076719d54861a5ef54c3357990932a5408d8c29053aacd7799c9f0f3b65e70eb5afbc9466338'
            'a53b050ad4811eed1ab077c31afefb66d1222e7ed57db59d31409d48a0bc9bf3b13ba50934162c9e0854d616aed6355c391f1c3f8720ea900d538d9dbe4203b6')
validpgpkeys=('E1622F96D2BB4E58018EEF9860F906016E407573'   # Stefano Lattarini
              'F2A38D7EEB2B66405761070D0ADEE10094604D37'   # Mathieu Lirzin
              '155D3FC500C834486D1EEA677FD9FCCB000BEEEE'   # Jim Meyering
              '17D3311B14BC0F248267BF020716748A30D155AD'   # Karl Berry
              '6C222EA6B2BD216AA406516AC868F0B6DE38409D')  # Kamila Szewczyk

prepare() {
	cd "${pkgname}"

	# Make amhello-1.0.tar.gz reproducible (when combined with $GZIP_ENV below).
	patch -Np1 -i ../enable-reproducible-builds.patch

	./bootstrap
}

build() {
	cd "${pkgname}"
	./configure --build=$CHOST --prefix=/usr
	make GZIP_ENV='-9 -n'
}

check() {
	cd "${pkgname}"
	make check
}

package() {
	cd "${pkgname}"
	make DESTDIR="${pkgdir}" install
}
