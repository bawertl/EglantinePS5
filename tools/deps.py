#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned build inputs of EglantinePS5 (tools/deps.json).

  tools/deps.py status          list every input, where it lives and whether it matches its pin
  tools/deps.py fetch [NAME...] fetch what is missing (all inputs, or the named ones)
  tools/deps.py path NAME       print where an input lives
  tools/deps.py clean           remove the fetched inputs inside .deps (sibling checkouts stay)

Nothing that already exists is modified: an existing checkout stays at whatever revision it
has (status reports it), an existing file or folder is not downloaded again. Downloads are
cached in $EGLANTINEPS5_DEPS_CACHE (default ~/.cache/eglantineps5-deps) and verified against
their pinned SHA-256/SHA-512 before use; git inputs are fetched at their pinned commit.
"""
import hashlib
import json
import os
import pathlib
import urllib.parse
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'tools/deps.json').read_text())
CACHE = pathlib.Path(os.environ.get('EGLANTINEPS5_DEPS_CACHE') or
                     pathlib.Path(os.environ.get('XDG_CACHE_HOME') or pathlib.Path.home() / '.cache')
                     / 'eglantineps5-deps')


def fail(message):
    print(f'deps: {message}', file=sys.stderr)
    sys.exit(1)


def items(names=()):
    known = {item['name']: item for item in MANIFEST['items']}
    unknown = [name for name in names if name not in known]
    if unknown:
        fail(f'unknown input(s): {", ".join(unknown)} (known: {", ".join(known)})')
    return [known[name] for name in names] if names else list(known.values())


def location(item):
    key = {'git': 'path', 'files': 'dest'}.get(item['kind'])
    return (ROOT / item[key]).resolve() if key else (ROOT / item['creates']).resolve()


def present(item):
    marker = item.get('creates')
    return (ROOT / marker).exists() if marker else location(item).exists()


def digest(path, algorithm):
    hasher = hashlib.new(algorithm)
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            hasher.update(block)
    return hasher.hexdigest()


def pinned_hash(entry):
    for algorithm in ('sha256', 'sha512'):
        if algorithm in entry:
            return algorithm, entry[algorithm]
    fail(f'no pinned hash for {entry.get("url")}')


def github_release_asset_api(url):
    """Return a fresh API asset endpoint for a GitHub release link, when available.

    GitHub's browser-download redirect can be cached with an expired signed URL.
    The release API gives us a second, independently resolved route to the SAME
    release asset; the pinned file digest remains mandatory on either route.
    """
    parsed = urllib.parse.urlsplit(url)
    parts = parsed.path.strip('/').split('/')
    if parsed.netloc != 'github.com' or len(parts) < 6 or parts[2:4] != ['releases', 'download']:
        return None
    owner, repo, tag, filename = parts[0], parts[1], parts[4], '/'.join(parts[5:])
    api = (f'https://api.github.com/repos/{owner}/{repo}/releases/tags/'
           f'{urllib.parse.quote(tag, safe="")}')
    headers = {'User-Agent': 'eglantineps5-deps', 'Accept': 'application/vnd.github+json'}
    # Do not print tokens or URLs containing secrets. The API works anonymously for public releases.
    request = urllib.request.Request(api, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    for asset in release.get('assets', []):
        if asset.get('name') == filename:
            return asset['url']
    return None


def download(url, algorithm, expected, name):
    """Download pinned bytes with retries, cached checksum and GitHub release API fallback."""
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / name
    if target.exists() and digest(target, algorithm) == expected:
        return target
    partial = target.with_name(target.name + f'.partial-{os.getpid()}')
    api_url = None
    last_error = None
    for attempt in range(1, 4):
        # Alternate the direct release URL with the GitHub API, which resolves a fresh
        # signed asset redirect. A cache-busting query handles stale CDN redirects.
        urls = [(url, {'User-Agent': 'eglantineps5-deps'})]
        if '/releases/download/' in url and url.startswith('https://github.com/'):
            try:
                if api_url is None:
                    api_url = github_release_asset_api(url)
                if api_url:
                    urls.append((api_url, {'User-Agent': 'eglantineps5-deps',
                                           'Accept': 'application/octet-stream'}))
            except (OSError, ValueError, KeyError) as error:
                last_error = error
            join = '&' if urllib.parse.urlsplit(url).query else '?'
            urls.append((f'{url}{join}attempt={attempt}-{os.getpid()}',
                         {'User-Agent': 'eglantineps5-deps'}))
        for source, headers in urls:
            try:
                print(f'deps: downloading {source}', flush=True)
                request = urllib.request.Request(source, headers=headers)
                with urllib.request.urlopen(request, timeout=120) as response, open(partial, 'wb') as out:
                    shutil.copyfileobj(response, out, 1 << 20)
                actual = digest(partial, algorithm)
                if actual == expected:
                    partial.replace(target)
                    return target
                last_error = f'{algorithm} mismatch: got {actual}, expected {expected}'
            except OSError as error:
                last_error = error
            finally:
                partial.unlink(missing_ok=True)
        if attempt != 3:
            time.sleep(5 * attempt)
    fail(f'cannot download or verify {url}: {last_error}')


def extract(archive, destination, strip, only=()):
    """Extracts into destination through a temporary folder beside it (no partial trees).
    `only` keeps the members whose path (after strip) is one of these files or lies in one of
    these folders."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = pathlib.Path(tempfile.mkdtemp(prefix='.deps-', dir=destination.parent))
    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zipped:
                for member in zipped.infolist():
                    parts = pathlib.PurePosixPath(member.filename).parts[strip:]
                    if not parts:
                        continue
                    relative = pathlib.PurePosixPath(*parts)
                    if only and not any(str(relative) == keep or
                                        str(relative).startswith(keep.rstrip('/') + '/')
                                        for keep in only):
                        continue
                    target = staging.joinpath(*relative.parts)
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zipped.open(member) as source, open(target, 'wb') as output:
                        shutil.copyfileobj(source, output)
                    mode = member.external_attr >> 16
                    if mode:
                        target.chmod(mode)
        else:
            with tarfile.open(archive) as tar:
                members = []
                for member in tar.getmembers():
                    parts = pathlib.PurePosixPath(member.name).parts[strip:]
                    if not parts:
                        continue
                    member.name = str(pathlib.PurePosixPath(*parts))
                    if only and not any(member.name == keep or
                                        member.name.startswith(keep.rstrip('/') + '/')
                                        for keep in only):
                        continue
                    members.append(member)
                # Python 3.11.0-3.11.3 has no extraction filters; the archive's hash was checked.
                safe = {'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}
                tar.extractall(staging, members=members, **safe)
        destination.mkdir(parents=True, exist_ok=True)
        for entry in staging.iterdir():
            target = destination / entry.name
            if target.exists():
                continue  # never replace what is already there
            entry.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def git(*args, cwd=None):
    subprocess.run(['git', *args], cwd=cwd, check=True)


def boilerplate_zlib_ready(path):
    """The SDK marker alone does not prove upstream's zlib setup finished."""
    root = path / '.deps/native/zlib/root'
    return (root / '.source-version').is_file() and \
           (root / '.source-version').read_text().strip() == '1.3.2' and \
           (root / 'usr/include/zlib.h').is_file() and \
           any(root.rglob('libz.a'))


def stage_boilerplate_zlib(path):
    """Seed upstream's zlib archive from the identical, SHA-verified official release.

    The legacy zlib.net/fossils URL can return an HTML/error body. Upstream's
    setup script then exits with a checksum mismatch. We NEVER relax its digest
    check: copy only bytes matching the publisher's pinned 1.3.2 SHA-256.
    """
    expected = 'bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16'
    archive = path / '.deps/native/zlib/zlib-1.3.2.tar.gz'
    if archive.is_file() and digest(archive, 'sha256') == expected:
        print('deps: verified cached boilerplate zlib 1.3.2', flush=True)
        return
    verified = download('https://github.com/madler/zlib/releases/download/v1.3.2/zlib-1.3.2.tar.gz',
                        'sha256', expected, 'boilerplate-zlib-1.3.2.tar.gz')
    archive.parent.mkdir(parents=True, exist_ok=True)
    temp = archive.with_name(archive.name + f'.partial-{os.getpid()}')
    try:
        shutil.copyfile(verified, temp)
        if digest(temp, 'sha256') != expected:
            fail('boilerplate zlib: verified staging copy does not match SHA-256')
        temp.replace(archive)
    finally:
        temp.unlink(missing_ok=True)
    print('deps: seeded official, SHA-256-verified boilerplate zlib 1.3.2', flush=True)


def fetch_git(item):
    path = location(item)
    if not path.exists():
        print(f'deps: fetching {item["url"]} at {item["commit"][:12]} into {path}', flush=True)
        staging = path.with_name(path.name + f'.partial-{os.getpid()}')
        shutil.rmtree(staging, ignore_errors=True)
        git('init', '-q', str(staging))
        git('remote', 'add', 'origin', item['url'], cwd=staging)
        git('fetch', '-q', '--depth', '1', 'origin', item['commit'], cwd=staging)
        git('-c', 'advice.detachedHead=false', 'checkout', '-q', '--detach', 'FETCH_HEAD', cwd=staging)
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=staging, text=True).strip()
        if head != item['commit']:
            fail(f'{item["name"]}: fetched {head}, pinned {item["commit"]}')
        staging.rename(path)
    needs_setup = ('setup' in item and
                   (not (path / item['setup_creates']).exists() or
                    (item['name'] == 'boilerplate' and not boilerplate_zlib_ready(path))))
    if needs_setup:
        command = item['setup']
        if item['name'] == 'boilerplate':
            # The boilerplate's setup-native-dependencies.sh uses one silent wget to
            # fetch the very same SDK that lapy-payload-sdk already pins by SHA-256.
            # Fetch it once via our verified, retrying cache and reuse its SDK tree;
            # still run upstream's setup for native zlib (with --skip-sdk).
            sdk_item = next(entry for entry in MANIFEST['items']
                            if entry['name'] == 'lapy-payload-sdk')
            fetch(sdk_item)
            sdk_source = ROOT / sdk_item['extract']
            if not ((sdk_source / 'bin/prospero-clang').is_file() and
                    (sdk_source / 'bin/prospero-lld').is_file() and
                    (sdk_source / 'target/include').is_dir()):
                fail('pinned payload SDK is incomplete; refusing boilerplate setup')
            sdk_link = path / '.deps/native/ps5-payload-sdk'
            sdk_link.parent.mkdir(parents=True, exist_ok=True)
            if not sdk_link.exists() and not sdk_link.is_symlink():
                sdk_link.symlink_to(sdk_source.resolve(), target_is_directory=True)
            elif not sdk_link.resolve().samefile(sdk_source.resolve()):
                fail(f'{sdk_link} is not the pinned SDK; not replacing existing data')
            # Validate and place the upstream-pinned archive before its zlib build.
            # Its own sha256sum check and native compile still run unchanged.
            if not boilerplate_zlib_ready(path):
                stage_boilerplate_zlib(path)
            command = [*command, '--skip-sdk']
        print(f'deps: setting up {item["name"]}: {" ".join(command)}', flush=True)
        subprocess.run(command, cwd=path, check=True)


