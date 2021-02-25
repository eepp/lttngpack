# Copyright (c) 2021 Philippe Proulx <eeppeliteloop@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import re
import bs4
import requests
import collections
import packaging.version


class _Distro:
    def __init__(self, name, versions):
        self._name = name
        self._versions = versions

    @property
    def name(self):
        return self._name

    @property
    def versions(self):
        return self._versions


class _DistroVersion:
    def __init__(self, version):
        self._version = version
        self._pkgs = []

    @property
    def version(self):
        return self._version

    @property
    def pkgs(self):
        return self._pkgs

    def pkg(self, name):
        for pkg in self._pkgs:
            if pkg.name == name:
                return pkg


class _Pkg:
    def __init__(self, name, version):
        self._name = name
        self._version = version

    @property
    def name(self):
        return self._name

    @property
    def version(self):
        return self._version


_RepologyProjects = collections.namedtuple('_RepologyProjects',
                                           ['tools', 'ust', 'modules'])


def _distro_versions_from_repology_repos(repology_repos, repo_version_func):
    distro_versions = []

    for repo in repology_repos:
        repo_version = repo_version_func(repo)

        if repo_version is None:
            continue

        distro_version = None

        for dv in distro_versions:
            if dv.version == repo_version:
                distro_version = dv

        if distro_version is None:
            distro_version = _DistroVersion(repo_version)
            distro_versions.append(distro_version)

        distro_version.pkgs.append(_Pkg(repo['visiblename'],
                                        packaging.version.parse(repo['version'])))

    return distro_versions


def _alpine_distro(repology_repos):
    def repo_version(repo):
        m = re.match(r'alpine_(\d+)_(\d+)', repo['repo'])

        if m:
            return f'{m.group(1)}.{m.group(2)}'

    return _Distro('Alpine Linux',
                   _distro_versions_from_repology_repos(repology_repos, repo_version))


def _arch_distro(repology_repos):
    def repo_version(repo):
        if repo['repo'] == 'arch':
            return '(rolling)'

    return _Distro('Arch Linux',
                   _distro_versions_from_repology_repos(repology_repos, repo_version))


def _debian_distro(repology_repos):
    def repo_version(repo):
        m = re.match(r'debian_(.+)', repo['repo'])

        if m and m.group(1) != 'sid':
            return m.group(1)

    return _Distro('Debian', _distro_versions_from_repology_repos(repology_repos, repo_version))


def _fedora_distro(repology_repos):
    def repo_version(repo):
        m = re.match(r'fedora_(\d+)', repo['repo'])

        if m:
            return m.group(1)

    return _Distro('Fedora', _distro_versions_from_repology_repos(repology_repos, repo_version))


def _opensuse_distro(repology_repos):
    def repo_version(repo):
        m = re.match(r'opensuse_leap_(\d+)_(\d+)', repo['repo'])

        if m:
            return f'{m.group(1)}.{m.group(2)}'

    return _Distro('openSUSE Leap',
                   _distro_versions_from_repology_repos(repology_repos, repo_version))


def _ubuntu_distro(repology_repos):
    def repo_version(repo):
        m = re.match(r'ubuntu_(\d+)_(\d+)', repo['repo'])

        if m:
            return f'{m.group(1)}.{m.group(2)}'

    return _Distro('Ubuntu', _distro_versions_from_repology_repos(repology_repos, repo_version))


def _buildroot_distro():
    def distro_version(br_version):
        def pkg(name):
            mk = requests.get(f'https://git.buildroot.net/buildroot/plain/package/{name}/{name}.mk?h={br_version}.x')

            if 'Invalid branch' in mk.text:
                return

            m = re.search(r'^LTTNG_.+_VERSION\s+=\s+([^\s]+)', mk.text, re.M)
            return _Pkg(name, packaging.version.parse(m.group(1)))

        lttng_tools_pkg = pkg('lttng-tools')

        if lttng_tools_pkg is None:
            return

        lttng_ust_pkg = pkg('lttng-libust')
        lttng_modules_pkg = pkg('lttng-modules')
        dist_version = _DistroVersion(br_version)
        dist_version.pkgs.append(lttng_tools_pkg)
        dist_version.pkgs.append(lttng_ust_pkg)
        dist_version.pkgs.append(lttng_modules_pkg)
        return dist_version

    yr = 2019
    month = 2
    distro_versions = []

    while True:
        dist_version = distro_version(f'{yr}.{month:02}')

        if dist_version is None:
            break

        distro_versions.append(dist_version)
        month += 3

        if month > 11:
            yr += 1
            month = 2

    return _Distro('Buildroot', distro_versions)


