import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('storage_manage', ROOT / 'scripts/manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class StorageConfigurationTests(unittest.TestCase):
    def test_storage_config_only_reaches_control_plane(self):
        config = manage.read(ROOT / 'config/platform.example.toml')
        for key in ('worker_token', 'jwt_key', 'integration_key', 'integration_worker_token',
                    'integration_runtime_generation'):
            config['shared'][key] = 'test-only'
        config['shared']['integration_worker_token'] = 'integration-test-only'
        for key in ('password', 'root_password'):
            config['database'][key] = 'test-only'
        config['control_plane']['storage']['s3'].update({
            'enabled': True, 'endpoint': 'https://objects.test', 'bucket': 'private',
            'access_key': 'test-access', 'secret_key': 'test-secret',
        })
        for mode in ('local', 'docker'):
            result = manage.configurations(config, mode)
            self.assertEqual(result['control-plane']['storage']['s3']['secret_key'], 'test-secret')
            self.assertNotIn('test-secret', repr(result['ai-worker']))
            self.assertNotIn('test-secret', repr(result['api-ui-worker']))