def fetch(item):
    kind = item['kind']
    if kind == 'git':
        fetch_git(item)
        return
    if present(item):
        return
    if kind == 'archive':
        algorithm, expected = pinned_hash(item)
        name = pathlib.PurePosixPath(item.get('save') or f'{item["name"]}-{expected[:12]}.tar.gz').name
        archive = download(item['url'], algorithm, expected, name)
        if 'save' in item:
            saved = ROOT / item['save']
            if not saved.exists():
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(archive, saved)
        extract(archive, ROOT / item['extract'], item.get('strip', 0), item.get('only', ()))
    elif kind == 'files':
        destination = ROOT / item['dest']
        destination.mkdir(parents=True, exist_ok=True)
        for entry in item['files']:
            target = destination / entry['name']
            if target.exists():
                continue
            algorithm, expected = pinned_hash(entry)
            shutil.copyfile(download(entry['url'], algorithm, expected, f'{item["name"]}-{entry["name"]}'), target)
    else:
        fail(f'{item["name"]}: unknown kind {kind}')
    if not present(item):
        fail(f'{item["name"]}: fetched, but {item["creates"]} is still missing')


def revision(path):
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
        return None


def status():
    width = max(len(item['name']) for item in MANIFEST['items'])
    mismatched = 0
    for item in MANIFEST['items']:
        where = os.path.relpath(location(item), ROOT)
        if item['kind'] == 'git':
            path = location(item)
            if not path.exists():
                state = 'missing'
            else:
                head = revision(path)
                if head == item['commit']:
                    state = 'ok (pinned commit)'
                else:
                    mismatched += 1
                    state = f'present at {head[:12] if head else "no git checkout"}, pinned {item["commit"][:12]}'
                if 'setup' in item and not (path / item['setup_creates']).exists():
                    state += '; setup pending'
        else:
            state = 'ok' if present(item) else 'missing'
        print(f'{item["name"]:<{width}}  {state:<40}  {where}')
    if mismatched:
        print(f'\n{mismatched} checkout(s) differ from their pin; the build uses them as they are.')


