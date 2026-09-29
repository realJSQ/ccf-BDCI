"""Explicit study profiles; no failure-based fallback to a different study."""
from pathlib import Path
import hashlib

from replay_paper_evidence import digest

HERE = Path(__file__).resolve().parent


class StudyAdapter:
    def __init__(self, kind):
        if kind not in ('replay_v1', 'recovery_v2'):
            raise ValueError('unknown_study_kind')
        self.kind = self.study_kind = kind
        self.skill = HERE / 'skills' / ('recovery-v2-paper' if kind == 'recovery_v2' else 'replay-paper')
        self.paper_limits = {'max_words': None, 'max_field_chars': None} if self.is_v2 else {}

    @property
    def is_v2(self):
        return self.kind == 'recovery_v2'

    def build_evidence(self, run):
        if self.is_v2:
            from recovery_v2_paper_evidence import build_evidence
        else:
            from replay_paper_evidence import build_evidence
        return build_evidence(run)

    def decode(self, raw):
        if self.is_v2:
            from run_recovery_v2 import RecoveryState
            value = RecoveryState.decode_response(raw)
            if 'invalid_model_response' in value:
                raise ValueError('invalid_model_json')
            return value
        from run_topics import parse_object
        return parse_object(raw)

    def render(self, root, paper, sources, evidence, mode):
        if self.is_v2:
            from recovery_v2_paper_render import render_recovery_v2_paper as render
        else:
            from replay_paper_render import render_replay_paper as render
        return render(root, paper, sources, evidence, mode)

    def profile_sha256(self):
        renderer = HERE / ('recovery_v2_paper_render.py' if self.is_v2 else 'replay_paper_render.py')
        paths = [renderer, *sorted(self.skill.rglob('*.md')), *sorted(self.skill.rglob('*.py'))]
        if self.is_v2:
            paths += [HERE / name for name in ('run_replay_paper.py', 'paper_contracts.py', 'study_adapter.py')]
        return digest({str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})

    def verification_command(self, run):
        run = Path(run)
        if self.is_v2:
            return [str(run / 'frozen_source/research/run_recovery_v2.py'), '--verify-run', str(run)]
        return [str(HERE / 'analyze_replay.py'), str(run), '--verify-only']


def get_adapter(kind='replay_v1'):
    return StudyAdapter(kind)
