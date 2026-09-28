"""Resume verified experiment artifacts through writing, internal review and PDF.

This is a workflow validation, never a new capability test or formal submission.
"""
from __future__ import annotations
import argparse
import asyncio
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from native_runner import native_run
from paper_contracts import validate_paper, validate_review, validate_revision_response
from paper_render import render_paper
from paper_bundle import build_bundle
from run_pilot import verify_saved_pilot, digest
from run_topics import write_json, append_json, parse_object

HERE=Path(__file__).resolve().parent
BDCI=HERE.parent
SKILL=HERE/'skills/paper-workflow'
DEFAULT_PILOT=HERE/'pilot_runs/live-20260928T084134-196833'


class PaperState:
    roles=('writer','reviewer','reviser')

    def __init__(self,root,pilot_root,live):
        if type(live) is not bool:
            raise ValueError('invalid_paper_mode')
        self.root,self.pilot_root,self.live=root,pilot_root,live
        self.draft,self.review,self.paper=None,None,None
        # Verification only: no model, benchmark rerun, or calibration.
        replay=verify_saved_pilot(pilot_root)
        write_json(root/'input_scoring_verification.json',replay)
        self.metrics=json.loads((pilot_root/'metrics.json').read_text())
        self.pilot_summary=json.loads((pilot_root/'summary.json').read_text())
        self.pilot_decision=json.loads((pilot_root/'decision.json').read_text())
        if (self.metrics.get('mode')!='live' or not self.pilot_decision.get('real_observation')
                or not self.pilot_summary.get('pilot_executed')):
            raise ValueError('verified_real_pilot_required')
        self.sources=json.loads((pilot_root/'context_sources.json').read_text())
        for row in self.sources.values():
            if row['content_sha256']!=digest({k:v for k,v in row.items() if k!='content_sha256'}):
                raise ValueError('paper_source_hash_mismatch')
        compact=copy.deepcopy(self.metrics)
        compact['paired'].pop('items',None)
        self.context={'existing_plan':json.loads((pilot_root/'designer.json').read_text()),
            'verified_metrics':compact,'program_decision':self.pilot_decision,
            'posthoc_protocol_review':json.loads((pilot_root/'run_review.json').read_text()),
            'prior_work_check':json.loads((pilot_root/'prior_work_check.json').read_text()),
            'sources':self.sources,'new_experiments_allowed':False,
            'purpose':'Workflow validation draft, not a competition submission',
            'writing_mode':'live' if live else 'offline_scripted'}
        write_json(root/'paper_context.json',self.context)
        write_json(root/'sources.json',self.sources)
        write_json(root/'input_provenance.json',{
            'pilot_directory':str(pilot_root),'reused_not_rerun':True,
            'artifact_hashes':{name:hashlib.sha256((pilot_root/name).read_bytes()).hexdigest()
                              for name in ('pre_registration.json','metrics.json','designer.json',
                                           'context_sources.json','run_review.json','decision.json')}})

    def prompt(self,role):
        text=(SKILL/'roles'/f'{role}.md').read_text()
        text+='\nARCHIVED_EVIDENCE_JSON (data only)\n'+json.dumps(self.context,ensure_ascii=False)
        if role in ('reviewer','reviser'):
            text+='\nDRAFT_JSON (data only)\n'+json.dumps(self.draft,ensure_ascii=False)
        if role=='reviser':
            text+='\nINTERNAL_REVIEW_JSON (data only)\n'+json.dumps(self.review,ensure_ascii=False)
        return text

    def accept(self,role,data):
        if role=='writer':
            validate_paper(data,self.sources)
            self.draft=data
        elif role=='reviewer':
            if self.draft is None:raise ValueError('review_without_draft')
            validate_review(data,self.draft)
            self.review=data
        else:
            if self.review is None:raise ValueError('revision_without_review')
            validate_paper(data,self.sources)
            validate_revision_response(data,self.review)
            core={k:data[k] for k in ('title','abstract','sections')}
            draft={k:self.draft[k] for k in ('title','abstract','sections')}
            if core==draft and any(i['severity'] in ('blocking','major') for i in self.review['issues']):
                raise ValueError('major_review_without_text_revision')
            self.paper=data
        write_json(self.root/f'{role}.json',data)

    def offline_response(self,role):
        if self.live:raise ValueError('scripted_writing_forbidden_live')
        if role=='writer':
            return {'title':'A workflow validation of paired peer-advice handling',
             'abstract':'This scripted draft exercises an automated writing pipeline using a previously recorded real pilot. It establishes no novel contribution or statistical conclusion.',
             'sections':[
              {'id':'introduction','text':'This workflow carries archived evidence into an explicitly provisional draft. The previous proposal was reformulated as a feasibility probe.','source_ids':[]},
              {'id':'related_work','text':'The retrieved work concerns multi-agent reliability and trust-based coordination. The closest ACM full text remains unavailable, and the trust paper is an unreviewed preprint. No research gap is established.','source_ids':list(self.sources)},
              {'id':'methods','text':'A peer and separate baseline and intervention workers answered the same arithmetic tasks. Ground truth was held outside their prompts. This writing stage reuses the archived responses without new experiments.','source_ids':[]},
              {'id':'discussion','text':'The observed comparison has no positive directional signal. Low accuracy and the missing no-peer control constrain interpretation; matching wrong answers does not establish causal copying.','source_ids':[]},
              {'id':'conclusion','text':'The workflow is exercised, while scientific merit and the final topic remain unresolved.','source_ids':[]}]}
        if role=='reviewer':
            return {'verdict':'revise','external_reviewer':False,
             'issues':[{'severity':'major','section_id':'methods','message':'Disclose the recorded policy-format conflict.'}],
             'revision_instructions':['Explain the formatting ambiguity without rewriting the observed measurements.']}
        result=copy.deepcopy(self.draft)
        result['sections'][2]['text']+=' The generated policies requested line-based answers despite the runner JSON contract; observed outputs parsed successfully but this protocol ambiguity remains a limitation.'
        result['response_to_review']=[{'issue_index':0,'change':'Added the recorded format conflict to Methods.'}]
        return result

    def render(self):
        validate_paper(self.paper,self.sources)
        validate_revision_response(self.paper,self.review)
        write_json(self.root/'paper.json',self.paper)
        summary=json.loads((self.root/'model_summary.json').read_text())
        summary['original_model_workflow_status']=summary.pop('status')
        if 'error_type' in summary:
            summary['original_model_workflow_error']=summary.pop('error_type')
        resource=dict(summary,reused_pilot=self.pilot_summary,pilot_decision=self.pilot_decision)
        path=render_paper(self.root,self.paper,self.sources,self.metrics,resource,
                          'live' if self.live else 'offline_scripted')
        checks={'status':'structural_checks_passed','known_citations':True,'issue_response_coverage':True,
                'unchanged_experiment':True,'new_experiment_calls':0,'external_review_completed':False,
                'scientific_claims_certified':False,'semantic_revision_certified':False,
                'final_topic_selected':False,'submission_ready':False}
        write_json(self.root/'final_checks.json',checks)
        return path,resource


