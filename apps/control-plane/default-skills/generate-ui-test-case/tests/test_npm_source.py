import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from read_npm_source import read_sources


def archive_bytes(extra=(), version='1.2.3'):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as bundle:
        for name, content in [('package/package.json', json.dumps({'name':'example', 'version':version}).encode()),
                              ('package/es/control.js', b'export const role = "checkbox";'), *extra]:
            member = tarfile.TarInfo(name)
            if content is None:
                member.type = tarfile.SYMTYPE
                member.linkname = '/tmp/elsewhere'
                bundle.addfile(member)
            else:
                member.size = len(content)
                bundle.addfile(member, io.BytesIO(content))
    return stream.getvalue()


class NpmSourceTests(unittest.TestCase):
    def run_archive(self, root, data, **overrides):
        source = root / 'input.tgz'
        source.write_bytes(data)
        args = dict(package='example', version='1.2.3',
                    integrity='sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode(),
                    output_dir=root/'output', members=['es/control.js'], archive=source)
        args.update(overrides)
        return read_sources(**args)

    def test_selected_bytes_identity_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            report=self.run_archive(root, archive_bytes())
            self.assertEqual(report['verifiedFiles'], 2)
            self.assertEqual((root/'output/source/es/control.js').read_bytes(), b'export const role = "checkbox";')
            evidence=json.loads((root/'output/provenance.json').read_text())
            self.assertEqual(evidence['package'], 'example')
            self.assertEqual(len(evidence['files']), 2)
            self.assertEqual((root/'input.tgz').read_bytes(), (root/'output/archive.tgz').read_bytes())

    def test_integrity_version_and_missing_members_fail_without_output(self):
        for changes in [dict(integrity='sha512-' + base64.b64encode(bytes(64)).decode()),
                        dict(version='1.2.4'), dict(version='^1.2.3'), dict(members=['missing.js'])]:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                with self.assertRaises(ValueError): self.run_archive(root, archive_bytes(), **changes)
                self.assertFalse((root/'output').exists())

    def test_traversal_symlink_and_duplicate_members_are_rejected(self):
        for extra, selected in [([('package/../outside.js',b'x')], ['es/control.js']),
                                ([('package/link.js',None)], ['link.js']),
                                ([('package/es/control.js',b'other')], ['es/control.js'])]:
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                with self.assertRaises(ValueError): self.run_archive(root, archive_bytes(extra), members=selected)
                self.assertFalse((root/'output').exists())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'output').mkdir(); (root/'output/keep').write_text('original')
            with self.assertRaises(ValueError): self.run_archive(root, archive_bytes())
            self.assertEqual((root/'output/keep').read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
