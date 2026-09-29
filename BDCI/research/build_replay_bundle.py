"""Build and verify an explicitly incomplete recovery-paper candidate, without APIs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import sys
import zipfile
import unicodedata

# Verification must not mutate an unpacked archive by creating bytecode caches.
sys.dont_write_bytecode = True

import paper_bundle as base
from paper_contracts import validate_paper, validate_review, validate_revision_response, normalize_bound_issues
from replay_paper_evidence import digest
from study_adapter import get_adapter
from resource_accounting import audit_resources, render_report, source_path

HERE = Path(__file__).resolve().parent
PAPER_FILES = ('paper.pdf', 'paper.tex', 'paper.md', 'references.bib', 'paper.json',
    'writer.json', 'reviewer.json', 'reviser.json', 'evidence.json', 'sources.json',
    'input_provenance.json', 'summary.json', 'model_summary.json', 'model_usage.jsonl',
    'continuation.json', 'recovery.json', 'failure.json', 'editorial_revision.json',
    'editorial_assistance.json', 'pdf_validation.json', 'revision_guidance.json') + base.STYLE_FILES + tuple(
    f'{prefix}_{role}.txt' for prefix in ('raw', 'prompt') for role in ('writer', 'reviewer', 'reviser'))


def validate_team_name(value):
    """Accept one portable directory name, preserving Chinese names verbatim."""
    if (not isinstance(value, str) or not value or value != value.strip()
            or value in ('.', '..') or value.endswith('.')
            or any(char in '/\\<>:"|?*' or unicodedata.category(char).startswith('C')
                   for char in value)
            or value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
            or len(value.encode('utf-8')) > 200):
        raise ValueError('invalid_team_name')
    return value


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_bound_review(writer, review, evidence, *, max_field_chars=10000):
    if set(review) != {'verdict', 'external_reviewer', 'issues', 'revision_instructions',
                      'draft_sha256', 'evidence_sha256', 'issue_quotes'}:
        raise ValueError('invalid_bound_review')
    if review['draft_sha256'] != digest(writer) or review['evidence_sha256'] != digest(evidence):
        raise ValueError('review_target_mismatch')
    normalized = normalize_bound_issues({k: review[k] for k in
        ('verdict', 'external_reviewer', 'issues', 'revision_instructions')}, review['issue_quotes'])
    validate_review(normalized, writer, max_field_chars=max_field_chars)
    quotes = review['issue_quotes']
    if not isinstance(quotes, list) or len(quotes) != len(normalized['issues']):
        raise ValueError('unanchored_review')
    sections = {s['id']: s['text'] for s in writer['sections']}
    sections['abstract'] = writer['abstract']
    for issue, quote in zip(normalized['issues'], quotes):
        if not isinstance(quote, str) or not quote.strip() or quote not in sections[issue['section_id']]:
            raise ValueError('ungrounded_review')
    return normalized


def editorial_source(root, research):
    metadata = root / 'editorial_assistance.json'
    if not metadata.exists() or 'source_directory' not in read(metadata):
        return None
    relative = Path(read(metadata)['source_directory'])
    if len(relative.parts) != 2 or relative.parts[0] != 'replay_paper_runs' or relative.name in ('.', '..'):
        raise ValueError('unsafe_editorial_source')
    source = research / relative
    if source == root or not source.is_dir() or source.is_symlink():
        raise ValueError('unsafe_editorial_source')
    if 'source_directory' in read(source / 'editorial_assistance.json'):
        raise ValueError('nested_editorial_source')
    return source


def manuscript_adapter(root, research=HERE):
    root = Path(root)
    source = editorial_source(root, research)
    provenance = read((source or root) / 'input_provenance.json')
    return get_adapter(provenance.get('study_kind', 'replay_v1'))


def validate_manuscript(root, replay_root, research=HERE):
    root = Path(root)
    source = editorial_source(root, research)
    adapter = manuscript_adapter(root, research)
    final_limits = adapter.paper_limits
    review_limits = {"max_field_chars": None} if adapter.is_v2 else {}
    draft_limits = ({"max_words": 1800} if adapter.study_kind == "replay_v1" else final_limits)
    review_limits = {'max_field_chars': None} if adapter.is_v2 else {}
    if source is not None:
        normalized, inherited = validate_manuscript(source, replay_root, research)
        meta = read(root / 'editorial_assistance.json')
        paper, summary = read(root / 'paper.json'), read(root / 'summary.json')
        validate_paper(paper, read(root / 'sources.json'), **final_limits)
        validate_revision_response(paper, read(source / 'reviewer.json'), **review_limits)
        if (meta['source_paper_sha256'] != digest(read(source / 'paper.json'))
                or meta['source_pdf_sha256'] != sha(source / 'paper.pdf')
                or meta['final_paper_sha256'] != digest(paper)
                or meta['new_model_calls'] != 0 or meta['measurements_changed'] is not False
                or read(root / 'evidence.json') != read(source / 'evidence.json')
                or read(root / 'sources.json') != read(source / 'sources.json')
                or summary['pdf']['sha256'] != sha(root / 'paper.pdf')
                or not (root / 'paper.pdf').read_bytes().startswith(b'%PDF-')
                or summary['submission_ready'] is not False
                or summary['external_review_completed'] is not False
                or summary['new_model_calls'] != 0
                or any(summary[k] != inherited[k] for k in ('writing_model_calls', 'writing_total_tokens'))):
            raise ValueError('editorial_source_binding_mismatch')
        return normalized, summary
    evidence, sources = read(root / 'evidence.json'), read(root / 'sources.json')
    previous_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        rebuilt = adapter.build_evidence(replay_root)
    finally:
        sys.dont_write_bytecode = previous_bytecode
    if evidence != rebuilt:
        raise ValueError('saved_evidence_mismatch')
    provenance = read(root / 'input_provenance.json')
    if adapter.study_kind == 'recovery_v2' and provenance.get('profile_sha256') != adapter.profile_sha256():
        raise ValueError('study_profile_binding_mismatch')
    if provenance['evidence_sha256'] != digest(evidence) or provenance['sources_sha256'] != digest(sources):
        raise ValueError('input_provenance_mismatch')
    outputs = {}
    for role in ('writer', 'reviewer', 'reviser'):
        outputs[role] = read(root / f'{role}.json')
        if outputs[role] != adapter.decode((root / f'raw_{role}.txt').read_text()):
            raise ValueError('raw_response_mismatch')
    if adapter.is_v2:
        from run_replay_paper import ReplayPaperState
        state = ReplayPaperState.__new__(ReplayPaperState)
        state.root = root
        state.adapter, state.evidence, state.sources = adapter, evidence, sources
        state.outputs, state.profile_hash = outputs, provenance['profile_sha256']
        for role in ('writer', 'reviewer', 'reviser'):
            if (root / f'prompt_{role}.txt').read_text() != state.prompt(role):
                raise ValueError('saved_prompt_binding_mismatch:' + role)
    validate_paper(outputs['writer'], sources, **draft_limits)
    normalized = validate_bound_review(outputs['writer'], outputs['reviewer'], evidence, **review_limits)
    validate_paper(outputs['reviser'], sources, **draft_limits)
    validate_revision_response(outputs['reviser'], outputs['reviewer'], **review_limits)
    paper = read(root / 'paper.json')
    validate_paper(paper, sources, **final_limits)
    validate_revision_response(paper, outputs['reviewer'], **review_limits)
    if paper != outputs['reviser']:
        assistance = read(root / 'editorial_assistance.json')
        if (assistance['original_model_revision_sha256'] != digest(outputs['reviser'])
                or assistance['final_paper_sha256'] != digest(paper)
                or assistance['new_model_calls'] != 0
                or read(root / 'editorial_revision.json') != paper):
            raise ValueError('editorial_provenance_mismatch')
    summary = read(root / 'summary.json')
    if (summary['pdf']['sha256'] != sha(root / 'paper.pdf')
            or not (root / 'paper.pdf').read_bytes().startswith(b'%PDF-')
            or summary['submission_ready'] is not False
            or summary['external_review_completed'] is not False):
        raise ValueError('invalid_candidate_summary')
    return normalized, summary


def validate_rendered_sources(root, research=HERE):
    root = Path(root)
    adapter = manuscript_adapter(root, research)
    summary = read(root / 'summary.json')
    evidence = copy.deepcopy(read(root / 'evidence.json'))
    evidence['resource'].update({key: summary[key] for key in ('writing_model_calls', 'writing_total_tokens')})
    with tempfile.TemporaryDirectory(prefix='replay-render-check-') as temporary:
        rendered = Path(temporary)
        adapter.render(rendered, read(root / 'paper.json'), read(root / 'sources.json'), evidence, summary['mode'])
        for name in ('paper.tex', 'paper.md', 'references.bib'):
            if (root / name).read_bytes() != (rendered / name).read_bytes():
                raise ValueError('rendered_source_mismatch:' + name)


def writing_chain(root, research=HERE):
    """Resolve only selected local run names; never trust saved absolute paths."""
    chain, seen = [], set()
    current = Path(root)
    original = editorial_source(current, research)
    if original is not None:
        chain.append(current)
        current = original
    while True:
        if current.name in seen:
            raise ValueError('cyclic_continuation')
        seen.add(current.name)
        chain.append(current)
        if not (current / 'continuation.json').exists():
            return chain
        name = Path(read(current / 'continuation.json')['source']).name
        current = research / 'replay_paper_runs' / name
        if not current.is_dir() or current.is_symlink():
            raise ValueError('missing_or_unsafe_continuation')


def select_study(root, explicit=None):
    """A missing saved input is an error; explicit relocation stays content-bound."""
    if explicit is not None:
        selected = Path(explicit).resolve()
    else:
        original = editorial_source(root, HERE)
        provenance = read((original or root) / 'input_provenance.json')
        relative = provenance.get('study_run_relative')
        if relative is not None:
            selected = source_path(HERE, relative)
        else:
            selected = Path(provenance['run'])
            if not selected.is_absolute():
                raise ValueError('ambiguous_legacy_study_path')
    if not selected.is_dir() or selected.is_symlink():
        raise ValueError('study_missing_supply_study_run')
    return selected


def registered_usage(run, inventory, bdci):
    """Relocated copies resolve to one inventory entry, never additional usage."""
    for entry in inventory['runs']:
        if (sha(run / 'model_usage.jsonl') == sha(source_path(bdci, entry['usage']))
                and sha(run / 'model_summary.json') == sha(source_path(bdci, entry['summary']))):
            return entry['usage']
    raise ValueError('unregistered_live_run_update_resource_inventory:' + run.name)


def registered_study(run, inventory, bdci, study_kind='replay_v1'):
    usage = registered_usage(run, inventory, bdci)
    canonical = source_path(bdci, usage).parent
    # Same usage is not permission to overwrite history with edited evidence.
    with tempfile.TemporaryDirectory(prefix='study-binding-') as temporary:
        left, right = Path(temporary) / 'selected', Path(temporary) / 'registered'
        base._copy_study_evidence(run, left, study_kind)
        base._copy_study_evidence(canonical, right, study_kind)
        signature = lambda root: {str(p.relative_to(root)): sha(p) for p in root.rglob('*') if p.is_file()}
        if signature(left) != signature(right):
            raise ValueError('registered_study_content_mismatch')
    relative = str(canonical.relative_to(Path(bdci) / 'research'))
    return relative, usage


def verify_bundle(stage):
    stage = Path(stage)
    if stage.is_symlink():
        raise ValueError('unsafe_bundle_root')
    stage = stage.resolve()
    manifest = read(stage / 'manifest.json')
    if 'bundle_name' in manifest:
        name = validate_team_name(manifest['bundle_name'])
        if stage.name != name:
            raise ValueError('bundle_name_mismatch')
        if manifest.get('team_name') is not None and validate_team_name(manifest['team_name']) != name:
            raise ValueError('team_name_mismatch')
    elif manifest.get('team_name') is not None:
        raise ValueError('missing_bundle_name')
    if manifest.get('submission_ready') is not False or manifest['status'] != 'not_submission_ready':
        raise ValueError('invalid_readiness_claim')
    actual = {str(p.relative_to(stage)): sha(p) for p in stage.rglob('*')
              if p.is_file() and p != stage / 'manifest.json'}
    if any(p.is_symlink() for p in stage.rglob('*')) or actual != manifest['files']:
        raise ValueError('manifest_mismatch')
    research = stage / 'code/BDCI/research'
    paper = research / 'replay_paper_runs' / manifest['paper_run']
    study_relative = manifest.get('study_run', base.REPLAY_RUN)
    study = source_path(research, study_relative)
    _, summary = validate_manuscript(paper, study, research)
    study_kind = manuscript_adapter(paper, research).study_kind
    if manifest.get('study_kind', 'replay_v1') != study_kind:
        raise ValueError('study_kind_binding_mismatch')
    validate_rendered_sources(paper, research)
    if ('integration_only' in manifest and (manifest['integration_only'] is not (summary['mode'] != 'live')
            or manifest.get('writing_mode') != summary['mode'])):
        raise ValueError('writing_mode_claim_mismatch')
    if sha(stage / 'paper/paper.pdf') != summary['pdf']['sha256']:
        raise ValueError('delivered_pdf_mismatch')
    chain = writing_chain(paper, research)
    model_runs = [run for run in chain if (run / 'model_summary.json').exists()]
    totals = {'model_calls': 0, 'total_tokens': 0}
    for run in reversed(model_runs):
        model = read(run / 'model_summary.json')
        usage = [json.loads(line) for line in (run / 'model_usage.jsonl').read_text().splitlines() if line.strip()]
        if (model['model_calls'] != len(usage)
                or model['total_tokens'] != sum(row['total_tokens'] for row in usage)
                or model['model_usage'] != usage):
            raise ValueError('raw_usage_accounting_mismatch')
        if (run / 'continuation.json').exists():
            continued = read(run / 'continuation.json')
            if any(continued['source_summary'][key] != totals[key] for key in totals):
                raise ValueError('continuation_accounting_mismatch')
            parent = research / 'replay_paper_runs' / Path(continued['source']).name
            hashes = continued.get('saved_raw_sha256') or {'writer': continued['writer_sha256']}
            for role, saved_hash in hashes.items():
                if role not in ('writer', 'reviewer') or saved_hash != sha(parent / f'raw_{role}.txt') or saved_hash != sha(run / f'raw_{role}.txt'):
                    raise ValueError('continuation_raw_mismatch')
            if study_kind == 'recovery_v2':
                prompts = continued.get('saved_prompt_sha256', {})
                if set(prompts) != set(hashes):
                    raise ValueError('continuation_prompt_inventory_mismatch')
                for role, expected in prompts.items():
                    if expected != sha(parent / f'prompt_{role}.txt') or expected != sha(run / f'prompt_{role}.txt'):
                        raise ValueError('continuation_prompt_mismatch')
                migration = continued['profile_migration']
                if (migration['from'] != read(parent / 'input_provenance.json')['profile_sha256']
                        or migration['to'] != read(run / 'input_provenance.json')['profile_sha256']
                        or migration['inherited_prompts_identical'] is not True
                        or (migration['from'] != migration['to'] and migration['explicit'] is not True)):
                    raise ValueError('continuation_profile_migration_mismatch')
        for key in totals:
            totals[key] += model[key]
    if totals != {'model_calls': summary['writing_model_calls'], 'total_tokens': summary['writing_total_tokens']}:
        raise ValueError('writing_accounting_mismatch')
    inventory = read(research / 'resource_runs.json')
    audit = audit_resources(stage / 'code/BDCI', inventory)
    if read(stage / 'resource_audit.json') != audit:
        raise ValueError('resource_audit_mismatch')
    registered_relative, study_usage = registered_study(study, inventory, stage / 'code/BDCI', study_kind)
    if registered_relative != study_relative:
        raise ValueError('noncanonical_study_inventory_binding')
    for run in model_runs:
        if read(run / 'model_summary.json')['mode'] == 'live':
            registered_usage(run, inventory, stage / 'code/BDCI')
    if (stage / 'resource_report.md').read_text() != render_report(
            audit, study_usage, {**totals, 'mode': summary['mode']}, study_kind=study_kind):
        raise ValueError('resource_report_mismatch')
    return {'status': 'verified_saved_candidate', 'files': len(actual),
            'submission_ready': False, 'new_model_calls': 0, 'writing': totals,
            'writing_mode': summary['mode'], 'study_run': study_relative, 'study_kind': study_kind, 'archived_live_usage': {
                'model_calls': audit['total_calls'], 'total_tokens': audit['total_tokens']}}


def write_v2_submission_docs(stage, study_relative, paper_run, summary, evidence):
    """Describe the selected v2 artifacts instead of relabeling old v1 docs."""
    study = '../code/BDCI/research/' + study_relative
    research = '../code/BDCI/research/'
    mode = summary['mode']
    totals = {row['policy']: row for row in evidence['summary_by_policy']}
    result_line = '；'.join(f"{policy}: {row['correct_completion']}/{row['episodes']} 正确" for policy, row in totals.items())
    no_gain = (totals['E']['correct_completion'] == totals['A']['correct_completion'] == totals['G']['correct_completion'])
    result_note = ('E的正确完成数没有超过模型原计划A或确定性对照G。' if no_gain else '差异应结合配对基础实例、错误类型和工具调用数评估。')
    base._write(stage / 'docs/architecture.md', f'''# 当前作品架构：recovery_v2

本说明绑定本包研究 `{study_relative}`、论文 `{paper_run}`，写作模式 `{mode}`。
本包尚不可正式提交。仓库历史说明保留在 code/BDCI/docs/submission，
其中旧六实例、18计划、72次重放及严格/事后终止修复属于 v1 历史研究，不能当作本轮结果。

Agent 的选题、方法提案与协议审查使用 JiuwenSwarm 原生 team skill；
开发助手纠正依赖传播、评分真值、信息对称和数据划分后，冻结本轮方案。
选题到实验仍是多个入口，外审与正式提交尚未接入自动闭环。

当前实验由 [run_recovery_v2.py]({research}run_recovery_v2.py) 顺序取得36份模型计划，
在本地CPU执行 A/D/E/F 四个共用计划的策略及不依赖模型计划的确定性 G 策略，合计180次。
九个自编结构留出基础实例各含四种场景；不是180个独立样本，也不是外部独立验证。
冻结输入、源码、原始响应及结果在 [研究目录]({study}/)。

实验后 [run_replay_pipeline.py]({research}run_replay_pipeline.py) 协调
冻结证据复验 → 原生 writer/reviewer/reviser → LaTeX/PDF → 候选ZIP → 包内校验。
[study_adapter.py]({research}study_adapter.py) 按显式 study_kind 选择证据、角色和渲染器；
`recovery_v2_evidence/1` 与旧证据结构分别处理，失败不会回退另一研究。
模型文本与数值表分离；数值表来自复验结果。结构检查、哈希和内部审稿不认证科学结论。

[native_runner.py]({research}native_runner.py) 通过 SwarmFlow、TeamWorkerBackend、DeepAgent
调用模型，注册 ResearchBudgetRail 及官方 skill-use Rail；研究角色 tools=[]，
本地重放和证据检查由 Python 控制程序执行。ExperimentEvidenceRail 仅接入独立 smoke 工具路径。
当前 v2 调用不设人为 token 停止阈值，保留服务自身容量、请求计数、usage与未完成准入保护。
离线写作使用脚本模型，仅验证控制流程；不能宣称新论文由真实模型生成。
''')
    base._write(stage / 'docs/module_call.md', f'''# 所选 v2 模块调用与复现

以下命令从 ZIP 的 `code` 目录执行。依赖安装见该目录 README.md；保存证据验证不需要 API 密钥。

```bash
python BDCI/research/build_replay_bundle.py --verify ..
python BDCI/research/{study_relative}/frozen_source/research/run_recovery_v2.py --verify-run BDCI/research/{study_relative}
```

第一条验证本包文件清单、原始写作响应、审稿目标与引文、研究和角色配置绑定、
确定性渲染来源、PDF哈希、资源清单及冻结研究重放。第二条独立复算36份计划和180次策略执行。
冻结 verifier 需要保留研究目录 basename。它们不会重发模型请求；PDF哈希一致不等于论文语义正确。

真实研究：`run_recovery_v2.py` → 公共工具契约与旧缓存 → 顺序模型计划 →
`recovery_v2_engine.py` 五策略CPU执行 → 独立实现的同作者评分器 → 冻结存档。
写作：`run_replay_paper.py --study-kind recovery_v2 --study-run <run>` →
`recovery_v2_paper_evidence.build_evidence` → recovery-v2-paper team skill 的三角色 →
`recovery_v2_paper_render` → Tectonic。当前 v2 没有1600词或人为token上限。
内部 reviewer 使用同一模型服务，不是 Stanford 外审。

可在依赖和轻量LaTeX就绪后，用已有研究运行新的离线编排验证：
```bash
python BDCI/research/run_replay_pipeline.py --study-kind recovery_v2 --study-run BDCI/research/{study_relative} --output /tmp/recovery-v2-new-integration --team-name 真没招了
```

输出目录必须新建；不带 --live 的写作是脚本响应，不新增真实科学实验。
本包实际写作模式为 `{mode}`；不要运行 --live 来复现保存结果。
实验后协调器保存研究哈希、论文链和ZIP检查点，部分模型响应缺失时不自动重复请求。
选题、提案、协议冻结、外审、正式提交仍不在这一协调入口内。
''')
    base._write(stage / 'docs/innovation.md', f'''# 工程贡献、实测结果与主张边界

JiuwenSwarm 源码已扩展 ResearchBudgetRail 与 ExperimentEvidenceRail。
前者在真实研究编排中记录 admission/usage 并阻止未完成请求被静默重复；
后者只在独立 smoke 工具路径验证文件收据，不代表研究过程已接入工具证据 Rail。
官方贡献 PR 尚未提交，源码存在不等于上游接受。

本轮改进是明确版本的研究证据适配、冻结源码复算、同源论文与资源打包及实验后协调。
角色输出、稿件、审稿对象、引用和渲染来源均可检查；这些工程约束不能替代语义和科学审查。
方案来自 Agent 研究方向与开发助手协议修正，应披露人工介入，不能称完整自主科研。

所选 [v2研究]({study}/) 有九个自编结构留出基础实例、36份真实模型计划、180次策略执行。
{result_line}。{result_note}
不能由全对推出总体等价、统计显著、外部泛化、算法新颖性或保护层额外收益。
静态实际依赖闭包属于已有机制；实际图是给定工具契约，不是新发现算法。
没有注入暂时故障，因此不能主张重试有效性。

本包论文为 `{paper_run}`，写作模式 `{mode}`。离线脚本论文只说明集成链可运行。
旧v1的六实例、18计划、72重放及事后追加终止动作属于历史开发证据，
本轮没有对模型计划事后补终止动作；不得混合两轮统计或把180次重放当独立样本。
仍需完成最终论文质量检查、最终PDF对应Stanford外审Token、官方贡献PR和正式提交验收。
''')


def build_bundle(root, output, study_run=None, team_name=None):
    bundle_name = validate_team_name(team_name) if team_name is not None else 'replay-candidate'
    root, output = Path(root).resolve(), Path(output).resolve()
    study = select_study(root, study_run)
    study_kind = manuscript_adapter(root).study_kind
    review, summary = validate_manuscript(root, study)
    inventory = read(HERE / 'resource_runs.json')
    study_relative, study_usage = registered_study(study, inventory, base.BDCI, study_kind)
    validate_rendered_sources(root)
    chain = writing_chain(root)
    for run in chain:
        if (run / 'model_summary.json').exists() and read(run / 'model_summary.json')['mode'] == 'live':
            registered_usage(run, inventory, base.BDCI)
    output.mkdir(parents=True, exist_ok=True)
    delivery, archive = output / bundle_name, output / (bundle_name + '.zip')
    if delivery.exists() or archive.exists():
        raise FileExistsError('candidate_output_already_exists')
    with tempfile.TemporaryDirectory(prefix='.replay-bundle-', dir=output) as temporary:
        adapter = Path(temporary) / 'adapter'
        adapter.mkdir()
        original = editorial_source(root, HERE)
        for source_root in ([original, root] if original else [root]):
            for name in PAPER_FILES:
                if (source_root / name).exists() or (source_root / name).is_symlink():
                    base._copy(source_root / name, adapter / name, source_root)
        # This compatibility projection follows the complete bound-review checks
        # above. The delivered internal review is restored to the original.
        base._json(adapter / 'reviewer.json', review)
        base.build_bundle(adapter, pilot_root=HERE / base.REVISION_PILOT, summary=summary)
        stage = adapter / 'delivery' / bundle_name
        (adapter / 'delivery/workflow-validation').rename(stage)
        base._copy_study_evidence(study, stage / 'code/BDCI/research' / study_relative, study_kind)
        for run in chain:
            destination = stage / 'code/BDCI/research/replay_paper_runs' / run.name
            for name in PAPER_FILES:
                if (run / name).exists() or (run / name).is_symlink():
                    base._copy(run / name, destination / name, run)
        for source_root in ([original, root] if original else [root]):
            for name in PAPER_FILES:
                if (source_root / name).exists() or (source_root / name).is_symlink():
                    base._copy(source_root / name, stage / 'internal_review' / name, source_root)
        inventory = read(HERE / 'resource_runs.json')
        audit = audit_resources(base.BDCI, inventory)
        base._copy(HERE / 'resource_runs.json',
                   stage / 'code/BDCI/research/resource_runs.json', base.BDCI)
        for entry in inventory['runs']:
            for key in ('usage', 'summary'):
                relative = entry[key]
                base._copy(source_path(base.BDCI, relative), stage / 'code/BDCI' / relative, base.BDCI)
        base._json(stage / 'resource_audit.json', audit)
        base._write(stage / 'resource_report.md', render_report(audit,
            study_usage,
            {'model_calls': summary['writing_model_calls'], 'total_tokens': summary['writing_total_tokens'], 'mode': summary['mode']}, study_kind=study_kind))
        if study_kind == 'recovery_v2':
            write_v2_submission_docs(stage, study_relative, root.name, summary, read(root / 'evidence.json'))
        team_note = (f'队伍名称：{team_name}。ZIP 和顶层目录均采用此名称。'
                     if team_name is not None else 'replay-candidate 不是队伍名称；正式队伍信息待补充。')
        base._write(stage / '提交说明.md', f'''# 开发候选包，尚不能正式提交
本包保存所选恢复实验及绑定论文，研究主张与正式科学验收未完成。
{team_note}
仍缺当前赛题模板复核、最终 PDF 对应的外部 Reviewer Access Token、官方贡献 PR URL。
内部模型审阅不是外部评审；本次打包不调用模型、不上传、不提交。
''')
        if summary['mode'] != 'live':
            note = stage / '提交说明.md'
            base._write(note, note.read_text() + '\n本包论文为离线脚本集成测试产物，不是真实模型生成的新论文。不可用于正式投稿。\n')
        study_command = (f'python BDCI/research/{study_relative}/frozen_source/research/run_recovery_v2.py --verify-run BDCI/research/{study_relative}'
                         if study_kind == 'recovery_v2' else f'python BDCI/research/analyze_replay.py BDCI/research/{study_relative} --verify-only')
        base._write(stage / 'code/REPLAY_REPRODUCTION.md', f'''# Saved recovery evidence
From this code directory, using Python 3.13 and the installed project dependencies:
```bash
python BDCI/research/build_replay_bundle.py --verify ..
{study_command}
```
These commands use saved responses and CPU replay, without model APIs or credentials.
The first verifies file hashes, raw-response equality, review bindings, editorial
provenance, PDF hash, writing accounting and the selected study replay evidence.
It does not certify scientific novelty or external review. Dependency installation
and framework setup are documented in README.md. TeX recompilation requires the
lightweight Tectonic installation and its font/package cache; neither is bundled.
Original absolute paths in provenance are historical metadata; verification resolves
selected run names relative to this archive. No live run is needed for verification.
''')
        manifest = read(stage / 'manifest.json')
        manifest.update(bundle_kind='recovery_paper_development_candidate', submission_ready=False,
                        bundle_name=bundle_name, team_name=team_name,
                        paper_run=root.name, study_run=study_relative, study_kind=study_kind,
                        integration_only=summary['mode'] != 'live', writing_mode=summary['mode'],
                        paper_sha256=summary['pdf']['sha256'],
                        editorial_assistance=summary.get('editorial_assistance', False))
        if team_name is not None:
            manifest['missing_materials'] = [
                'Competition submission validation' if item == 'Final team naming and competition submission validation' else item
                for item in manifest['missing_materials']]
        manifest['missing_materials'].extend(['Unified end-to-end automatic research entry point', 'Independent scientific validation'])
        manifest['files'] = {str(p.relative_to(stage)): sha(p) for p in sorted(stage.rglob('*'))
                             if p.is_file() and p.name != 'manifest.json'}
        base._json(stage / 'manifest.json', manifest)
        for p in stage.rglob('*'):
            if p.is_file() and base.SECRET_PATTERN.search(p.read_bytes()):
                raise ValueError('credential_like_content_in_bundle')
        verify_bundle(stage)
        shutil.move(str(stage), delivery)
    # Fixed ZIP timestamp/order gives reproducible bytes for identical inputs.
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(delivery.rglob('*')):
            if path.is_file():
                info = zipfile.ZipInfo(str(path.relative_to(output)), date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (path.stat().st_mode & 0xffff) << 16
                zipped.writestr(info, path.read_bytes())
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper-run', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--study-run', type=Path, help='Content-bound relocation of the saved compatible study')
    parser.add_argument('--team-name', help='Team name used verbatim for ZIP and top-level directory')
    parser.add_argument('--verify', type=Path, help='Verify an unpacked replay-candidate directory')
    args = parser.parse_args()
    if args.verify:
        if args.paper_run or args.output or args.study_run or args.team_name is not None:
            parser.error('--verify cannot be combined with build arguments')
        print(json.dumps(verify_bundle(args.verify)))
    else:
        if not args.paper_run or not args.output:
            parser.error('--paper-run and --output required')
        print(build_bundle(args.paper_run, args.output, args.study_run, team_name=args.team_name))