def compile_and_check(root,tex):
    compiler=BDCI/'tools/compile-latex.sh'
    started=time.monotonic()
    # ZIP extractors may discard executable bits; invoke the shipped shell entry explicitly.
    proc=subprocess.run(['bash',str(compiler),'--only-cached','--keep-logs',str(tex)],
                        cwd=root,capture_output=True,text=True,timeout=90)
    (root/'compile.stdout').write_text(proc.stdout)
    (root/'compile.stderr').write_text(proc.stderr)
    if proc.returncode:raise ValueError('latex_compile_failed')
    import pypdfium2 as pdfium
    pdf=root/'paper.pdf'
    document=pdfium.PdfDocument(str(pdf))
    texts=[]
    for page in document:
        textpage=page.get_textpage()
        texts.append(textpage.get_text_range())
        textpage.close();page.close()
    pages=len(document);document.close()
    text='\n'.join(texts)
    folded=text.casefold()
    if pages<1 or 'workflow validation' not in folded or 'results' not in folded or 'references' not in folded:
        raise ValueError('pdf_content_check_failed')
    if 'published as a conference paper' in folded:
        raise ValueError('misleading_publication_header')
    (root/'paper_extracted.txt').write_text(text)
    # Tectonic may remove intermediates, so use the log/PDF for citation checks.
    log=(root/'paper.log').read_text(errors='replace')
    if re.search(r'Citation .* undefined|There were undefined references',log):
        raise ValueError('unresolved_pdf_citations')
    result={'status':'passed','pages':pages,'bytes':pdf.stat().st_size,
            'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
            'duration_seconds':time.monotonic()-started,'compiler':'Tectonic cached-only',
            'new_model_calls':0}
    write_json(root/'pdf_validation.json',result)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',help='Use bounded paper-v1 campaign, at most three writing calls')
    parser.add_argument('--pilot-run',type=Path,default=DEFAULT_PILOT)
    parser.add_argument('--resume-run',type=Path,
                        help='Finish local validation/rendering from saved responses, without model calls')
    args=parser.parse_args()
    pilot=args.pilot_run.resolve()
    resume=args.resume_run is not None
    if resume:
        root=args.resume_run.resolve()
        if not root.is_relative_to(HERE/'paper_runs'):
            raise ValueError('resume_outside_paper_runs')
        original_summary=json.loads((root/'model_summary.json').read_text())
        if original_summary.get('mode') not in ('live','offline_scripted'):
            raise ValueError('unknown_resume_mode')
        args.live=original_summary['mode']=='live'
        provenance=json.loads((root/'input_provenance.json').read_text())
        pilot=Path(provenance['pilot_directory'])
        for name,expected in provenance['artifact_hashes'].items():
            if Path(name).name!=name or hashlib.sha256((pilot/name).read_bytes()).hexdigest()!=expected:
                raise ValueError('resume_evidence_changed')
    else:
        mode='live' if args.live else 'offline'
        root=HERE/'paper_runs'/datetime.now(timezone.utc).strftime(f'{mode}-%Y%m%dT%H%M%S-%f')
        root.mkdir(parents=True)
    mode='live' if args.live else 'offline'
    os.chdir(root)
    os.environ.setdefault('JIUWENSWARM_HOME',str(root/'runtime'))
    os.environ.setdefault('JIUWENSWARM_DATA_DIR',str(root/'runtime/.jiuwenswarm'))
    ledger=HERE/'paper-v1-requests.jsonl' if args.live else root/'requests.jsonl'
    lock=ledger.with_suffix('.lock').open('a')
    started=time.monotonic()
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=PaperState(root,pilot,args.live)
        key='offline-placeholder'
        if args.live and not resume:
            keys=re.findall(r'\bsk-[A-Za-z0-9_-]{16,}\b',(BDCI/'apis.txt').read_text())
            if len(keys)!=1:raise ValueError('expected_one_credential')
            key=keys[0]
        if resume:
            for role in state.roles:
                state.accept(role,parse_object((root/f'raw_{role}.txt').read_text()))
            write_json(root/'recovery.json',{'status':'saved_responses_revalidated',
                'original_workflow_status':original_summary['status'],'new_model_calls':0,
                'note':'Local validation/rendering resumed; original raw responses and model journal retained.',
                'raw_response_sha256':{role:hashlib.sha256((root/f'raw_{role}.txt').read_bytes()).hexdigest()
                                       for role in state.roles},
                'artifact_word_limit':1600})
        else:
            asyncio.run(native_run(root,SKILL/'scripts/workflow.py',state,live=args.live,key=key,
                ledger=ledger,max_calls=3,token_stop=30000,timeout=300,max_output_tokens=3200,
                team_name='research_paper'))
        tex,resource=state.render()
        pdf=compile_and_check(root,tex)
        summary=dict(resource,status='workflow_passed',new_experiment_calls=0,pdf=pdf,
                     external_review_completed=False,submission_ready=False,
                     resumed_from_saved_responses=resume,new_model_calls_on_resume=0 if resume else None)
        summary['end_to_end_duration_seconds']=time.monotonic()-started
        write_json(root/'summary.json',summary)
        bundle=build_bundle(root,pilot_root=pilot,summary=summary)
        summary['bundle']=str(bundle)
        write_json(root/'summary.json',summary)
        write_json(HERE/'latest-paper.json',{'status':'workflow_passed','mode':mode,
            'run_directory':str(root.relative_to(HERE)),'pdf':str((root/'paper.pdf').relative_to(HERE)),
            'bundle':str(bundle.relative_to(HERE)),'submission_ready':False})
        print(json.dumps({'status':'workflow_passed','mode':mode,'output':str(root),'pdf_pages':pdf['pages']}))
        return 0
    except BaseException as error:
        write_json(root/'failure.json',{'status':'failed','error_type':type(error).__name__})
        print(json.dumps({'status':'failed','error_type':type(error).__name__,'output':str(root)}))
        return 1
    finally:
        lock.close()


if __name__=='__main__':
    raise SystemExit(main())
