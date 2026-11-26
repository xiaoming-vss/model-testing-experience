/** 历史需求关联的示例产物与冻结输入，字段按 0.1 契约；只供测试使用。 */

const scope = (roles: string[], states: string[], conditions: string[]) => ({ roles, states, conditions })
const item = (itemId: string, text: string, status: string, functionName = '管理员登录') => ({
  itemId, functionId: 'f-1', functionName, sectionTitle: '功能使用与业务规则', text, status, materialBlockIds: [`blk-${itemId}`],
})

export const frozenInput = {
  schemaVersion: '0.1',
  artifactType: 'historical_requirement_relation_input',
  currentRequirement: {
    requirementId: 'req-new', materialSnapshotId: 'mat-new', items: [
      item('1-3-1', '管理员连续输错密码 3 次后锁定账号。', 'confirmed'),
      item('1-3-2', '管理员可通过绑定邮箱自助解锁。', 'unconfirmed'),
    ],
  },
  historicalRequirements: [{
    requirementId: 'req-old', materialSnapshotId: 'mat-old', items: [
      item('1-3-1', '管理员连续输错密码 5 次后锁定账号。', 'confirmed'),
      item('1-3-2', '管理员可通过邮件自助解锁。', 'confirmed'),
    ],
  }],
  knownRelations: [{
    fromRequirementId: 'req-mid', fromMaterialSnapshotId: 'mat-mid',
    toRequirementId: 'req-old', toMaterialSnapshotId: 'mat-old',
    relationType: 'supplements', scope: scope(['全部角色'], ['账号已锁定'], []),
  }],
}

export const analysis = {
  schemaVersion: '0.1',
  artifactType: 'historical_requirement_relation_analysis',
  requirementId: 'req-new',
  materialSnapshotId: 'mat-new',
  relations: [
    {
      relationId: 'rel-1', historicalRequirementId: 'req-old', historicalMaterialSnapshotId: 'mat-old', relationType: 'changes',
      impacts: [
        {
          impactId: 'imp-1', ruleEffect: 'changed', reviewStatus: 'proposed', scope: scope(['管理员'], [], ['连续登录失败']),
          previousRule: '管理员连续输错密码 5 次后锁定账号。', currentRule: '管理员连续输错密码 3 次后锁定账号。',
          changeSummary: '锁定阈值由 5 次降为 3 次。', currentItemIds: ['1-3-1'], historicalItemIds: ['1-3-1'],
        },
        {
          impactId: 'imp-2', ruleEffect: 'retired', reviewStatus: 'needs_confirmation', scope: scope(['管理员'], ['账号已锁定'], []),
          previousRule: '管理员可通过邮件自助解锁。', currentRule: null,
          changeSummary: '是否一并取消待确认。', currentItemIds: ['1-3-2'], historicalItemIds: ['missing'],
        },
      ],
    },
    {
      relationId: 'rel-2', historicalRequirementId: 'req-mid', historicalMaterialSnapshotId: 'mat-mid', relationType: 'supplements',
      impacts: [{
        impactId: 'imp-3', ruleEffect: 'supplemented', reviewStatus: 'proposed', scope: scope([], [], []),
        previousRule: '锁定时记录失败原因。', currentRule: '锁定时记录失败原因与操作人。',
        changeSummary: '追加操作人。', currentItemIds: ['1-3-1'], historicalItemIds: ['missing'],
      }],
    },
  ],
  openQuestions: [
    { impactId: 'imp-2', question: '邮件自助解锁是否一并取消？' },
    { impactId: null, question: '是否涉及第三方登录？' },
  ],
}

export const emptyAnalysis = { ...analysis, relations: [], openQuestions: [{ impactId: null, question: '是否涉及第三方登录？' }] }
