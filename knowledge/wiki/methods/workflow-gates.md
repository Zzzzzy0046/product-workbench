---
id: method-workflow-gates
type: method
domain: workflow
stage: all
platform: [android, ios]
region: [global]
evidence_level: approved-plan
status: active
source:
  - source-workflow-implementation-v1
reviewed_at: 2026-10-21
expires_at:
supersedes: []
tags: [Gate, formal-only, G1, G2, G3, G4, G5]
---

# 工作流 Gate

默认快速流程不使用 Gate、风险清单或条件闭环。日常按市场与竞品分析、原型图＋需求说明、初审修改、终审整理和需求评审继续当前工作，不强制生成全套文档。独立 F2、完整埋点和 F3 实测按需；已有原型、评审或模块资料时可直接开始相应任务。

只有用户明确要求正式机会判断、阶段评审或历史完整流程时才使用：

- G1：机会判断；
- G2：正式产品定义评审；
- G3：正式方案评审；
- G4：基于真实构建和测试证据的研发验收；
- G5：已有真实产品数据后的迭代判断。

计划文档不能证明真实实现已经通过。这个证据原则仍适用于快速模式，但不需要生成 Gate 文档。

正式 G3 的方案闭环至少包含：有边界的 MVP、完整主流程、Loading/Empty/Error 等相关异常、权限和数据规则，以及可执行验收标准。
