"""Copy the canonical contract into independent application packages, or check drift."""
import argparse
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'apps/control-plane/default-skills/mtx-analyze-case-visualization/references'
targets = [root / 'apps/control-plane/src/testing_agent/domain/case_visualization', root / 'apps/ai-worker/src/testing_agent_ai_worker/tasks/case_visualization']
parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
for target in targets:
    for name in ('contract.py', 'output.schema.json'):
        original, destination = source / name, target / name
        if args.check:
            if not destination.exists() or original.read_bytes() != destination.read_bytes():
                raise SystemExit(f'Contract drift: {destination}')
        else:
            target.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(original.read_bytes())
    if not args.check:
        (target / '__init__.py').touch()
example = source / "examples.json"
ui_example = root / "apps/studio/src/features/test-orders/fixtures/visualization.json"
if args.check:
    if example.read_bytes() != ui_example.read_bytes():
        raise SystemExit("Studio visualization fixtures drifted")
else:
    ui_example.parent.mkdir(parents=True, exist_ok=True)
    ui_example.write_bytes(example.read_bytes())
print("Case visualization contract copies are synchronized.")