def _yocto_distro():
    def distro_version(yocto_version):
        pkgs = []
        page = requests.get(f'https://git.openembedded.org/openembedded-core/tree/meta/recipes-kernel/lttng?h={yocto_version}')
        m = re.search(r'lttng-tools_([\d.]+)\.bb', page.text)
        lttng_tools_pkg = _Pkg('lttng-tools', packaging.version.parse(m.group(1)))
        m = re.search(r'lttng-ust_([\d.]+)\.bb', page.text)
        lttng_ust_pkg = _Pkg('lttng-ust', packaging.version.parse(m.group(1)))
        m = re.search(r'lttng-modules_([\d.]+)\.bb', page.text)
        lttng_modules_pkg = _Pkg('lttng-modules', packaging.version.parse(m.group(1)))
        dist_version = _DistroVersion(yocto_version)
        dist_version.pkgs.append(lttng_tools_pkg)
        dist_version.pkgs.append(lttng_ust_pkg)
        dist_version.pkgs.append(lttng_modules_pkg)
        return dist_version

    gw = requests.get('https://git.openembedded.org/openembedded-core/')
    soup = bs4.BeautifulSoup(gw.text, 'html.parser')
    yocto_version_blacklist = set([
        r'.*-next.*',
        r'\d.*',
        r'daisy',
        r'danny',
        r'denzil',
        r'dizzy',
        r'dora',
        r'dylan',
        r'fido',
        r'jethro',
        r'krogoth',
        r'master',
        r'morty',
        r'pyro',
        r'rocko',
        r'sumo',
    ])

    valid_versions = []

    for opt in soup.find(id='cgit').find('select', attrs={'name': 'h'}).find_all('option'):
        is_valid = True

        for blacklist_re in yocto_version_blacklist:
            if re.match(blacklist_re, opt['value']):
                is_valid = False
                break

        if is_valid:
            valid_versions.append(opt['value'])

    distro_versions = []

    for version in valid_versions:
        distro_versions.append(distro_version(version))

    return _Distro('Yocto', distro_versions)


def _repology_project(project_name):
    return requests.get(f'https://repology.org/api/v1/project/{project_name}').json()


def _repology_repos():
    return (_repology_project('lttng-tools') + _repology_project('lttng-ust') +
            _repology_project('lttng-modules'))


def distros():
    repology_repos = _repology_repos()
    distros = []
    distros.append(_alpine_distro(repology_repos))
    distros.append(_arch_distro(repology_repos))
    distros.append(_buildroot_distro())
    distros.append(_debian_distro(repology_repos))
    distros.append(_fedora_distro(repology_repos))
    distros.append(_opensuse_distro(repology_repos))
    distros.append(_ubuntu_distro(repology_repos))
    distros.append(_yocto_distro())
    distros.sort(key=lambda distro: distro.name)
    return distros


if __name__ == '__main__':
    def distro_version_pkg_version(distro_version, pkg_names):
        pkg = None

        for pkg_name in pkg_names:
            pkg = distro_version.pkg(pkg_name)

            if pkg is not None:
                break

        if pkg is not None:
            return str(pkg.version)

        return ''

    import prettytable

    distros = distros()
    table = prettytable.PrettyTable()
    table.field_names = ['Distro / Project', 'LTTng-tools', 'LTTng-UST', 'LTTng-modules']
    table.align = 'r'

    for distro in sorted(distros, key=lambda d: d.name.lower()):
        for distro_version in sorted(distro.versions, key=lambda v: packaging.version.parse(v.version)):
            table.add_row([f'{distro.name} {distro_version.version}',
                           distro_version_pkg_version(distro_version, ['lttng-tools', 'ltt-control']),
                           distro_version_pkg_version(distro_version, ['lttng-ust', 'ust', 'lttng-libust']),
                           distro_version_pkg_version(distro_version, ['lttng-modules'])])

    print(table)
