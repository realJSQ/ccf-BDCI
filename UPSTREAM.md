# Upstream provenance

- Repository: https://atomgit.com/openJiuwen/jiuwenswarm
- Branch at setup: develop
- Commit: fc18e5c572a6b3b62bb42ea843cce674140e4266
- Import: tracked working-tree source snapshot under BDCI/jiuwenswarm, without Git history.
- Original license: BDCI/jiuwenswarm/LICENSE; retain OPEN_SOURCE_SOFTWARE_NOTICE.md and nested notices.

Local additions to the upstream tree:

- jiuwenswarm/agents/harness/common/rails/research_evidence_rail.py
- jiuwenswarm/agents/harness/common/rails/research_budget_rail.py

Research skills, runners, tests, documentation and archived validation artifacts
are in BDCI/research, BDCI/validation and BDCI/docs. Original upstream tracked files
were copied without content changes. This is not an upstream contribution PR.

Dependencies pinned in the tested environment:

- agent-core: 9e3390195a9ea15235b2b5f7412cb2aa440622cc
- agent-protocol / intelli-router: f70ae827ba059deddef87406f90b77bcde403dc1

Official ICLR template source is included only for compilation validation; it is
not an original project paper. Tectonic's license and provenance are retained,
while its binary and downloaded TeX cache are installed locally on demand.
