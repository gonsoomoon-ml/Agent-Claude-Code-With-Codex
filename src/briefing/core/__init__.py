"""core/ — 로컬↔Runtime 공통 '진실(truth)' 코드. runtime/ 은 이걸 배포로 감쌀 뿐.

분리 원칙: core=진실(로직) / runtime=배포 하니스(AgentCore) / local=AWS 없는 baseline.
"""
