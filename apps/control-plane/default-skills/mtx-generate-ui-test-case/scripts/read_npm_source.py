#!/usr/bin/env python3
"""Read selected package sources after verifying the caller's lockfile integrity.

Downloads from the public npm registry or reads a supplied archive. Never installs
dependencies, executes package scripts, or writes into the application source tree.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, build_opener

MAX_ARCHIVE = 32 * 1024 * 1024
MAX_FILE = 4 * 1024 * 1024


def registry_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'registry.npmjs.org':
        raise ValueError('Only public npm registry HTTPS URLs are supported')


class RegistryRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        registry_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit):
    registry_url(url)
    with build_opener(RegistryRedirect()).open(url, timeout=30) as response:
        registry_url(response.geturl())
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Source download exceeds the size limit')
    return data


def verify_integrity(data, integrity):
    match = re.fullmatch(r'(sha256|sha384|sha512)-([A-Za-z0-9+/]+={0,2})', integrity)
    if not match:
        raise ValueError('Supply one sha256/sha384/sha512 integrity value from the lockfile')
    expected = base64.b64decode(match[2], validate=True)
    if hashlib.new(match[1], data).digest() != expected:
        raise ValueError('Archive does not match the supplied lockfile integrity')


def relative_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or str(path) != value:
        raise ValueError('Package member must be a normalized relative POSIX path')
    return path


def read_sources(package, version, integrity, output_dir, members=(), archive=None):
    if not re.fullmatch(r'(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]+', package):
        raise ValueError('Invalid npm package name')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?', version):
        raise ValueError('Supply an exact resolved version, not a range or tag')
    output = Path(output_dir).absolute()
    if output.exists():
        raise ValueError('Output directory already exists; use a fresh evidence directory')
    requested = ['package.json', *members]
    for name in requested:
        relative_path(name)
    origin = None
    if archive is None:
        metadata_url = 'https://registry.npmjs.org/' + quote(package, safe='') + '/' + quote(version, safe='')
        metadata = json.loads(fetch(metadata_url, 1024 * 1024))
        if metadata.get('name') != package or metadata.get('version') != version:
            raise ValueError('Registry metadata package/version mismatch')
        origin = metadata['dist']['tarball']
        data = fetch(origin, MAX_ARCHIVE)
    else:
        with Path(archive).open('rb') as handle:
            data = handle.read(MAX_ARCHIVE + 1)
        if len(data) > MAX_ARCHIVE:
            raise ValueError('Archive exceeds the size limit')
    verify_integrity(data, integrity)
    extracted = {}
    inventory = []
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as bundle:
        entries = {}
        total_size = 0
        for index, member in enumerate(bundle):
            if index >= 10000:
                raise ValueError('Archive has too many members')
            relative_path(member.name.rstrip('/'))
            total_size += member.size
            if total_size > 128 * 1024 * 1024:
                raise ValueError('Archive expanded size exceeds the limit')
            if member.name.rstrip('/') == 'package' and member.isdir():
                continue
            if not member.name.startswith('package/'):
                raise ValueError('Archive member is outside package/')
            name = member.name[len('package/'):].rstrip('/')
            if not name:
                continue
            relative_path(name)
            if name in entries:
                raise ValueError('Duplicate archive member: ' + name)
            entries[name] = member
            inventory.append({'path': name, 'bytes': member.size, 'regularFile': member.isfile()})
        for name in dict.fromkeys(requested):
            member = entries.get(name)
            if member is None or not member.isfile() or member.size > MAX_FILE:
                raise ValueError('Requested member is missing, non-regular or too large: ' + name)
            handle = bundle.extractfile(member)
            if handle is None:
                raise ValueError('Cannot read requested member: ' + name)
            extracted[name] = handle.read(MAX_FILE + 1)
            if len(extracted[name]) != member.size:
                raise ValueError('Member size mismatch: ' + name)
    identity = json.loads(extracted['package.json'])
    if identity.get('name') != package or identity.get('version') != version:
        raise ValueError('Archive package.json package/version mismatch')
    report = {'package': package, 'version': version, 'lockIntegrity': integrity,
              'archiveSha256': hashlib.sha256(data).hexdigest(), 'tarballUrl': origin,
              'archiveInput': str(Path(archive).absolute()) if archive else None,
              'files': [{'path': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
                        for name, content in extracted.items()],
              'scope': 'Verified source bytes only; trace current component props and render branches before using locators.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.npm-source-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'evidence'
        stage.mkdir()
        for name, content in extracted.items():
            path = stage / 'source' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        (stage / 'archive.tgz').write_bytes(data)
        (stage / 'members.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
        (stage / 'provenance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if output.exists():
            raise ValueError('Output appeared concurrently; refusing to replace it')
        stage.rename(output)
    return {'outputDir': str(output), 'package': package, 'version': version,
            'verifiedFiles': len(extracted), 'archiveSha256': report['archiveSha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('package', 'version', 'integrity', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--member', action='append', default=[])
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(read_sources(args.package, args.version, args.integrity,
                                     args.output_dir, args.member, args.archive)))
    except (ValueError, KeyError, OSError, tarfile.TarError) as error:
        parser.exit(2, f'Package source read failed: {error}\n')


if __name__ == '__main__':
    main()