def clean():
    """Removes the fetched inputs inside this repository's .deps; sibling checkouts stay."""
    deps = (ROOT / '.deps').resolve()
    for item in MANIFEST['items']:
        targets = []
        if item['kind'] == 'files':
            targets.append(ROOT / item['dest'])
        elif item['kind'] == 'archive':
            if 'save' in item:
                targets.append(ROOT / item['save'])
            extract = pathlib.PurePosixPath(item['extract'])
            if extract == pathlib.PurePosixPath('.deps'):
                top = pathlib.PurePosixPath(item['creates']).relative_to(extract).parts[0]
                targets.append(ROOT / extract / top)
            else:
                targets.append(ROOT / extract)
        for target in targets:
            target = target.resolve()
            if deps not in target.parents or not target.exists():
                continue
            print(f'deps: removing {os.path.relpath(target, ROOT)}')
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__.strip())
        return
    command, names = argv[0], argv[1:]
    if command == 'status':
        status()
    elif command == 'clean':
        clean()
    elif command == 'fetch':
        for item in items(names):
            fetch(item)
    elif command == 'path':
        if len(names) != 1:
            fail('usage: tools/deps.py path NAME')
        print(location(items(names)[0]))
    else:
        fail(f'unknown command {command} (status, fetch, path)')


if __name__ == '__main__':
    main(sys.argv[1:])
