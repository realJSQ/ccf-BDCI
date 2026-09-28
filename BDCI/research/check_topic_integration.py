"""Real-framework failure path: budget two must prevent the critic request.

Run separately in a normal shell; the managed sandbox cannot wake aiofiles threads.
No network, no credential reads. Output lives in a fresh guard-* run directory.
"""
import asyncio
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from run_topics import HERE, execute


def main():
    root = Path(tempfile.mkdtemp(prefix='guard-', dir=HERE / 'runs'))
    os.chdir(root)
    from jiuwenswarm.agents.harness.common.rails import research_budget_rail as module
    original = module.ResearchRunBudget
    def limited(root, ledger):
        return original(root, ledger, max_calls=2)
    try:
        with patch.object(module, 'ResearchRunBudget', limited):
            asyncio.run(execute(root, False, 'offline-placeholder', root / 'requests.jsonl'))
    except asyncio.CancelledError as error:
        assert str(error) == 'research_call_limit', type(error).__name__
    else:
        raise AssertionError('third_model_request_not_blocked')
    summary = json.loads((root / 'summary.json').read_text())
    assert summary['model_calls'] == 2
    assert len(summary['model_usage']) == 2
    assert not (root / 'critic.json').exists()
    assert not (root / 'pilot_handoff.json').exists()
    result = {'status':'passed', 'admissions':2, 'responses':2, 'critic_blocked':True,
              'mode':'offline_scripted', 'output':str(root)}
    (root / 'guard_result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
